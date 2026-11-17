"""Helpers for tests that need many drafts at once."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright.models import ImportDraft


def clone_drafts(client: TestClient, copies: int) -> None:
    """Copy the household's first draft `copies` times, straight into the table."""
    with client.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        first: Any = session.scalars(select(ImportDraft).order_by(ImportDraft.id)).first()
        columns = [c.key for c in ImportDraft.__table__.columns if c.key != "id"]
        for number in range(copies):
            values = {key: getattr(first, key) for key in columns}
            values["name"] = f"Recipe {number}"
            session.add(ImportDraft(**values))
        session.commit()
