"""D3 "API names": the API is named one way everywhere (consistency review BE13-BE29)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import db_of
from test_today import ago, ahead, new_recipe

from mealwright.main import create_app
from mealwright.models import BatchCook, MealItem, Tub

API = "/api/v1"


def openapi() -> dict[str, Any]:
    return create_app().openapi()


# --- BE17: list envelopes and paging ---------------------------------------------------------


def test_no_route_answers_a_bare_list() -> None:
    """Every list comes in an object named after what it holds, so a field can be added later
    (paging, a count) without breaking an app."""
    bare = []
    for path, ops in openapi()["paths"].items():
        for method, op in ops.items():
            for code, answer in op.get("responses", {}).items():
                schema = answer.get("content", {}).get("application/json", {}).get("schema", {})
                if code.startswith("2") and schema.get("type") == "array":
                    bare.append(f"{method.upper()} {path}")
    assert bare == []


def test_paged_lists_take_after_and_answer_next() -> None:
    """One cursor name: a paged list takes the `next` of the page before as `after`."""
    old_names = {"before", "more", "cursor", "page", "offset"}
    wrong = [
        f"{method.upper()} {path} ?{param['name']}"
        for path, ops in openapi()["paths"].items()
        for method, op in ops.items()
        for param in op.get("parameters", [])
        if param["in"] == "query" and param["name"] in old_names
    ]
    assert wrong == []


def test_tubs_left_pages_with_after_and_next(kitchen: TestClient) -> None:
    recipe = new_recipe(kitchen, "Paged sambar")
    with db_of(kitchen) as db:
        batch = BatchCook(
            household_id=1,
            recipe_id=recipe,
            recipe_name="Paged sambar",
            cooked_on=ago(kitchen, 1),
            tub_count=3,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for days in (1, 2, 3):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, days)))
        db.commit()
    everything = ok(kitchen.get(f"{API}/plan/tubs-left"))
    assert everything["next"] is None and "more" not in everything
    ids = [t["id"] for t in everything["tubs"]]
    assert len(ids) == 3
    seen: list[int] = []
    after: str | None = None
    for _ in range(3):
        params: dict[str, Any] = {"limit": 2} | ({"after": after} if after else {})
        page = ok(kitchen.get(f"{API}/plan/tubs-left", params=params))
        seen += [t["id"] for t in page["tubs"]]
        after = page["next"]
        if after is None:
            break
    assert seen == ids
    assert kitchen.get(f"{API}/plan/tubs-left", params={"after": "x"}).status_code == 422
    today = ok(kitchen.get(f"{API}/today"))
    assert today["tubs_left_next"] is None and "tubs_left_more" not in today


# --- BE18: the API says "food" ---------------------------------------------------------------


def test_a_planned_ingredient_is_a_food_in_the_api_and_stays_ingredient_in_the_database(
    kitchen: TestClient,
) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Banana"}), 201)["food"]
    slot = ok(kitchen.get(f"{API}/meal-slots"))["meal_slots"][0]["id"]
    day = str(ahead(kitchen, 1))
    old = kitchen.post(f"{API}/plan/items", json={"date": day, "slot_id": slot, "ingredient_id": 1})
    assert old.status_code == 422  # the old name is gone, not quietly read
    ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": day, "slot_id": slot, "food_id": food["id"]}
        ),
        201,
    )
    [meal] = ok(kitchen.get(f"{API}/plan", params={"from": day, "to": day}))["meals"]
    [item] = meal["items"]
    assert item["kind"] == "food" and item["food"]["id"] == food["id"]
    assert "ingredient" not in item
    with db_of(kitchen) as db:
        assert [i.kind for i in db.scalars(select(MealItem))] == ["ingredient"]


def test_the_food_names_in_the_routes() -> None:
    paths = openapi()["paths"]
    assert "/api/v1/recipes/drafts/by-food" in paths
    assert "/api/v1/recipes/drafts/by-food/answer" in paths
    assert not [p for p in paths if "ingredient" in p]


# --- BE28: one resource has one home -------------------------------------------------------


def test_your_data_routes_live_under_your_data_and_the_old_ones_are_gone() -> None:
    paths = openapi()["paths"]
    for old in ("/backups", "/export", "/delete-everything", "/shopping/changes"):
        assert f"{API}{old}" not in paths, old
    assert set(paths[f"{API}/your-data/backups"]) == {"get", "patch", "post"}
    assert set(paths[f"{API}/your-data/export"]) == {"get", "post"}
    assert set(paths[f"{API}/your-data/delete-everything"]) == {"get", "post"}
    assert "get" in paths[f"{API}/shopping/sync"]


def test_the_old_your_data_addresses_answer_404(kitchen: TestClient) -> None:
    for old in ("/backups", "/export", "/delete-everything", "/shopping/changes?since=0"):
        assert kitchen.get(f"{API}{old}").status_code == 404, old
    assert ok(kitchen.get(f"{API}/your-data/backups"))["keep"] >= 1
    assert ok(kitchen.get(f"{API}/shopping/sync", params={"since": 0}))["cursor"] == 0


# --- BE19: day names follow one rule ---------------------------------------------------------

# The rule (proposed, for cabledrawer): a calendar day on its own is `date`; the day an event
# happened or happens is `<event>_on`; a day that names whose it is, or pairs with a `_time`
# field, is `<what>_day` (`{day, time}` is the bare pair); a range is `from`/`to` or
# `start`/`end`; `today` is the household's today; `use_by...` keep the label's own words.
# A moment is `<event>_at` (or `at`); `undo_until` and `server_time` say what they are.
DAY_NAMES_KEPT = {"from", "to", "start", "end", "today", "day"}
MOMENT_NAMES_KEPT = {"at", "undo_until", "server_time"}


def _formatted(schema: dict[str, Any]) -> str | None:
    found = schema.get("format")
    for alt in schema.get("anyOf", []):
        found = found or alt.get("format")
    return found if isinstance(found, str) else None


def _dated_fields() -> list[tuple[str, str, str]]:
    spec = openapi()
    fields = [
        (name, _formatted(prop) or "", schema_name)
        for schema_name, schema in spec["components"]["schemas"].items()
        for name, prop in schema.get("properties", {}).items()
    ]
    fields += [
        (param["name"], _formatted(param.get("schema", {})) or "", f"{method.upper()} {path}")
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
        for param in op.get("parameters", [])
    ]
    return fields


def test_every_day_and_moment_field_follows_the_rule() -> None:
    def day_ok(name: str, where: str) -> bool:
        if name == "day":  # only as the day half of a {day, time} pair
            props = openapi()["components"]["schemas"].get(where, {}).get("properties", {})
            return "time" in props
        return (
            name == "date"
            or name in DAY_NAMES_KEPT
            or name.endswith(("_on", "_day"))
            or name.startswith("use_by")
        )

    wrong = [
        f"{where}.{name}"
        for name, kind, where in _dated_fields()
        if (kind == "date" and not day_ok(name, where))
        or (kind == "date-time" and not (name.endswith("_at") or name in MOMENT_NAMES_KEPT))
    ]
    assert wrong == []


def test_the_renamed_day_fields(kitchen: TestClient) -> None:
    schemas = openapi()["components"]["schemas"]
    assert "released_on" in schemas["UpdatesOut"]["properties"]
    assert "cook_day" in schemas["BatchPreviewOut"]["properties"]
    assert "date" in schemas["SuggestionsOut"]["properties"]
    assert ok(kitchen.get(f"{API}/updates"))["released_on"]


# --- BE27 and CL12: path parameters are named after their noun -------------------------------


def test_path_parameters_are_named_after_their_noun() -> None:
    import re

    paths = openapi()["paths"]
    found = {
        (m.group(1), m.group(2))
        for path in paths
        for m in re.finditer(r"/([a-z-]+)/\{(\w+)\}", path)
    }
    assert ("people", "person_id") in found  # a person, who may have no login (CL12)
    assert ("meal-slots", "meal_slot_id") in found
    assert ("stock", "stock_id") in found
    assert ("sessions", "session_id") in found
    old = {"member_id", "plan_slot_id", "lot_id", "sign_in_id"}
    assert not [pair for pair in found if pair[1] in old]


def test_shopping_ids_in_the_address_are_uuids() -> None:
    paths = openapi()["paths"]
    for path, ops in paths.items():
        if not path.startswith(f"{API}/shopping/"):
            continue
        for op in ops.values():
            for param in op.get("parameters", []):
                if param["in"] == "path" and param["name"] in ("list_id", "item_id"):
                    assert param["schema"].get("pattern", "").startswith("^[0-9a-f]{8}-"), path


# --- BE20: one registry of change kinds ------------------------------------------------------

# Every kind there was before the rule (0.9.5-beta.3). Never add to this list.
BEFORE_D3 = (
    "added",
    "amounts_shown_changed",
    "batch_cook_switch",
    "binned",
    "cook_step_changed",
    "cooked",
    "draft_removed",
    "draft_saved",
    "food_back",
    "food_created",
    "food_edited",
    "food_removed",
    "found",
    "household_renamed",
    "item_added",
    "item_amount",
    "item_deleted",
    "item_moved",
    "item_place",
    "kitchen_changed",
    "list_made",
    "list_removed",
    "list_renamed",
    "mealie_drafts_answered",
    "merged",
    "moved",
    "person_added",
    "person_changed",
    "person_login",
    "person_removed",
    "pints_changed",
    "place_added",
    "place_removed",
    "place_renamed",
    "places_ordered",
    "plan_added",
    "plan_batch",
    "plan_batch_removed",
    "plan_batch_session",
    "plan_batch_session_changed",
    "plan_batch_session_removed",
    "plan_cooked",
    "plan_copied",
    "plan_didnt",
    "plan_eaters",
    "plan_leftovers",
    "plan_method",
    "plan_moved",
    "plan_moveit",
    "plan_optional",
    "plan_removed",
    "plan_servings",
    "plan_slot",
    "plan_start",
    "plan_started",
    "plan_tub",
    "recipe_created",
    "recipe_imported",
    "recipe_removed",
    "recipe_saved",
    "repacked",
    "set_left",
    "setting_kept",
    "shop_added",
    "shop_removed",
    "shop_renamed",
    "shopped",
    "shops_ordered",
    "split",
    "stocktake",
    "tags_merged",
    "to_freezer",
    "undo",
    "use_by",
    "used",
    "whos_this_switch",
)


def _kinds_in_the_code() -> dict[str, str]:
    """Every change kind the code names as a literal: the kind given to `record(...)`, a
    `FoodEdit.record(...)`, `_finish(...)`, `kitchen_changes.ordered(...)`, `.done(...)`, a
    `Change(kind=...)`, and a `change.kind == ...` or `change.kind in (...)` test."""
    import ast
    from pathlib import Path

    import mealwright

    root = Path(mealwright.__file__).parent
    found: dict[str, str] = {}

    def keep(node: ast.AST | None, where: str) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.setdefault(node.value, where)
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                keep(element, where)

    for path in sorted(root.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            where = f"{path.relative_to(root)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Compare):
                left = node.left
                if (
                    isinstance(left, ast.Attribute)
                    and left.attr == "kind"
                    and isinstance(left.value, ast.Name)
                    and left.value.id in ("change", "Change", "earlier")
                ):
                    for right in node.comparators:
                        keep(right, where)
                continue
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            arg: ast.AST | None = None
            if name == "record":
                # history.record(kitchen, kind, ...), or an edit's .record(kind, ...)
                on_edit = isinstance(fn, ast.Attribute) and getattr(fn.value, "id", "") != "history"
                index = 0 if on_edit else 1
                arg = node.args[index] if len(node.args) > index else None
            elif name in ("_finish", "ordered"):
                arg = node.args[1] if len(node.args) > 1 else None
            elif name == "done" and isinstance(fn, ast.Attribute):
                arg = node.args[0] if node.args else None
            elif name != "Change":
                continue
            for keyword in node.keywords:
                if keyword.arg in ("kind", "change_kind"):
                    arg = keyword.value
            keep(arg, where)
    return found


def test_every_change_kind_the_code_names_is_in_the_registry() -> None:
    from mealwright import change_kinds

    found = _kinds_in_the_code()
    assert len(found) > 60  # the scan still finds the kinds
    assert {k: w for k, w in found.items() if k not in change_kinds.ALL} == {}


def test_the_modules_use_the_registry() -> None:
    from mealwright import (
        change_kinds,
        history,
        kitchen_changes,
        mealie_answers,
        people,
        plan,
        recipe_tags,
        removals,
        roles,
        shopping,
    )
    from mealwright.api.v1 import changes

    assert changes.STOCK_KINDS is change_kinds.STOCK
    assert changes.INGREDIENT_KINDS is change_kinds.INGREDIENTS
    assert kitchen_changes.KINDS is change_kinds.SETTINGS
    assert removals.KINDS is change_kinds.REMOVALS
    assert people.KINDS is change_kinds.PEOPLE
    assert history.KEY_ONLY_KINDS is change_kinds.KEY_ONLY
    assert history.NOTE_KINDS is change_kinds.NOTES
    assert shopping.LIST_KINDS is change_kinds.LISTS
    assert {mealie_answers.KIND, recipe_tags.KIND} <= set(change_kinds.RECIPES)
    assert set(plan._KINDS.values()) <= set(change_kinds.PLAN)
    assert set(roles.ADMIN_KINDS) <= change_kinds.ALL


def test_a_new_change_kind_follows_the_rule_and_fits_the_column() -> None:
    """Kinds made before the rule are kept (they are stored, and named by queued Undos); a
    kind added after them is `<thing>_added`, `_changed` or `_removed`, in 20 letters."""
    from mealwright import change_kinds

    new = change_kinds.ALL - set(BEFORE_D3)
    assert [k for k in new if not change_kinds.RULE.match(k)] == []
    too_long = {k for k in change_kinds.ALL if len(k) > change_kinds.LONGEST}
    assert too_long == change_kinds.LONGER_THAN_THE_COLUMN  # no new one; see the module
    assert set(BEFORE_D3) <= change_kinds.ALL  # none is dropped: they are stored


def test_shops_are_recorded_through_kitchen_changes() -> None:
    from pathlib import Path

    from mealwright.api.v1 import kitchen

    source = Path(kitchen.__file__).read_text()
    assert '"shop_added"' not in source and '"shop_renamed"' not in source
    assert "kitchen_changes.shop_added(" in source and "kitchen_changes.shop_renamed(" in source
