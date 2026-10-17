"""The bundled USDA table and the conversion maths."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mealwright.conversions import (
    AskOnce,
    Known,
    UnitAmount,
    convert_milli,
    suggestion,
    table,
    to_base_milli,
)
from mealwright.names import normalise


def test_table_loads_with_unique_names() -> None:
    rows = table().rows
    assert 200 <= len(rows) <= 250
    seen: dict[str, str] = {}
    for row in rows.values():
        assert row.mg_per_ml or row.item_weight_mg, row.key
        for name in row.names:
            key = normalise(name)
            assert seen.setdefault(key, row.key) == row.key, name


def test_table_values_come_from_usda() -> None:
    # Plain flour: USDA 168894, 1 cup = 125 g; 1 US cup = 236.588 ml.
    flour = table().match("Plain flour")
    assert flour is not None and flour.mg_per_ml == round(125_000 / 236.5882365)
    # Eggs: USDA 171287, 1 large = 50 g.
    eggs = table().match("Eggs")
    assert eggs is not None and eggs.item_weight_mg == 50_000 and eggs.counted_as == "count"


def test_table_matching() -> None:
    assert table().match("Basmati Rice") is not None
    assert table().match("toor dal") is None  # not in USDA: asked once instead
    assert table().match("toor dal", "arhar dal", "rice") == table().rows["long_grain_rice"]
    close = table().close("Organic basmati rice")
    assert close is not None and close.key == "long_grain_rice"


def test_suggestions() -> None:
    assert suggestion("weight_per_ml", None, 250) == Decimal(200)
    assert suggestion("item_weight", None, 250) == Decimal(100)
    flour = table().rows["plain_flour"]
    assert suggestion("weight_per_ml", flour, 240) == Decimal(130)  # 126.8 g, 2 sig figs


TOOR = Known(mg_per_ml=800, item_mg=None)
ONION = Known(mg_per_ml=None, item_mg=150_000)


def test_same_family_needs_nothing() -> None:
    nothing = Known(None, None)
    assert to_base_milli(UnitAmount(Decimal(1), "kg"), "weight", nothing, 250) == 1_000_000
    assert to_base_milli(UnitAmount(Decimal(2), "tbsp"), "volume", nothing, 250) == 30_000
    assert to_base_milli(UnitAmount(Decimal(1), "cup"), "volume", nothing, 240) == 240_000


def test_volume_to_weight() -> None:
    assert to_base_milli(UnitAmount(Decimal(1), "cup"), "weight", TOOR, 250) == 200_000
    with pytest.raises(AskOnce) as asked:
        to_base_milli(UnitAmount(Decimal(1), "cup"), "weight", Known(None, None), 250)
    assert asked.value.kind == "weight_per_ml"


def test_count_and_weight() -> None:
    assert to_base_milli(UnitAmount(Decimal(300), "g"), "count", ONION, 250) == 2_000
    assert to_base_milli(UnitAmount(Decimal(2), "count"), "weight", ONION, 250) == 300_000
    with pytest.raises(AskOnce) as asked:
        to_base_milli(UnitAmount(Decimal(1), "cup"), "count", ONION, 250)
    assert asked.value.kind == "weight_per_ml"


@given(
    st.integers(min_value=1, max_value=10**9),
    st.integers(min_value=100, max_value=3_000),
    st.integers(min_value=1_000, max_value=2_000_000),
)
def test_conversions_round_trip(milli: int, mg_per_ml: int, item_mg: int) -> None:
    """weight → volume → weight and weight → count → weight come back within rounding."""
    known = Known(mg_per_ml, item_mg)
    for other in ("volume", "count"):
        there = convert_milli(milli, "weight", other, known, 250)  # type: ignore[arg-type]
        back = convert_milli(there, other, "weight", known, 250)  # type: ignore[arg-type]
        factor = mg_per_ml if other == "volume" else item_mg
        # One thousandth of the other unit, in grams-thousandths, plus rounding.
        assert abs(back - milli) <= factor / 1000 + 1
