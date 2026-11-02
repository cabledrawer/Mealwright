"""add food restock_typed_at

Revision ID: 5fbd6d33c434
Revises: d2e6a4b81c37
Create Date: 2026-11-02 12:00:00

The restock date typed in the editor wins (0.7 K5; cabledrawer 2 Nov: "when I type a restock date,
the pantry shows that date even if a Shopping tick is newer").

- `food.restock_typed_at`: the moment a restock date was typed, or Restocked was pressed, in
  the editor. A "Restocked" tick on Shopping counts only when it was ticked after this moment.
  Empty to begin with, so every date shown stays as it was.

Going back drops the column. The only loss is that a typed date under a newer tick is shown
as the tick again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5fbd6d33c434"
down_revision: str | Sequence[str] | None = "d2e6a4b81c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(
            sa.Column("restock_typed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("restock_typed_at")
