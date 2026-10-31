"""The list counter is written the moment a number is taken (0.7 K2, follow-up 7 from PR 74's
security round 2), so a second `Batch` in the same transaction (a plan Undo updates the list inside
the Undo's own) can never start from a stale number or wind the counter back."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_plan import db_of

from mealwright.api.v1.context import Kitchen
from mealwright.models import Household, Login
from mealwright.shopping import Batch


def _kitchen(db: Session) -> Kitchen:
    household = db.get(Household, 1)
    assert household is not None
    login = db.scalars(select(Login).where(Login.household_id == 1)).first()
    assert login is not None
    return Kitchen(db=db, login=login, household=household, idempotency_key=None, request="TEST")


def test_take_writes_the_counter_at_once(kitchen: TestClient) -> None:
    with db_of(kitchen) as db:
        k = _kitchen(db)
        start = k.household.list_seq
        batch = Batch(k, action="first")
        assert batch.take() == start + 1
        assert k.household.list_seq == start + 1  # before finish()
        assert batch.take() == start + 2 and k.household.list_seq == start + 2


def test_a_second_batch_in_the_same_transaction_carries_on_from_the_first(
    kitchen: TestClient,
) -> None:
    with db_of(kitchen) as db:
        k = _kitchen(db)
        start = k.household.list_seq
        outer = Batch(k, action="outer")
        inner = Batch(k, action="inner")
        assert outer.take() == start + 1
        assert inner.take() == start + 2  # never the number the outer one has used
        inner.finish()
        outer.finish()  # finishing the outer one never winds the counter back
        assert k.household.list_seq == start + 2
        db.commit()
        db.refresh(k.household)
        assert k.household.list_seq == start + 2


def test_a_refused_action_hands_its_number_back(kitchen: TestClient) -> None:
    with db_of(kitchen) as db:
        k = _kitchen(db)
        start = k.household.list_seq
        batch = Batch(k, action="refused")
        batch.take()
        batch.give_back()
        assert k.household.list_seq == start
        assert batch.take() == start + 1  # numbers have no gaps
