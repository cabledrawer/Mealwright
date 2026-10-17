"""Taking stock: oldest first, freezer last, never below zero (Hypothesis)."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from mealwright.stock import LotView, add_months, plan_take, use_order

START = datetime(2026, 1, 1, tzinfo=UTC)

lot_views = st.lists(
    st.builds(
        LotView,
        id=st.integers(min_value=1, max_value=10**6),
        amount=st.integers(min_value=0, max_value=10**9),
        use_by=st.one_of(st.none(), st.dates(date(2026, 1, 1), date(2027, 12, 31))),
        added_at=st.integers(min_value=0, max_value=10**6).map(
            lambda s: START + timedelta(seconds=s)
        ),
        freezer=st.booleans(),
    ),
    max_size=12,
    unique_by=lambda lot: lot.id,
)
wanted = st.integers(min_value=0, max_value=10**10)


@given(lot_views, wanted, st.booleans())
def test_never_below_zero_and_nothing_lost(
    lots: list[LotView], amount: int, include_freezer: bool
) -> None:
    plan, short = plan_take(lots, amount, include_freezer)
    by_id = {lot.id: lot for lot in lots}
    for lot_id, taken in plan:
        assert 0 < taken <= by_id[lot_id].amount  # never more than a lot holds
    usable = sum(lot.amount for lot in lots if include_freezer or not lot.freezer)
    taken_total = sum(taken for _, taken in plan)
    assert taken_total == min(amount, usable)
    assert short == amount - taken_total >= 0
    assert len({lot_id for lot_id, _ in plan}) == len(plan)


@given(lot_views, wanted)
def test_oldest_first(lots: list[LotView], amount: int) -> None:
    """A lot is only touched once every lot that goes off before it is used up."""
    plan, _short = plan_take(lots, amount, include_freezer=True)
    order = [lot for lot in use_order(lots) if lot.amount > 0]
    taken = dict(plan)
    touched = [lot for lot in order if lot.id in taken]
    if touched:
        last = order.index(touched[-1])
        for lot in order[:last]:
            assert taken.get(lot.id) == lot.amount  # everything before it fully used
        assert order[: len(touched)] == touched


@given(lot_views, wanted)
def test_freezer_last_and_only_when_asked(lots: list[LotView], amount: int) -> None:
    plan, _short = plan_take(lots, amount)
    by_id = {lot.id: lot for lot in lots}
    assert not any(by_id[lot_id].freezer for lot_id, _ in plan)
    with_freezer, _ = plan_take(lots, amount, include_freezer=True)
    kinds = [by_id[lot_id].freezer for lot_id, _ in with_freezer]
    assert kinds == sorted(kinds)  # fridge and cupboard before freezer


def test_use_order_examples() -> None:
    old = LotView(1, 100, None, START, False)
    soon = LotView(2, 100, date(2026, 1, 3), START + timedelta(days=5), False)
    later = LotView(3, 100, date(2026, 2, 1), START, False)
    frozen = LotView(4, 100, date(2026, 1, 2), START, True)
    newer_no_date = LotView(5, 100, None, START + timedelta(days=1), False)
    order = use_order([old, soon, later, frozen, newer_no_date])
    assert [lot.id for lot in order] == [2, 3, 1, 5, 4]


def test_add_months() -> None:
    assert add_months(date(2026, 10, 17), 3) == date(2027, 1, 17)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2027, 11, 30), 3) == date(2028, 2, 29)
