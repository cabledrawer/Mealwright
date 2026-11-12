"""Settings → Privacy: the switches for outside connections and "Your own network".

Everyone in the household can read both; only an admin can change them (spec section 6,
"Recipe import, decided for 0.5": the photo switch and the allow list). Both are stored with
the household. A change takes effect at once: the outbound gate reads the switches and the
list each time it is about to connect, so there is nothing to restart.

Nothing here makes a network connection. Log lines name the switch in plain words and never
an address: an entry on the list is an address too, so the log says only that one was added
or removed.
"""

import ipaddress
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from mealwright import own_network, sso, sso_accounts
from mealwright.api.v1.context import Here
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.history import as_utc
from mealwright.household import today
from mealwright.models import Household, OwnNetworkEntry
from mealwright.outbound import LABELS, Connection, set_switch
from mealwright.outbound import switches as stored_switches
from mealwright.roles import Action, allowed
from mealwright.shopping import lock_household

log = logging.getLogger(__name__)

# Proposed, for cabledrawer (O1 review r2, finding 2).
PASSWORDS_BACK_ON_OWN_NETWORK = (
    "Removed. Password sign-in is on again, because your sign-in server is no longer on Your "
    "own network. Add it back and test sign-in, or turn password sign-in off again later."
)

router = APIRouter(tags=["privacy"], dependencies=[SameOrigin])

# The switches that do something in this version, in the order the Privacy mockup draws them.
# Notifications appear here when they arrive.
SHOWN = (
    Connection.RECIPE_IMPORT,
    Connection.RECIPE_PHOTOS,
    Connection.SINGLE_SIGN_ON,
    Connection.UPDATE_CHECK,
)
Shown = Literal["recipe_import", "recipe_photos", "single_sign_on", "update_check"]


class SwitchOut(BaseModel):
    connection: Shown
    on: bool


class SwitchesOut(BaseModel):
    switches: list[SwitchOut]
    # False for a member: they see the switches and can't change them.
    can_change: bool


class SwitchIn(BaseModel):
    on: bool


def _switches(kitchen: Here) -> SwitchesOut:
    stored = stored_switches(kitchen.db, kitchen.household_id)
    return SwitchesOut(
        switches=[SwitchOut(connection=c.value, on=stored[c]) for c in SHOWN],  # type: ignore[arg-type]
        can_change=allowed(kitchen.login.role, Action.PRIVACY, kitchen.by_token),
    )


@router.get("/privacy/switches")
def get_switches(kitchen: Here) -> SwitchesOut:
    """Every Privacy switch of the household, on or off. They all start off."""
    return _switches(kitchen)


@router.put("/privacy/switches/{connection}")
def put_switch(connection: Shown, body: SwitchIn, kitchen: Here) -> SwitchesOut:
    """Admins only. Turn one switch on or off; the next connection follows it at once.
    Asking for the state it already has changes nothing. Answers with all the switches."""
    kitchen.admin_only(Action.PRIVACY)
    kind = Connection(connection)
    was = stored_switches(kitchen.db, kitchen.household_id)[kind]
    set_switch(kitchen.db, kitchen.household_id, kind, body.on)
    kitchen.db.commit()
    if was != body.on:
        log.info("Privacy: %s switched %s", LABELS[kind], "on" if body.on else "off")
    return _switches(kitchen)


# --- Your own network ----------------------------------------------------------------------


class EntryOut(BaseModel):
    id: int
    kind: Literal["name", "address", "range"]
    value: str
    # How many addresses an IPv4 range holds (it is at most /8, so 16,777,216). None for
    # anything else: a name or one address, and an IPv6 range, which holds too many to count.
    addresses: int | None
    added_by: str
    # The day it was added, in the household's time zone (like every date in the app).
    added_on: date


class OwnNetworkOut(BaseModel):
    entries: list[EntryOut]
    limit: int
    can_change: bool


class EntryIn(BaseModel):
    # Anything longer than a host name can be is refused by the checks with the usual
    # sentence; this only bounds what is read.
    value: str = Field(max_length=1000)


def _entry(row: OwnNetworkEntry, household: Household) -> EntryOut:
    addresses: int | None = None
    if row.kind == "range":
        network = ipaddress.ip_network(row.value)
        if network.version == 4:
            addresses = network.num_addresses
    return EntryOut(
        id=row.id,
        kind=row.kind,  # type: ignore[arg-type]
        value=row.value,
        addresses=addresses,
        added_by=row.added_by_name,
        added_on=today(household, as_utc(row.added_at)),
    )


