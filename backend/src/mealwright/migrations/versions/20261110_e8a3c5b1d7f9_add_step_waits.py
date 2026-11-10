"""add step waits

Revision ID: e8a3c5b1d7f9
Revises: b6d1f3a8c254
Create Date: 2026-11-10 14:00:00

Steps that wait (0.8 wave 5, M1; cabledrawer 31 Oct and 9 Nov).

- `recipe_step.wait_kind`, `wait_min_minutes`, `wait_max_minutes`, `wait_overnight`: a step can
  carry a wait (marinate, ferment, soak...) as a range in minutes, or one that ends at
  "overnight". All empty to begin with: every existing step has no wait, and a recipe made
  before this keeps its single time (nothing is guessed from old words).

Going back drops the four columns. The only loss is the waits.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8a3c5b1d7f9"
down_revision: str | Sequence[str] | None = "b6d1f3a8c254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("recipe_step", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("wait_kind", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("wait_min_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("wait_max_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("wait_overnight", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe_step", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("wait_overnight")
        batch_op.drop_column("wait_max_minutes")
        batch_op.drop_column("wait_min_minutes")
        batch_op.drop_column("wait_kind")
