"""Database tables.

Every table belongs to a household (`household_id`), so more than one household per
install stays possible later. The household table's own `id` is that household_id.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mealwright.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Household(Base):
    __tablename__ = "household"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
