"""Who may do what: the one place that says which actions need an Admin (0.9 A1; the roles table
cabledrawer's 0.6 review asked for, "written before Settings is built").

There are two roles only, Admin and Member (spec section 3, cabledrawer 17 Oct). Members cook, plan
and shop, and change anything in the kitchen; admins also change the people of the household and
the household-wide settings below. Every admin check in the API goes through `allowed()`, by
naming one of these actions, and `tests/test_roles.py` tries each admin route as a Member.
"""

from enum import StrEnum

ADMIN = "admin"
MEMBER = "member"
ROLES = (ADMIN, MEMBER)


class Action(StrEnum):
    """What can be asked of `allowed()`. Each needs an Admin unless `MEMBERS_MAY` lists it."""

    # Settings → Household: add, change or remove a person, give a login, change a role, and
    # the "Who's this?" switch.
    PEOPLE = "people"
    # Household-wide settings: the pint, Batch cook shown or hidden, meal slots, and the
    # household's time zone and cup size from the browser.
    HOUSEHOLD_SETTINGS = "household_settings"
    # Settings → Privacy: every outside-connection switch and "Your own network".
    PRIVACY = "privacy"
    # Settings → Sign-in (single sign-on, password sign-in, API tokens; from 0.9).
    SIGN_IN = "sign_in"
    # Settings → Your data: how often and how many backups, Back up now, Export everything and
    # Delete everything (0.9 D1).
    YOUR_DATA = "your_data"
    # Cook mode's ingredients for each step: any person of the household (cabledrawer 1 Nov).
    COOK_PER_STEP = "cook_per_step"


# The whole table: each action and the roles that may do it.
TABLE: dict[Action, frozenset[str]] = {
    Action.PEOPLE: frozenset({ADMIN}),
    Action.HOUSEHOLD_SETTINGS: frozenset({ADMIN}),
    Action.PRIVACY: frozenset({ADMIN}),
    Action.SIGN_IN: frozenset({ADMIN}),
    Action.YOUR_DATA: frozenset({ADMIN}),
    Action.COOK_PER_STEP: frozenset({ADMIN, MEMBER}),
}

# Recent changes that only an admin can undo, because only an admin can make them, and the action
# each one is.
ADMIN_KINDS: dict[str, Action] = {
    "plan_slot": Action.HOUSEHOLD_SETTINGS,
    "batch_cook_switch": Action.HOUSEHOLD_SETTINGS,
    "pints_changed": Action.HOUSEHOLD_SETTINGS,
    "household_renamed": Action.HOUSEHOLD_SETTINGS,
    "amounts_shown_changed": Action.HOUSEHOLD_SETTINGS,
    "person_added": Action.PEOPLE,
    "person_changed": Action.PEOPLE,
    "person_removed": Action.PEOPLE,
    "whos_this_switch": Action.PEOPLE,
}
ADMIN_ONLY_KINDS = tuple(ADMIN_KINDS)


def allowed(role: str, action: Action) -> bool:
    """True when a login with this role may do this. An unknown role may do nothing."""
    return role in TABLE[action]


def admin_actions() -> list[Action]:
    """The actions only an admin may do (for Settings, and for the tests)."""
    return [action for action, roles in TABLE.items() if MEMBER not in roles]


def admin_kind_action(kind: str) -> Action:
    """The action a Recent changes kind in `ADMIN_KINDS` is (to undo it is to do it again)."""
    return ADMIN_KINDS[kind]


def can_undo_kind(role: str, kind: str) -> bool:
    """False when only an admin may undo this kind of change and this role isn't one."""
    return kind not in ADMIN_KINDS or allowed(role, ADMIN_KINDS[kind])
