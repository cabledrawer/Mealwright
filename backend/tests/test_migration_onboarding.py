"""PR U2's one database change: `household.onboarding_done` and `household.amounts_shown`."""

from pathlib import Path

from sqlalchemy import Engine, inspect, text

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "b2f7c4e8a915"  # the migration just before (0.9 D1: backup settings)
ONBOARDING = "c7a1e5d3f802"


def _columns(engine: Engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("household")}


def _households(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return list(
            connection.exec_driver_sql(
                "SELECT id, name, pints, undo_days FROM household ORDER BY id"
            ).all()
        )


def test_onboarding_migration_marks_existing_households_done_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')")
        )
    before = _households(engine)

    migrate.upgrade(engine, ONBOARDING)
    assert {"onboarding_done", "amounts_shown"} <= _columns(engine)
    assert _households(engine) == before
    with engine.connect() as connection:
        # A household from before has been set up already: it never sees onboarding.
        assert connection.exec_driver_sql(
            "SELECT onboarding_done, amounts_shown FROM household"
        ).all() == [(1, "as_written")]
    with engine.begin() as connection:
        # A household made after the upgrade (first-run setup) starts not done.
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (2, 'Next', '2026-11-13')"
        )
        assert connection.exec_driver_sql(
            "SELECT onboarding_done, amounts_shown FROM household WHERE id = 2"
        ).one() == (0, "as_written")
        connection.exec_driver_sql("UPDATE household SET amounts_shown = 'metric'")
        connection.exec_driver_sql("DELETE FROM household WHERE id = 2")

    migrate.downgrade(engine, BEFORE)
    assert not {"onboarding_done", "amounts_shown"} & _columns(engine)
    assert _households(engine) == before  # going back keeps the household

    migrate.upgrade(engine, ONBOARDING)  # forward again: done, amounts as written
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT onboarding_done, amounts_shown FROM household"
        ).all() == [(1, "as_written")]
    assert _households(engine) == before
