"""Every kind of change Mealwright keeps (`change.kind`), in one place (D3, BE20).

A change's `kind` is stored in the database and shown in the API (Recent changes, Undo), so a
kind is never renamed: a queued Undo, an old backup and an app built against an earlier version
all still name it. The modules that make each family use the tuples below.

The rule for a NEW kind (proposed, for cabledrawer): `<thing>_added`, `<thing>_changed` or
`<thing>_removed`, in at most 20 letters (the column's size). The kinds made before 0.9.5-beta.3
follow older patterns (bare stock verbs such as `used`, `food_created`, `list_made`,
`item_deleted`) and are kept as they are; `tests/test_api_names.py` lists them and holds every
kind added after them to the rule.
"""

import re

# Stock in the Pantry (Pantry → Recent changes): bare verbs, as the screen says them.
STOCK = (
    "added",
    "used",
    "binned",
    "set_left",
    "moved",
    "to_freezer",
    "use_by",
    "shopped",
    "found",
    "repacked",
    "cooked",
    "stocktake",
)

# Ingredients (Ingredients → Recent changes).
INGREDIENTS = (
    "food_created",
    "food_edited",
    "food_removed",
    "food_back",
    "merged",
    "split",
    "recipe_imported",
)

# Recipes and drafts.
RECIPES = ("recipe_removed", "draft_removed", "mealie_drafts_answered", "tags_merged")

# Only remember a request's Idempotency-Key: nothing to undo, not listed.
KEY_ONLY = ("recipe_created", "recipe_saved", "draft_saved", "setting_kept")

# Only there to be read, with no Undo of their own.
NOTES = ("food_back", "person_login")

# Shopping lists and their lines.
LISTS = (
    "list_made",
    "list_renamed",
    "list_removed",
    "item_added",
    "item_amount",
    "item_deleted",
    "item_place",
    "item_moved",
)

# The plan and batch cooking.
PLAN = (
    "plan_added",
    "plan_removed",
    "plan_moved",
    "plan_copied",
    "plan_leftovers",
    "plan_moveit",
    "plan_servings",
    "plan_optional",
    "plan_method",
    "plan_eaters",
    "plan_start",
    "plan_started",
    "plan_cooked",
    "plan_didnt",
    "plan_tub",
    "plan_slot",
    "plan_batch",
    "plan_batch_removed",
    "plan_batch_session",
    "plan_batch_session_changed",
    "plan_batch_session_removed",
)

# Household settings with an Undo (`kitchen_changes.py`).
SETTINGS = (
    "place_added",
    "place_renamed",
    "shops_ordered",
    "places_ordered",
    "kitchen_changed",
    "batch_cook_switch",
    "pints_changed",
    "cook_step_changed",
    "household_renamed",
    "amounts_shown_changed",
)

# Shops and places whose Undo lives in `removals.py`. A shop added or renamed is recorded by
# `kitchen_changes.py`, as a place is.
REMOVALS = ("shop_removed", "place_removed", "shop_added", "shop_renamed")

# Settings › Outside connections (admins only; `privacy_changes.py`; D4, BE5, cabledrawer 20 Nov).
PRIVACY = ("connection_changed", "own_network_added", "own_network_removed")

# People (admins only).
PEOPLE = ("person_added", "person_changed", "person_removed", "whos_this_switch")
PERSON_LOGIN = "person_login"

# An Undo of any change.
UNDO = "undo"

ALL: frozenset[str] = frozenset(
    (
        *STOCK,
        *INGREDIENTS,
        *RECIPES,
        *KEY_ONLY,
        *NOTES,
        *LISTS,
        *PLAN,
        *SETTINGS,
        *REMOVALS,
        *PRIVACY,
        *PEOPLE,
        PERSON_LOGIN,
        UNDO,
    )
)

RULE = re.compile(r"^[a-z]+(?:_[a-z]+)*_(?:added|changed|removed)$")

# `change.kind` is `String(20)`. SQLite does not hold a value to its size, so these four longer
# kinds are stored whole today; Postgres would refuse them. Widening the column is a migration,
# left for its own PR (reported to the lead in D3). No new kind may be longer.
LONGEST = 20
LONGER_THAN_THE_COLUMN = frozenset(
    {
        "amounts_shown_changed",
        "mealie_drafts_answered",
        "plan_batch_session_changed",
        "plan_batch_session_removed",
    }
)
