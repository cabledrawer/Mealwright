"""The bundled pack-size table (F120, F121; cabledrawer 7 Nov)."""

from __future__ import annotations

import time

import pytest

from mealwright import pack_sizes
from mealwright.pack_sizes import Size, parse_size, suggest_shop_id, suggest_sizes, where_to_buy


def test_table_loads_every_row() -> None:
    table = pack_sizes.table()
    # The spec line: 369 ingredients.
    assert len(table.rows) == 369
    for row in table.rows.values():
        assert row.sizes, row.key
        assert row.where in ("supermarket", "world aisle", "specialist")
        assert row.dates in ("best before", "use by"), row.key


def test_table_is_the_checked_file_unchanged() -> None:
    from importlib.resources import files

    text = (files("mealwright") / "data" / "pack-sizes.csv").read_text(encoding="utf-8")
    assert text.startswith("# Common pack sizes for Mealwright (F120, F121).")


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("500 g", Size("weight", 500_000)),
        ("1.5 kg", Size("weight", 1_500_000)),
        ("250 ml", Size("volume", 250_000)),
        ("1 l", Size("volume", 1_000_000)),
        ("12", Size("count", 12_000)),
    ],
)
def test_parse_size(text: str, size: Size) -> None:
    assert parse_size(text) == size


def test_parse_size_refuses_unknown_units() -> None:
    with pytest.raises(ValueError):
        parse_size("2 cups")


def test_matches_by_name_or_other_name_any_case() -> None:
    plain = [s.amount_milli for s in suggest_sizes(["Plain flour"], "weight")]
    maida = [s.amount_milli for s in suggest_sizes(["My flour", "MAIDA"], "weight")]
    assert plain == maida == [1_500_000, 500_000, 1_000_000]
    assert suggest_sizes(["Ghee"], "weight")[0].pack == "jar"


def test_no_match_gives_the_generic_sizes_by_kind() -> None:
    assert [s.amount_milli for s in suggest_sizes(["Mystery dust"], "weight")] == [
        100_000,
        250_000,
        500_000,
        1_000_000,
    ]
    assert [s.amount_milli for s in suggest_sizes(["Mystery"], "volume")] == [
        250_000,
        500_000,
        1_000_000,
    ]
    assert [s.amount_milli for s in suggest_sizes(["Mystery"], "count")] == [
        1_000,
        2_000,
        6_000,
        12_000,
    ]
    assert all(s.pack is None for s in suggest_sizes(["Mystery"], "count"))


def test_sizes_in_another_kind_are_converted_with_a_known_density() -> None:
    by_weight = suggest_sizes(["Ghee"], "weight")
    by_volume = suggest_sizes(["Ghee"], "volume")
    assert len(by_volume) == len(by_weight)
    # Ghee is lighter than water, so a 500 g jar holds more than 500 ml.
    assert by_volume[0].amount_milli > by_weight[0].amount_milli


def test_a_row_with_no_size_that_fits_gives_the_generic_sizes() -> None:
    row = next(
        r
        for r in pack_sizes.table().rows.values()
        if all(s.counted_as == "count" for s in r.sizes)
        and pack_sizes.conversion_table().rows.get(r.key) is None
        and pack_sizes.conversion_table().match(*r.names) is None
    )
    # Counts are not turned into millilitres: the generic sizes for the kind instead.
    assert [s.amount_milli for s in suggest_sizes([row.names[0]], "volume")] == [
        250_000,
        500_000,
        1_000_000,
    ]


def test_where_to_buy() -> None:
    assert where_to_buy(["Plain flour"]) == "supermarket"
    assert where_to_buy(["Asafoetida"]) == "specialist"
    assert where_to_buy(["Mystery"]) is None


SHOPS = [(1, "Tesco"), (2, "Market stall"), (3, "Indian grocer")]
CUISINE_SHOPS = [
    (1, "Tesco"),
    (2, "Sri Lankan corner"),
    (3, "Oriental Market"),
    (4, "Persian deli"),
    (5, "Tokyo Japanese Foods"),
    (6, "Beijing Chinese Mart"),
]


def test_specialist_goes_to_the_first_shop_matching_its_cuisine() -> None:
    assert suggest_shop_id("specialist", CUISINE_SHOPS, "indian") == 2
    assert suggest_shop_id("specialist", CUISINE_SHOPS, "chinese") == 3  # oriental, first
    assert suggest_shop_id("specialist", CUISINE_SHOPS[3:], "chinese") == 6
    assert suggest_shop_id("specialist", CUISINE_SHOPS, "japanese") == 3  # oriental, first
    assert suggest_shop_id("specialist", CUISINE_SHOPS[3:], "japanese") == 5
    assert suggest_shop_id("specialist", CUISINE_SHOPS, "middle eastern") == 4
    assert suggest_shop_id("specialist", [(1, "Halal Butcher"), *SHOPS], "middle eastern") == 1
    assert suggest_shop_id("specialist", [(1, "Desi Mart"), *SHOPS], "indian") == 1
    assert (
        suggest_shop_id("specialist", [(1, "Greek Mediterranean"), *SHOPS], "middle eastern") == 1
    )


