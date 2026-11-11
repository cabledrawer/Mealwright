"""add step timings and the household's kitchen

Revision ID: c3e9a1d7b504
Revises: a7c4e9d2b813
Create Date: 2026-11-11 10:00:00

Batch cook (Experimental), database change 1 of 3 (0.8 wave 6, B1; cabledrawer 28 Oct, 6 Nov and
11 Nov).

- `recipe_step.timing_hands` ("hands" or "waiting"), `timing_minutes` and `timing_equipment`
  ("hob", "pressure", "oven" or "none"): what a person set by hand on a step. Empty means the
  value is guessed from the step's words, every time it is read (so a step made before this,
  or one whose words change, always has an up-to-date guess and nothing needs filling in).
  A by-hand value is never overwritten by a guess.
- `household.kitchen_hob_rings` (4), `kitchen_pressure_cookers` (1), `kitchen_oven` (yes) and
  `kitchen_asked` (no): the household's equipment, and whether it has been asked yet (Batch
  cook asks once, on first use).

Going back drops the columns. What is lost: the by-hand timings and the kitchen.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9a1d7b504"
down_revision: str | Sequence[str] | None = "a7c4e9d2b813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("recipe_step", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("timing_hands", sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column("timing_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("timing_equipment", sa.String(length=8), nullable=True))
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kitchen_hob_rings", sa.Integer(), server_default="4", nullable=False)
        )
        batch_op.add_column(
            sa.Column("kitchen_pressure_cookers", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column("kitchen_oven", sa.Boolean(), server_default=sa.text("1"), nullable=False)
        )
        batch_op.add_column(
            sa.Column("kitchen_asked", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("kitchen_asked")
        batch_op.drop_column("kitchen_oven")
        batch_op.drop_column("kitchen_pressure_cookers")
        batch_op.drop_column("kitchen_hob_rings")
    with op.batch_alter_table("recipe_step", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("timing_equipment")
        batch_op.drop_column("timing_minutes")
        batch_op.drop_column("timing_hands")
