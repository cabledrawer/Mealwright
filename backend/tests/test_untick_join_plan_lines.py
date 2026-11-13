"""L2 (whole-0.9 review): an untick that joins two plan-made lines leaves the one line plan-made,
so the list keeps following the plan (a later meal is bought for)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import changes, counter, one
from test_recipe_list import line
from test_recipes import food as new_food
from test_shop_from_plan import plan, plan_lines, recipe


def shown(kitchen: TestClient) -> list[tuple[Any, bool, bool]]:
    return sorted(
        (r["amount"], any(t["standing"] for t in r["ticks"]), r["hand_edited"])
        for r in changes(kitchen)["items"]
        if not r.get("deleted") and not r.get("merged_into_id")
    )


def test_an_untick_beside_the_plans_own_line_keeps_following_the_plan(
    kitchen: TestClient,
) -> None:
    rice = new_food(kitchen, "Plan rice")
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    done = one(kitchen, "tick", counter(kitchen), item_id=item)
    plan(kitchen, sambar, 2)
    plan(kitchen, sambar, 3)
    one(kitchen, "untick", counter(kitchen), item_id=item, tick_ids=[done["id"]])
    assert shown(kitchen) == [(600, False, False)]
    plan(kitchen, sambar, 4)  # a fourth meal: 800 g needed, nothing in the pantry
    assert shown(kitchen) == [(800, False, False)]