def test_specialist_ignores_shops_of_another_cuisine() -> None:
    # A Chinese ingredient does not go to the Indian grocer when another shop isn't a supermarket.
    assert suggest_shop_id("specialist", SHOPS, "chinese") == 2
    assert suggest_shop_id("specialist", [(4, "Middle Eastern shop"), *SHOPS], "indian") == 3


def test_specialist_without_a_match_goes_to_the_first_shop_not_a_supermarket() -> None:
    assert suggest_shop_id("specialist", SHOPS[:2], "indian") == 2
    assert suggest_shop_id("specialist", SHOPS[:2]) == 2  # no cuisine
    assert suggest_shop_id("specialist", [(1, "Tesco"), (5, "Lidl")], "indian") is None


def test_supermarket_and_world_aisle_go_to_the_first_shop() -> None:
    assert suggest_shop_id("supermarket", SHOPS[::-1]) == 3
    assert suggest_shop_id("world aisle", SHOPS) == 1
    assert suggest_shop_id(None, SHOPS) is None
    assert suggest_shop_id("supermarket", []) is None


def test_world_aisle_and_supermarket_with_a_cuisine_go_to_a_matching_shop() -> None:
    # cabledrawer 7 Nov: basmati rice (world aisle, Indian) goes to the Indian grocer.
    assert suggest_shop_id("world aisle", SHOPS, "indian") == 3
    assert suggest_shop_id("supermarket", CUISINE_SHOPS, "japanese") == 3
    # No matching shop: still the first shop, not the specialist fallback.
    assert suggest_shop_id("world aisle", SHOPS, "middle eastern") == 1
    assert suggest_shop_id("supermarket", [(1, "Tesco"), (5, "Lidl")], "indian") == 1


def test_basmati_rice_is_suggested_the_indian_grocer() -> None:
    assert pack_sizes.usual_shop_id(["basmati rice"], SHOPS) == 3
    assert pack_sizes.usual_shop_id(["plain flour"], SHOPS) == 1


def test_cuisine_words_match_whole_words_only() -> None:
    # "Persiana" isn't "Persian"; "Desired" isn't "Desi".
    assert (
        suggest_shop_id("specialist", [(2, "Persiana"), (3, "Persian deli")], "middle eastern") == 3
    )
    assert suggest_shop_id("specialist", [(2, "Desired"), (3, "Desi shop")], "indian") == 3


def test_the_table_gives_each_row_its_cuisine() -> None:
    rows = pack_sizes.table().rows
    assert rows["chapati_flour"].cuisine == "indian"
    assert rows["plain_flour"].cuisine == ""
    assert {r.cuisine for r in rows.values()} == {
        "",
        "indian",
        "chinese",
        "japanese",
        "middle eastern",
    }
    assert all(r.cuisine for r in rows.values() if r.where == "specialist")


def test_usual_shop_id_by_the_table() -> None:
    assert pack_sizes.usual_shop_id(["Plain flour"], CUISINE_SHOPS) == 1
    assert pack_sizes.usual_shop_id(["Asafoetida"], CUISINE_SHOPS) == 2
    assert pack_sizes.usual_shop_id(["Mystery"], CUISINE_SHOPS) is None


def test_matching_is_quick() -> None:
    start = time.perf_counter()
    for _ in range(1000):
        suggest_sizes(["Basmati rice", "rice"], "weight")
    assert time.perf_counter() - start < 1.0


def grams(found: list[pack_sizes.Suggestion]) -> list[int]:
    return [s.amount_milli // 1000 for s in found]


def test_f183_nothing_odd_for_sugar_cumin_and_coconut_milk() -> None:
    # cabledrawer's hand test: Sugar 592 ml / 1.183 L / 2.367 L, Ground cumin 246 ml / 985 ml,
    # Coconut milk 382 g / 158 g. Each is now a size a shop sells.
    assert grams(suggest_sizes(["Sugar"], "volume")) == [1200, 600, 2250]
    assert grams(suggest_sizes(["Ground cumin"], "volume", "cumin_seeds")) == [250, 1000]
    assert grams(suggest_sizes(["Coconut milk"], "weight")) == [400, 150]


def test_f183_counts_stay_counts_and_are_never_turned_into_grams() -> None:
    # Garlic 3 g / 12 g and Bananas 118 g / 590 g / 708 g are gone: the generic weights.
    assert grams(suggest_sizes(["Garlic"], "weight")) == [100, 250, 500, 1000]
    assert grams(suggest_sizes(["Bananas"], "weight")) == [100, 250, 500, 1000]
    # Counted as a count, they keep the table's own counts.
    assert grams(suggest_sizes(["Bananas"], "count")) == [1, 5, 6]


@pytest.mark.parametrize(
    ("milli", "shop"),
    [
        (592_000, 600_000),
        (1_183_000, 1_200_000),
        (246_000, 250_000),
        (382_000, 400_000),
        (62_500, 65_000),  # half way: up, as every amount (D4, BE22)
        (3_000, 5_000),
        (12_300, 10_000),
    ],
)
def test_shop_size_rounds_to_a_size_a_shop_sells(milli: int, shop: int) -> None:
    assert pack_sizes.shop_size(milli) == shop
