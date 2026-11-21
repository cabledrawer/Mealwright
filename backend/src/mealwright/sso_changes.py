"""Single sign-on in Recent changes: the sign-in server's usernames are for admins (release
security pass beta.3; proposed, for cabledrawer).

A link, a new linked person, a refusal and an unlink (Settings › People, `sso_people.py`) and an
automatic link at a first sign-in (`sso_accounts._note_auto_link`) are `person_login` changes
whose summary names the account's username at the sign-in server: "Linked Asha to asha.k at your
sign-in server". The sign-in server's usernames are on Settings › People for an admin only (the
People list leaves `sso_username` out for everyone else), so the same goes for Recent changes: an
admin signed in on a device reads the summary as it is; a member and every API token (an
admin's too, as for Settings › People) read the same sentence without the username, "Linked Asha
to your sign-in server". The change keeps that sentence beside the summary (`undo_data`, which a
`person_login` change has no other use for and which no answer carries); a change made before
this has its username cut out by its pattern instead.

Recent changes is the one place a summary is read (`foods.change_out`: the list, an Undo's and a
retry's answer, the shopping sync's results). The live updates carry only numbers.
"""

import re
from typing import Any

from mealwright import change_kinds
from mealwright.api.v1.context import Kitchen
from mealwright.models import Change
from mealwright.roles import Action

KEY = "for_everyone"

# Proposed, for cabledrawer: the admin's sentences (words.md, Pe3/M2) without the username.
LINKED = "Linked {name} to your sign-in server"
ADDED = "Added {name}, linked to your sign-in server"
REFUSED = "Refused a sign-in at your sign-in server"
UNLINKED = "Unlinked {name} from your sign-in server"
AUTOMATICALLY = ", automatically"
# Only for a change whose summary has none of the patterns below (never made by this version).
SOME_CHANGE = "Changed a sign-in at your sign-in server"

# The other `person_login` changes name no account: "Made a sign-in link for Asha".
_NO_ACCOUNT = ("Made a ",)

# A name runs to the first " to " (", linked to ", " from "): a name with those words in it is
# cut short, never an account's username shown.
_PATTERNS = (
    (re.compile(r"Linked (.+?) to "), LINKED),
    (re.compile(r"Added (.+?), linked to "), ADDED),
    (re.compile(r"Unlinked (.+?) from "), UNLINKED),
)


def for_everyone(sentence: str) -> dict[str, Any]:
    """The `undo_data` of a change that names an account: the sentence a non-admin reads."""
    return {KEY: sentence}


def _without_username(summary: str) -> str:
    for pattern, sentence in _PATTERNS:
        found = pattern.match(summary)
        if found:
            said = sentence.format(name=found.group(1))
            return said + AUTOMATICALLY if summary.endswith(AUTOMATICALLY) else said
    if summary.startswith("Refused "):
        return REFUSED
    return SOME_CHANGE


def summary(kitchen: Kitchen, change: Change) -> str:
    """The summary this caller reads (see the module's notes)."""
    if change.kind != change_kinds.PERSON_LOGIN or kitchen.may(Action.PEOPLE):
        return change.summary
    kept = (change.undo_data or {}).get(KEY)
    if isinstance(kept, str):
        return kept
    if change.summary.startswith(_NO_ACCOUNT):
        return change.summary
    return _without_username(change.summary)