def _list(kitchen: Here) -> OwnNetworkOut:
    return OwnNetworkOut(
        entries=[
            _entry(e, kitchen.household)
            for e in own_network.entries(kitchen.db, kitchen.household_id)
        ],
        limit=own_network.MAX_ENTRIES,
        can_change=allowed(kitchen.login.role, Action.PRIVACY, kitchen.by_token),
    )


# The sentence the checks gave, with the answer's status and its code.
_REFUSALS = {
    own_network.BAD_ENTRY: (status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_entry"),
    own_network.NEVER: (status.HTTP_422_UNPROCESSABLE_CONTENT, "always_blocked"),
    own_network.TOO_WIDE: (status.HTTP_422_UNPROCESSABLE_CONTENT, "too_wide"),
    own_network.ALREADY: (status.HTTP_409_CONFLICT, "already_listed"),
    own_network.FULL: (status.HTTP_409_CONFLICT, "list_full"),
}


def _refused(sentence: str) -> Problem:
    code = _REFUSALS.get(sentence, (status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_entry"))
    return Problem(code[0], code[1], sentence)


class PasswordsBackOn(BaseModel):
    passwords_back_on: Literal[True]
    notice: str


@router.get("/privacy/own-network")
def get_own_network(kitchen: Here) -> OwnNetworkOut:
    """The household's "Your own network" list, oldest first. It starts empty."""
    return _list(kitchen)


@router.post("/privacy/own-network", status_code=status.HTTP_201_CREATED)
def add_entry(body: EntryIn, kitchen: Here) -> EntryOut:
    """Admins only. Add a host name, one address or a range (CIDR) to the list. A refusal
    comes with its own sentence and a `code`: `bad_entry`, `always_blocked`, `too_wide`
    (422), `already_listed` or `list_full` (409)."""
    kitchen.admin_only(Action.PRIVACY)
    lock_household(kitchen)  # so two admins adding at once can't go past the limit
    try:
        row = own_network.add(kitchen.db, kitchen.household_id, body.value, kitchen.login)
        kitchen.db.commit()
    except ValueError as error:
        kitchen.db.rollback()
        raise _refused(str(error)) from None
    except IntegrityError:  # the same entry added in the same moment
        kitchen.db.rollback()
        raise _refused(own_network.ALREADY) from None
    log.info("Your own network: added")
    return _entry(row, kitchen.household)


@router.delete(
    "/privacy/own-network/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={200: {"model": PasswordsBackOn}},
)
def remove_entry(entry_id: StoredInt, request: Request, kitchen: Here) -> Response:
    """Admins only. Take one entry off the list. An entry of another household is "not
    here" too. 204 normally. 200 with `passwords_back_on` and a `notice` to show when password
    sign-in was off and this entry was what let Mealwright reach the sign-in server: passwords
    are on again."""
    kitchen.admin_only(Action.PRIVACY)
    if not own_network.remove(kitchen.db, kitchen.household_id, entry_id):
        raise not_found("That entry")
    kitchen.db.commit()
    log.info("Your own network: removed")
    if _passwords_back_on(request, kitchen):
        return JSONResponse({"passwords_back_on": True, "notice": PASSWORDS_BACK_ON_OWN_NETWORK})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _passwords_back_on(request: Request, kitchen: Here) -> bool:
    """With password sign-in off, the sign-in server must stay reachable: if this removal made
    it unreachable (its address is no longer on the list), turn passwords back on, so nobody is
    locked out. True when it did."""
    db = kitchen.db
    row = sso_accounts.settings_row(db, kitchen.household_id)
    if row is None or row.password_sign_in or not sso_accounts.usable(row):
        return False
    if not sso_accounts.switch_on(db, kitchen.household_id):
        return False  # passwords already work with the switch off
    household_id, issuer = kitchen.household_id, row.issuer
    listed = own_network.load(db, household_id)
    db.rollback()  # the look-up below may wait: hold no database connection meanwhile
    gate = request.app.state.outbound
    if not sso.issuer_off_the_list(gate, household_id, issuer, listed):
        return False
    row = sso_accounts.settings_row(db, household_id)
    if row is None or row.password_sign_in or row.issuer != issuer:
        return False
    row.password_sign_in = True
    db.commit()
    log.warning("Single sign-on: password sign-in is on again, its sign-in server left the list")
    return True
