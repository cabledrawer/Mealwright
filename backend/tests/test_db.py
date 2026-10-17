from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from mealwright.db import make_engine


def test_database_errors_leave_out_what_people_typed(tmp_path: Path) -> None:
    """A database error ends up in the log as a traceback, so its text must not carry the
    query's values: a password typed into the username box, for example."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    typed = "my-password-typed-in-the-wrong-box"
    with engine.connect() as connection, pytest.raises(OperationalError) as error:
        connection.execute(text("SELECT * FROM no_such_table WHERE name = :name"), {"name": typed})
    assert typed not in str(error.value)
    assert "parameters hidden" in str(error.value)


def test_other_databases_hide_values_too(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("mealwright.db.create_engine", lambda url, **kw: seen.update(kw))
    make_engine("postgresql://user@localhost/none")  # the Postgres option, later
    assert seen.get("hide_parameters") is True
