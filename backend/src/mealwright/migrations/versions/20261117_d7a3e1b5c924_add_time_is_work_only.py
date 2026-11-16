"""add the hidden "time is work only" mark to recipes and their ways of cooking

Revision ID: d7a3e1b5c924
Revises: c4f7a2d9e816
Create Date: 2026-11-17 15:00:00

L6 (cabledrawer 13 and 15 Nov; beta.2): an imported recipe's saved Time already has its wait taken
off, so the plan must not take it off again. One hidden column on each of `recipe` and
`recipe_method` (the first way mirrors the recipe, as `time_minutes` does):

- `time_is_work_only`: true when the saved time is the recipe's own work with the wait already
  off. Not null; every row that exists gets false, so it keeps today's behaviour.

Going back drops the columns. What is lost: the mark (a recipe then reads by the plain L6 rule).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3e1b5c924"
down_revision: str | Sequence[str] | None = "c4f7a2d9e816"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("recipe", "recipe_method"):
        with op.batch_alter_table(
            table, schema=None, table_kwargs={"sqlite_autoincrement": True}
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "time_is_work_only", sa.Boolean(), server_default=sa.text("0"), nullable=False
                )
            )


def downgrade() -> None:
    for table in ("recipe_method", "recipe"):
        with op.batch_alter_table(
            table, schema=None, table_kwargs={"sqlite_autoincrement": True}
        ) as batch_op:
            batch_op.drop_column("time_is_work_only")
