"""add the household's backup settings

Revision ID: b2f7c4e8a915
Revises: b4f8e2a6c917
Create Date: 2026-11-13 09:00:00

Backups (0.9, D1; spec section 7, "Backups", cabledrawer 17 Oct): Mealwright backs its database up by
itself into the data folder, daily by default, keeping the last 7. Four small columns on
`household`:

- `backup_every`: how often, "daily" (the usual), "twice-daily" or "weekly".
- `backup_keep`: how many of its own backups are kept, 1 to 30 (7 by default).
- `backup_problem` and `backup_problem_at`: the last backup that failed, in plain words, and when;
  empty while backups work.

Every household that exists gets daily and 7, and no problem.

Going back drops the four columns. What is lost: a household's own choice of how often and how
many (it is back to daily and 7 when it comes again), and the last problem's words. The backup
files themselves stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2f7c4e8a915"
down_revision: str | Sequence[str] | None = "b4f8e2a6c917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("backup_every", sa.String(length=12), server_default="daily", nullable=False)
        )
        batch_op.add_column(
            sa.Column("backup_keep", sa.Integer(), server_default="7", nullable=False)
        )
        batch_op.add_column(sa.Column("backup_problem", sa.String(length=300), nullable=True))
        batch_op.add_column(
            sa.Column("backup_problem_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("backup_problem_at")
        batch_op.drop_column("backup_problem")
        batch_op.drop_column("backup_keep")
        batch_op.drop_column("backup_every")
