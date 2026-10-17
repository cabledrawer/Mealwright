"""Unit maths: storing amounts, rounding and showing them the way they're sold."""

import re
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mealwright.amounts import (
    MILLI,
    Size,
    about_text,
    as_sold,
    count_text,
    exact_text,
    from_milli,
    plural,
    quarters_text,
    significant,
    to_milli,
)
from mealwright.names import normalise

PACKET = Size(12, "packet", "packets", 500_000)
PACK = Size(30, "pack", "packs", 200_000)
BOTTLE = Size(5, "bottle", "bottles", 1_000_000)
DOZEN = Size(7, "dozen", "dozen", 12_000)
LOAF = Size(8, "loaf", "loaves", 20_000)
TUB = Size(9, "tub", "tubs", 500_000)


@pytest.mark.parametrize(
    ("milli", "counted_as", "size", "word", "expected"),
    [
        # The examples in docs/dev/api-0.2.md section 5.3 and the mockups.
        (750_000, "weight", PACKET, None, "1½\u00a0packets · about 750\u00a0g"),
        (1_000_000, "weight", PACKET, None, "2\u00a0packets · 1\u00a0kg"),
        (400_000, "weight", PACK, None, "2\u00a0packs · 400\u00a0g"),
        (1_500_000, "volume", BOTTLE, None, "1½\u00a0bottles · about 1.5\u00a0L"),
        (9_000, "count", DOZEN, None, "9\u00a0left · bought as a dozen"),
        (14_000, "count", LOAF, "slice", "14\u00a0slices · bought as a loaf"),
        (6_000, "count", None, "piece", "6\u00a0pieces"),
        (200_000, "weight", None, None, "200\u00a0g"),
        (40_000, "weight", PACKET, None, "under ¼\u00a0packet · about 40\u00a0g"),
        (250_000, "weight", TUB, None, "½\u00a0tub · about 250\u00a0g"),
        (500_000, "weight", TUB, None, "1\u00a0tub · 500\u00a0g"),
        (125_000, "weight", PACKET, None, "¼\u00a0packet · about 130\u00a0g"),
        (1_000, "count", None, "slice", "1\u00a0slice"),
        (500, "count", None, "slice", "½\u00a0slice"),
        (1_500, "count", None, None, "1½\u00a0left"),
        (0, "count", None, None, "0\u00a0left"),
        (0, "weight", PACKET, None, "0\u00a0g"),
        (200, "count", None, None, "under ½\u00a0left"),
        (240, "count", None, "egg", "under ½\u00a0egg"),
        (4, "weight", None, None, "under 0.1\u00a0g"),
        (49, "volume", None, None, "under 0.1\u00a0ml"),
        (50, "weight", None, None, "0.1\u00a0g"),
    ],
)
def test_as_sold_display(
    milli: int, counted_as: str, size: Size | None, word: str | None, expected: str
) -> None:
    word_plural = plural(word) if word else None
    shown = as_sold(milli, counted_as, size, word, word_plural)  # type: ignore[arg-type]
    assert shown.display == expected


def test_as_sold_parts() -> None:
    shown = as_sold(750_000, "weight", PACKET)
    assert shown.count == Decimal("1.5")
    assert shown.about is True
    assert shown.short == "1½\u00a0packets"
    exact = as_sold(1_000_000, "weight", PACKET)
    assert exact.about is False
    assert exact.short == "2\u00a0packets"


@pytest.mark.parametrize(
    ("milli", "expected"),
    [
        (200_000, "200\u00a0g"),
        (7_500, "7.5\u00a0g"),
        (7_000, "7\u00a0g"),
        (1_000_000, "1\u00a0kg"),
        (1_250_000, "1.25\u00a0kg"),
        (1_234_400, "1.234\u00a0kg"),
        (999_600, "1\u00a0kg"),
        (12_499, "12\u00a0g"),
        (12_500, "13\u00a0g"),
    ],
)
def test_exact_text(milli: int, expected: str) -> None:
    assert exact_text(milli, "weight") == expected


@pytest.mark.parametrize(
    ("milli", "counted_as", "expected"),
    [
        (750_000, "weight", "about 750\u00a0g"),
        (1_490_000, "weight", "about 1.5\u00a0kg"),
        (1_500_000, "volume", "about 1.5\u00a0L"),
        (7_340, "weight", "about 7.3\u00a0g"),
        (256, "weight", "about 0.26\u00a0g"),
        (995_000, "weight", "about 1\u00a0kg"),
        (45_000, "volume", "about 45\u00a0ml"),
    ],
)
def test_about_text(milli: int, counted_as: str, expected: str) -> None:
    assert about_text(milli, counted_as) == expected  # type: ignore[arg-type]


def test_quarters_and_halves() -> None:
    assert [quarters_text(q) for q in range(9)] == [
        "0", "¼", "½", "¾", "1", "1¼", "1½", "1¾", "2",
    ]  # fmt: skip
    assert count_text(1_249, None, None) == "1\u00a0left"  # 1.249 → nearest ½ is 1
    assert count_text(1_250, None, None) == "1½\u00a0left"  # halfway rounds up
    assert count_text(2_000, "onion", None) == "2\u00a0onions"


