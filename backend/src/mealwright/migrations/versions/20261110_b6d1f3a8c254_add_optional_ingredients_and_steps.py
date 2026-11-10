"""add optional ingredients and steps

Revision ID: b6d1f3a8c254
Revises: d4f8b2c1a695
Create Date: 2026-11-10 09:00:00

Optional ingredients and steps (0.8 wave 4, R3; cabledrawer 6 and 9 Nov).

- `recipe_line.optional` and `recipe_step.optional`: the line or step is Optional. Every
  existing line and step starts as not optional, so nothing changes until someone marks one.
- `meal_item.optional_skipped`: the ids of the Optional lines of a planned recipe that the person
  will not use (a list). Empty to begin with: a meal made before this counts every line, as
  it always did.
- `recipe.nutrition_set_at` and `recipe.lines_changed_at`: when the nutrition figures were last
  typed or read from a page, and when the ingredient lines last changed. The recipe page says
  "Nutrition possibly out of date" when the lines changed after the figures were set. Both
  empty to begin with: no old recipe says it.

Going back drops the columns. The only loss is the Optional marks, the picks and the dates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d1f3a8c254"
down_revision: str | Sequence[str] | None = "d4f8b2c1a695"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    for table in ("recipe_line", "recipe_step"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.add_column(
                sa.Column("optional", sa.Boolean(), server_default=sa.text("0"), nullable=False)
            )
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("optional_skipped", sa.JSON(), nullable=True))
    with op.batch_alter_table("recipe", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(
            sa.Column("nutrition_set_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("lines_changed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("lines_changed_at")
        batch_op.drop_column("nutrition_set_at")
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("optional_skipped")
    for table in ("recipe_step", "recipe_line"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.drop_column("optional")
