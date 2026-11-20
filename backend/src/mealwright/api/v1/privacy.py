"""Settings › Outside connections: the switches for outside connections and "Your own network".

Everyone in the household can read both; only an admin can change them (spec section 6,
"Recipe import, decided for 0.5": the photo switch and the allow list). Both are stored with
the household. A change takes effect at once: the outbound gate reads the switches and the
list each time it is about to connect, so there is nothing to restart.

Every change is in Recent changes with an Undo, for an admin (D4, BE5, cabledrawer 20 Nov;
`privacy_changes.py`), and each answer carries its change for the toast's Undo. A request with
an Idempotency-Key that is sent again answers as the first did and changes nothing more.

Nothing here makes a network connection. Log lines name the switch in plain words and never
an address: an entry on the list is an address too, so the log says only that one was added
or removed. They go on the sign-in log with the admin's username (D4, BE24 and BE25).
"""

import ipaddress
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from mealwright import own_network, privacy_changes, sso_accounts
from mealwright.api.v1.context import Here
from mealwright.api.v1.schemas import ChangeOut
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.foods import change_out
from mealwright.history import commit, replayed
from mealwright.household import today
from mealwright.kitchen_changes import key_kept
from mealwright.models import Change, Household, OwnNetworkEntry, as_utc
from mealwright.outbound import LABELS, Connection, set_switch
from mealwright.outbound import switches as stored_switches
from mealwright.roles import Action
from mealwright.shopping import lock_household

# Sign-in and privacy events share one logger (D4, BE25).
log = logging.getLogger("mealwright.sign_in")

PASSWORDS_BACK_ON_OWN_NETWORK = privacy_changes.PASSWORDS_BACK_ON_OWN_NETWORK

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
    # The change a switch made, for the toast's Undo (D4, BE5). Null on a read, and when the
    # switch was already as asked.
    change: ChangeOut | None = None


class SwitchIn(BaseModel):
    on: bool


def _made(kitchen: Here, made: Change | None) -> ChangeOut | None:
    """The change to answer with: one of this page's own (not a kept key)."""
    if made is None or made.kind not in privacy_changes.KINDS:
        return None
    return change_out(kitchen, made)


def _switches(kitchen: Here, made: Change | None = None) -> SwitchesOut:
    stored = stored_switches(kitchen.db, kitchen.household_id)
    return SwitchesOut(
        switches=[SwitchOut(connection=c.value, on=stored[c]) for c in SHOWN],  # type: ignore[arg-type]
        can_change=kitchen.may(Action.PRIVACY),
        change=_made(kitchen, made),
    )


def _start(kitchen: Here, response: Response) -> Change | None:
    """Admins only; the household's lock (two admins at once can't pass the list's limit). A
    retry of a change already made: that change."""
    kitchen.admin_only(Action.PRIVACY)
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is not None:
        response.headers["Idempotent-Replayed"] = "true"
    return earlier


def _commit(kitchen: Here, response: Response) -> Change | None:
    """Commit. Another request with the same key got there first: its change."""
    earlier = commit(kitchen)
    if earlier is not None:
        response.headers["Idempotent-Replayed"] = "true"
    return earlier


@router.get("/privacy/switches")
def get_switches(kitchen: Here) -> SwitchesOut:
    """Every Privacy switch of the household, on or off. They all start off."""
    return _switches(kitchen)


def _not_locked_out(kitchen: Here) -> None:
    """Refuse (409 `locked_out`) when the admin asking is the last who can get in and has only a
    single sign-on link (cabledrawer 14 Nov): ending single sign-on would lock them out."""
    if sso_accounts.would_lock_out(kitchen.db, kitchen.data_dir, kitchen.login):
        raise privacy_changes.locked_out()