def test_plurals() -> None:
    assert plural("packet") == "packets"
    assert plural("loaf") == "loaves"
    assert plural("dozen") == "dozen"
    assert plural("bunch") == "bunches"
    assert plural("berry") == "berries"
    assert plural("tray") == "trays"
    assert plural("big bag") == "big bags"


def test_significant_figures() -> None:
    assert significant(Decimal(1490)) == Decimal(1500)
    assert significant(Decimal("7.34")) == Decimal("7.3")
    assert significant(Decimal(0)) == 0


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Drumsticks (moringa)", "drumstick"),
        ("Tomatoes", "tomato"),
        ("Self-raising flour", "self raising flour"),
        ("Confectioners' sugar", "confectioner sugar"),
        ("Jalapeño", "jalapeno"),
        ("Strawberries", "strawberry"),
        ("Dates", "date"),
        ("  Toor   Dal ", "toor dal"),
        ("Glass", "glass"),
    ],
)
def test_normalise(name: str, key: str) -> None:
    assert normalise(name) == key


# --- Properties (Hypothesis) ------------------------------------------------------------------

amounts_milli = st.integers(min_value=0, max_value=10**12)
sizes_milli = st.integers(min_value=1, max_value=10**9)


@given(st.decimals(min_value=0, max_value=10**9, places=3, allow_nan=False))
def test_milli_round_trip(value: Decimal) -> None:
    assert Decimal(str(from_milli(to_milli(value)))) == value


@given(amounts_milli, sizes_milli)
def test_as_sold_is_within_an_eighth(milli: int, size_milli: int) -> None:
    """Rounded to the nearest ¼: never more than ⅛ of a size away from the truth."""
    shown = as_sold(milli, "weight", Size(1, "packet", "packets", size_milli))
    if shown.count is None:  # nothing left
        assert milli == 0
        return
    truth = Decimal(milli) / size_milli
    assert abs(shown.count - truth) <= Decimal("0.125")
    assert (shown.count * 4) % 1 == 0
    assert shown.about == (milli % size_milli != 0)


@given(st.integers(min_value=0, max_value=10**9))
def test_counts_round_to_halves(milli: int) -> None:
    shown = as_sold(milli, "count")
    assert shown.count is not None
    assert (shown.count * 2) % 1 == 0
    assert abs(shown.count - Decimal(milli) / MILLI) <= Decimal("0.25")


@given(st.integers(min_value=1, max_value=10**12))
def test_about_is_two_significant_figures(milli: int) -> None:
    value = Decimal(milli) / MILLI
    rounded = significant(value)
    assert abs(rounded - value) <= abs(value) * Decimal("0.05")
    digits = rounded.normalize().as_tuple().digits
    assert len(digits) <= 2 or all(d == 0 for d in digits[2:])


@given(
    st.integers(min_value=1, max_value=10**12),
    st.sampled_from(["weight", "volume", "count"]),
    st.one_of(st.none(), sizes_milli),
    st.sampled_from([None, "egg"]),
)
def test_some_never_shows_as_nothing(
    milli: int, counted_as: str, size_milli: int | None, word: str | None
) -> None:
    """A non-zero amount never reads as zero ("0 g", "0 left", "0 eggs")."""
    size = Size(1, "packet", "packets", size_milli) if size_milli else None
    shown = as_sold(milli, counted_as, size, word, None)  # type: ignore[arg-type]
    for text in (shown.short, *shown.display.split(" · ")):
        assert not text.startswith(("0 ", "0\u00a0")), shown.display
        assert "about 0\u00a0" not in text, shown.display


NUMBER_THEN_WORD = re.compile(r"[0-9½¼¾] [A-Za-z]")


@given(
    st.integers(min_value=0, max_value=10**12),
    st.sampled_from(["weight", "volume", "count"]),
    st.one_of(st.none(), sizes_milli),
    st.sampled_from([None, "slice"]),
)
def test_numbers_never_wrap_away_from_their_units(
    milli: int, counted_as: str, size_milli: int | None, word: str | None
) -> None:
    """A no-break space between a number and its unit ("750 g", "1½ packets"), so a
    narrow column never shows "750 / g"; normal spaces around " · " so it wraps there."""
    size = Size(1, "packet", "packets", size_milli) if size_milli else None
    shown = as_sold(milli, counted_as, size, word, None)  # type: ignore[arg-type]
    for text in (shown.display, shown.short):
        assert not NUMBER_THEN_WORD.search(text), text
    if " · " in shown.display or "\u00a0·" in shown.display:
        assert "\u00a0·" not in shown.display and "·\u00a0" not in shown.display


def test_no_break_space_examples() -> None:
    assert as_sold(750_000, "weight", PACKET).display == "1½\u00a0packets · about 750\u00a0g"
    assert as_sold(9_000, "count", DOZEN).display == "9\u00a0left · bought as a dozen"
    assert exact_text(1_250_000, "volume") == "1.25\u00a0L"
