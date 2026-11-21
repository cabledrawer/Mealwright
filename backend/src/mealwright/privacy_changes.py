"""Settings › Outside connections in Recent changes, with Undo (0.9.5-beta.3, D4, BE5).

cabledrawer 20 Nov: "outside-connection switches and Your own network go into Recent changes
with Undo (as the spec said)". Three kinds, each listed in `change_kinds.PRIVACY`, made and
undone only by an admin (`roles.ADMIN_KINDS`, never through an API token):

- `connection_changed`: one switch turned on or off. Its Undo puts the switch back while it is
  still as the change left it and nobody has changed that switch since; the outbound gate reads
  the switch each time, so an Undo of "switched on" blocks the next connection at once.
- `own_network_added`: an entry added. Its Undo takes that entry off again while it is there.
- `own_network_removed`: an entry taken off. Its Undo is refused (below).

An Undo never lets more go out (release security pass beta.3, Low 2; proposed, for
cabledrawer): every outside connection is off until someone turns it on on purpose, and one
Ctrl+Z / Cmd+Z, up to 7 days later, is not that. So the Undo of "Switched … off", and of
"Removed … from Your own network" (it would let the app reach that place again; before this it
added the entry back as a new one), is refused with `409 cannot_undo`, naming where to do it on
purpose. The Undo of "Switched … on" and of "Added …" still works. The change keeps `can_undo`,
so Ctrl+Z after a reload stops at it and says why rather than going on to an older change.

An Undo that would end single sign-on is held to the same rule as the screen's own switch and
Remove (cabledrawer 14 Nov): refused with `409 locked_out` when it would lock this admin out.
An Undo that turns password sign-in back on says so, as Remove does.

Log lines name the switch in plain words and never an address (see `api/v1/privacy.py`).
"""

import logging
from typing import Any

from fastapi import status
from sqlalchemy import Select, select
from sqlalchemy.orm import aliased

from mealwright import change_kinds, own_network, sso_accounts
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.history import record
from mealwright.models import Change, OwnNetworkEntry
from mealwright.outbound import LABELS, Connection, set_switch, switches
from mealwright.roles import Action

KINDS = change_kinds.PRIVACY

# Sign-in and privacy events share one logger (D4, BE25).
log = logging.getLogger("mealwright.sign_in")

# Proposed, for cabledrawer (O1 review r2, finding 2; r3: worded from `sso_can_start`).
PASSWORDS_BACK_ON_OWN_NETWORK = (
    "Removed. Passwords work again for now, because single sign-on can’t start without that "
    "entry: your sign-in server is no longer on Your own network. Add it back and "
    "passwords are off again."
)


# --- Who sees them (security review beta.3, finding 1) -----------------------------------------
#
# Proposed, for cabledrawer: an own-network change names its entry ("Added 192.168.1.0/24 to Your
# own network"), and the list itself is read only by those with the Privacy permission (an admin
# at a screen; never a member, never an API token: `GET /privacy/own-network`, D4, BE12). So those
# changes, and the Undos of them, are left out of Recent changes for everyone else, and are "not
# here" (404) when asked for by id. A switch change stays visible: the switches are readable by
# everyone in the household anyway.
OWN_NETWORK_KINDS = ("own_network_added", "own_network_removed")


def can_see_own_network(kitchen: Kitchen) -> bool:
    """Whether this caller may read Your own network, and so its changes: the same test as
    `GET /privacy/own-network`."""
    return kitchen.may(Action.PRIVACY)


def leave_out_hidden(kitchen: Kitchen, query: Select[Any]) -> Select[Any]:
    """Recent changes' query, without the own-network changes and the Undos of them when this
    caller can't read Your own network. Done in the query, so paging and `next` are unchanged."""
    if can_see_own_network(kitchen):
        return query
    target = aliased(Change)
    own_network_ids = select(target.id).where(
        target.household_id == kitchen.household_id, target.kind.in_(OWN_NETWORK_KINDS)
    )
    return query.where(
        Change.kind.not_in(OWN_NETWORK_KINDS),
        ~(
            (Change.kind == "undo")
            & Change.undoes_change_id.is_not(None)
            & Change.undoes_change_id.in_(own_network_ids)
        ),
    )


def hidden(kitchen: Kitchen, change: Change) -> bool:
    """Whether this change is one `leave_out_hidden` leaves out for this caller."""
    if can_see_own_network(kitchen):
        return False
    if change.kind in OWN_NETWORK_KINDS:
        return True
    if change.kind == "undo" and change.undoes_change_id is not None:
        target = kitchen.db.get(Change, change.undoes_change_id)
        return target is not None and target.kind in OWN_NETWORK_KINDS
    return False


# Proposed, for cabledrawer (release security pass beta.3, Low 2; the switch's sentence is the
# lead's brief's).
SWITCH_ON_IN_SETTINGS = "Switch it on in Settings › Outside connections."
ADD_IN_SETTINGS = "Add it again in Settings › Outside connections."


def _cannot_undo(detail: str) -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "cannot_undo", detail)  # proposed, for cabledrawer


def locked_out() -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "locked_out", sso_accounts.LOCKED_OUT)


# --- Recording ----------------------------------------------------------------------------------


def connection_changed(kitchen: Kitchen, connection: Connection, on: bool) -> Change:
    """One switch, turned on or off ("Switched recipe import on"; proposed, for cabledrawer)."""
    return record(
        kitchen,
        "connection_changed",
        f"Switched {LABELS[connection]} {'on' if on else 'off'}",
        None,
        {"connection": {"name": connection.value, "old": not on, "new": on}},
    )


