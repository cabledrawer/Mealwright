"""One rounding for amounts (0.9.5-beta.3, D4, BE22).

Every amount is rounded half away from zero by `amounts.round_half_up` (as `to_milli`), never
by Python's round(), which rounds a half to the even number: 2.5 g would be 2 g on one screen
and 3 g on another.
"""

import ast
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from mealwright.amounts import round_half_up, to_milli
from mealwright.pack_sizes import shop_size

SOURCES = Path(__file__).resolve().parents[1] / "src" / "mealwright"

# The round() calls that are not amounts, with why.
NOT_AMOUNTS = {
    "pasted_recipe.py": "minutes of a recipe's times",
    "recipe_import.py": "a pint's millilitres, to three places, for the reading",
    "step_waits.py": "minutes of a step's wait",
    "step_timings.py": "minutes of a step",
    "photos.py": "a photo's width and height in pixels",
}


@pytest.mark.parametrize(
    ("value", "whole"),
    [
        (Decimal("2.5"), 3),
        (Decimal("-2.5"), -3),
        (Decimal("2.4999"), 2),
        (Fraction(5, 2), 3),
        (Fraction(-5, 2), -3),
        (Fraction(7, 3), 2),
        (0.5, 1),
        (2.675, 3),
        (4, 4),
    ],
)
def test_a_half_goes_up(value: Decimal | Fraction | float | int, whole: int) -> None:
    assert round_half_up(value) == whole


def test_it_agrees_with_to_milli() -> None:
    for text in ("0.0005", "1.0025", "2.5", "0.0015"):
        assert round_half_up(Decimal(text) * 1000) == to_milli(text)


def test_a_shop_size_on_the_half_goes_up() -> None:
    # 112.5 g is half way between 100 and 125 in steps of 25: up, as on every screen.
    assert shop_size(112_500) == 125_000
    assert shop_size(87_500) == 90_000  # 17.5 steps of 5


def test_no_bare_round_on_an_amount() -> None:
    found = []
    for path in sorted(SOURCES.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "round"
                and path.name not in NOT_AMOUNTS
            ):
                found.append(f"{path.relative_to(SOURCES)}:{node.lineno}")
    assert found == []
    for name, why in NOT_AMOUNTS.items():
        assert why and (SOURCES / name).exists(), name
