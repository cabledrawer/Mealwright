"""add staple restock date

Revision ID: b89c3c1918f8
Revises: c5f1b8d2a763
Create Date: 2026-10-30 23:00:00

A restock date per staple (0.7 K1; cabledrawer 20 Oct: "a restock date per staple (0.7)").

- `list_tick.restock`: this purchase was a staple ticked on Shopping ("Restocked · staples
  aren't counted"). Purchases made before this upgrade are marked when nothing went into the
  pantry and their ingredient is a staple now: that is what the row said.
- `food.restocked_at`: the newest restock among purchases the tidy-up has deleted, so the date
  outlives them. Empty to begin with.

Going back drops both columns. The only loss is the restock dates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b89c3c1918f8"
down_revision: str | Sequence[str] | None = "c5f1b8d2a763"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("restocked_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("list_tick", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("restock", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )
    op.execute(
        "UPDATE list_tick SET restock = 1 WHERE bought_milli IS NULL AND item_id IN ("
        " SELECT list_item.id FROM list_item JOIN food ON food.id = list_item.food_id"
        " WHERE food.staple AND food.household_id = list_tick.household_id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("list_tick", schema=None) as batch_op:
        batch_op.drop_column("restock")
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("restocked_at")