def own_network_added(kitchen: Kitchen, entry: OwnNetworkEntry) -> Change:
    """An entry added (the toast's words, words.md: "Added wiki.home.example to Your own
    network")."""
    return record(
        kitchen,
        "own_network_added",
        f"Added {entry.value} to Your own network",
        None,
        {"entry": {"id": entry.id, "value": entry.value}},
    )


def own_network_removed(kitchen: Kitchen, entry: OwnNetworkEntry) -> Change:
    """An entry taken off ("Removed wiki.home.example from Your own network")."""
    return record(
        kitchen,
        "own_network_removed",
        f"Removed {entry.value} from Your own network",
        None,
        {"entry": {"id": entry.id, "value": entry.value}},
    )


def take_off(kitchen: Kitchen, entry_id: int) -> tuple[OwnNetworkEntry | None, bool]:
    """Take one entry off, under the single sign-on rules (the screen's Remove and the Undo of
    an add): the entry taken off (None when the household has no such entry), and whether that
    turned password sign-in back on. Raises `409 locked_out`, with nothing changed, when it
    would lock this admin out. The caller commits."""
    db, household_id = kitchen.db, kitchen.household_id
    entry = db.get(OwnNetworkEntry, entry_id)
    if entry is None or entry.household_id != household_id:
        return None, False
    was_off = sso_accounts.passwords_off(db, kitchen.data_dir, household_id)
    locks_out = sso_accounts.would_lock_out(db, kitchen.data_dir, kitchen.login)
    own_network.remove(db, household_id, entry_id)
    db.flush()
    if locks_out and not sso_accounts.sso_can_start(db, kitchen.data_dir, household_id):
        # This entry may be what let single sign-on reach the sign-in server: it can't start
        # without it, or can't be told (after a restart the memory of the address is empty).
        raise locked_out()
    # Passwords count as off only while single sign-on can start (`sso_can_start`, with no
    # look-up): if this removal ended that, they work again.
    back_on = was_off and not sso_accounts.passwords_off(db, kitchen.data_dir, household_id)
    return entry, back_on


# --- Undo -----------------------------------------------------------------------------------


def undo(kitchen: Kitchen, change: Change) -> str | None:
    """Put one of these changes back, or refuse (409 `cannot_undo` or `locked_out`) and change
    nothing. Returns the sentence to show instead of "Undone" (passwords work again), if any."""
    data: dict[str, Any] = change.undo_data or {}
    if change.kind == "connection_changed":
        _undo_switch(kitchen, change, data["connection"])
        return None
    if change.kind == "own_network_added":
        return _undo_added(kitchen, data["entry"])
    if change.kind == "own_network_removed":
        _undo_removed(kitchen, data["entry"])
    return None


def _switched_again(kitchen: Kitchen, change: Change, name: str) -> bool:
    """The same switch was changed after this change and that change still stands (on, off,
    on: its Undo is refused too, as `kitchen_changes.made_again`)."""
    later = kitchen.db.scalars(
        select(Change.undo_data).where(
            Change.household_id == kitchen.household_id,
            Change.kind == "connection_changed",
            Change.id > change.id,
            Change.undone_by_change_id.is_(None),
        )
    )
    return any((data or {}).get("connection", {}).get("name") == name for data in later)


def _undo_switch(kitchen: Kitchen, change: Change, data: dict[str, Any]) -> None:
    connection = Connection(data["name"])
    now = switches(kitchen.db, kitchen.household_id)[connection]
    if now != data["new"] or _switched_again(kitchen, change, data["name"]):
        raise _cannot_undo(  # proposed, for cabledrawer
            f"That can’t be undone: {LABELS[connection]} has been switched again."
        )
    if data["old"]:
        # The Undo of "Switched … off" would turn an outside connection on: never by an Undo.
        raise _cannot_undo(SWITCH_ON_IN_SETTINGS)
    # Switching single sign-on off again: the screen's own switch asks the same.
    if (
        connection is Connection.SINGLE_SIGN_ON
        and now
        and sso_accounts.would_lock_out(kitchen.db, kitchen.data_dir, kitchen.login)
    ):
        raise locked_out()
    set_switch(kitchen.db, kitchen.household_id, connection, False)
    kitchen.db.flush()
    log.info("Privacy: %s switched off (Undo) by %s", LABELS[connection], kitchen.login.username)


def _undo_added(kitchen: Kitchen, data: dict[str, Any]) -> str | None:
    entry, back_on = take_off(kitchen, data["id"])
    if entry is None:
        raise _cannot_undo(  # proposed, for cabledrawer
            f"That can’t be undone: {data['value']} is no longer on Your own network."
        )
    log.info("Your own network: removed (Undo) by %s", kitchen.login.username)
    if back_on:
        log.info("Single sign-on: passwords work again, it can't start without that entry")
        return PASSWORDS_BACK_ON_OWN_NETWORK
    return None


def _undo_removed(kitchen: Kitchen, data: dict[str, Any]) -> None:
    """Always refused: putting the entry back would let the app reach that place again (Low 2)."""
    back = kitchen.db.scalar(
        select(OwnNetworkEntry.id).where(
            OwnNetworkEntry.household_id == kitchen.household_id,
            OwnNetworkEntry.value == data["value"],
        )
    )
    if back is not None:  # added again since: the add's own sentence, as before
        raise _cannot_undo(f"That can’t be undone. {own_network.ALREADY}")  # proposed
    raise _cannot_undo(ADD_IN_SETTINGS)
