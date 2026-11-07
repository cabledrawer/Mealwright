"""add food date_kind

Revision ID: a8c3e5f71d24
Revises: 5fbd6d33c434
Create Date: 2026-11-07 12:00:00

Use by or Best before (0.8, cabledrawer 7 Nov).

- `food.date_kind`: "use_by" or "best_before" when the household chose one for the
  ingredient in its editor. Empty to begin with: every ingredient then gets its default (the
  pack-size table's, else by where it is usually kept), so nothing a household has typed is
  changed.

Going back drops the column. The only loss is the choices made in the editor.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c3e5f71d24"
down_revision: str | Sequence[str] | None = "5fbd6d33c434"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("date_kind", sa.String(length=11), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("date_kind")
