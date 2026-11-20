"""CL22: the limits the screens keep (frontend/src/lib/limits.ts) say what the server says."""

import re
from pathlib import Path

from mealwright import auth, page_reader, pasted_recipe
from mealwright.api.v1 import recipe_schemas
from mealwright.step_waits import MAX_WAIT_MINUTES

LIMITS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "limits.ts"


def screen_limits() -> dict[str, int]:
    found = re.findall(r"export const ([A-Z_]+) = ([\d_]+);", LIMITS.read_text(encoding="utf-8"))
    return {name: int(value.replace("_", "")) for name, value in found}


def test_the_screens_limits_are_the_servers() -> None:
    screens = screen_limits()
    assert screens == {
        "MAX_LINES": recipe_schemas.MAX_LINES,
        "MAX_STEPS": recipe_schemas.MAX_STEPS,
        "MAX_TAGS": recipe_schemas.MAX_TAGS,
        "MAX_TAG_CHARS": recipe_schemas.MAX_TAG_CHARS,
        "MAX_MINUTES": MAX_WAIT_MINUTES,
        "MAX_SERVES": page_reader.MAX_SERVES,
        "MIN_PASSWORD": auth.MIN_PASSWORD,
    }


def test_the_server_agrees_with_itself() -> None:
    """The same limit copied into the page reader and the pasted-recipe reader is one number."""
    assert page_reader.MAX_LINES == recipe_schemas.MAX_LINES
    assert page_reader.MAX_STEPS == recipe_schemas.MAX_STEPS
    assert page_reader.MAX_MINUTES == pasted_recipe.MAX_MINUTES == MAX_WAIT_MINUTES
    assert page_reader.MAX_SERVES == pasted_recipe.MAX_SERVES
