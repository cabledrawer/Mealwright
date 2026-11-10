"""add meal item start times

Revision ID: a7c4e9d2b813
Revises: f1a6d3c8e502
Create Date: 2026-11-10 21:00:00

The plan works backwards (0.8 wave 5, M3, F124; cabledrawer 31 Oct and 9 Nov).

- `meal_item.start_at`: when the person will start a recipe's long wait (soak and grind the
  batter the evening before). An instant (UTC); the screens show it in the household's time.
- `meal_item.started_at`: when the wait was begun ("Done already", or Cook mode past the step).

Both are empty to begin with: a meal made before this has none, and nothing reads differently.
Going back drops both columns. What is lost: every start time and every "started" mark.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c4e9d2b813"
down_revision: str | Sequence[str] | None = "f1a6d3c8e502"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("started_at")
        batch_op.drop_column("start_at")