@router.put("/privacy/switches/{connection}")
def put_switch(connection: Shown, body: SwitchIn, kitchen: Here, response: Response) -> SwitchesOut:
    """Admins only. Turn one switch on or off; the next connection follows it at once.
    Asking for the state it already has changes nothing. Answers with all the switches and
    the change made (`connection_changed`, in Recent changes with an Undo)."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _switches(kitchen, earlier)
    kind = Connection(connection)
    was = stored_switches(kitchen.db, kitchen.household_id)[kind]
    made = None
    if was == body.on:
        key_kept(kitchen)
    else:
        if kind is Connection.SINGLE_SIGN_ON and not body.on:
            _not_locked_out(kitchen)
        set_switch(kitchen.db, kitchen.household_id, kind, body.on)
        made = privacy_changes.connection_changed(kitchen, kind, body.on)
    earlier = _commit(kitchen, response)
    if earlier is not None:
        return _switches(kitchen, earlier)
    if made is not None:
        log.info(
            "Privacy: %s switched %s by %s",
            LABELS[kind],
            "on" if body.on else "off",
            kitchen.login.username,
        )
    return _switches(kitchen, made)


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
    # The change that added it, for the toast's Undo (D4, BE5). Only in the answer to an add.
    change: ChangeOut | None = None


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
        can_change=kitchen.may(Action.PRIVACY),
    )


# The sentence the checks gave, with the answer's status and its code.
_REFUSALS = {
    own_network.BAD_ENTRY: (status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_entry"),
    own_network.NEVER: (status.HTTP_422_UNPROCESSABLE_CONTENT, "always_blocked"),
    own_network.TOO_WIDE: (status.HTTP_422_UNPROCESSABLE_CONTENT, "too_wide"),
    own_network.ALREADY: (status.HTTP_409_CONFLICT, "already_there"),
    own_network.FULL: (status.HTTP_409_CONFLICT, "too_many_entries"),
}


def _refused(sentence: str) -> Problem:
    code = _REFUSALS.get(sentence, (status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_entry"))
    return Problem(code[0], code[1], sentence)


class PasswordsBackOn(BaseModel):
    """What taking an entry off answers, always (0.9.5-beta.3, D2, BE16)."""

    passwords_back_on: bool
    notice: str | None
    # The change that took it off, for the toast's Undo (D4, BE5).
    change: ChangeOut | None = None


@router.get("/privacy/own-network")
def get_own_network(kitchen: Here) -> OwnNetworkOut:
    """The household's "Your own network" list, oldest first. It starts empty."""
    return _list(kitchen)


def _added(kitchen: Here, made: Change) -> EntryOut:
    """The answer to an add, first or replayed: the entry as it is now, with its change. One
    taken off since is answered as it was added (from the change)."""
    data = (made.undo_data or {}).get("entry", {})
    row = kitchen.db.get(OwnNetworkEntry, data.get("id", 0))
    if row is None or row.household_id != kitchen.household_id:
        raise not_found("That entry")
    out = _entry(row, kitchen.household)
    out.change = _made(kitchen, made)
    return out


@router.post("/privacy/own-network", status_code=status.HTTP_201_CREATED)
def add_entry(body: EntryIn, kitchen: Here, response: Response) -> EntryOut:
    """Admins only. Add a host name, one address or a range (CIDR) to the list. A refusal
    comes with its own sentence and a `code`: `bad_entry`, `always_blocked`, `too_wide`
    (422), `already_there` or `too_many_entries` (409). Answers with the entry and its change
    (`own_network_added`)."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _added(kitchen, earlier)
    try:
        row = own_network.add(kitchen.db, kitchen.household_id, body.value, kitchen.login)
    except ValueError as error:
        kitchen.db.rollback()
        raise _refused(str(error)) from None
    made = privacy_changes.own_network_added(kitchen, row)
    try:
        earlier = _commit(kitchen, response)
    except IntegrityError:  # the same entry added in the same moment
        kitchen.db.rollback()
        raise _refused(own_network.ALREADY) from None
    if earlier is not None:
        return _added(kitchen, earlier)
    log.info("Your own network: added by %s", kitchen.login.username)
    return _added(kitchen, made)


@router.delete("/privacy/own-network/{entry_id}")
def remove_entry(entry_id: StoredInt, kitchen: Here, response: Response) -> PasswordsBackOn:
    """Admins only. Take one entry off the list. An entry of another household is "not
    here" too. Answers `passwords_back_on` false and `notice` null, or true with a `notice` to
    show when password sign-in was off and this entry was what let Mealwright reach the
    sign-in server: passwords are on again. `change` is the removal (`own_network_removed`)."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _removed(kitchen, earlier)
    try:
        entry, back_on = privacy_changes.take_off(kitchen, entry_id)
    except Problem:
        kitchen.db.rollback()
        raise
    if entry is None:
        raise not_found("That entry")
    made = privacy_changes.own_network_removed(kitchen, entry)
    if back_on:
        made.undo_data = {**(made.undo_data or {}), "passwords_back_on": True}
    earlier = _commit(kitchen, response)
    if earlier is not None:
        return _removed(kitchen, earlier)
    log.info("Your own network: removed by %s", kitchen.login.username)
    if back_on:
        log.info("Single sign-on: passwords work again, it can't start without that entry")
    return _removed(kitchen, made)


def _removed(kitchen: Here, made: Change) -> PasswordsBackOn:
    """The answer to a removal, first or replayed (the notice is kept with the change)."""
    back_on = bool((made.undo_data or {}).get("passwords_back_on"))
    return PasswordsBackOn(
        passwords_back_on=back_on,
        notice=PASSWORDS_BACK_ON_OWN_NETWORK if back_on else None,
        change=_made(kitchen, made),
    )
