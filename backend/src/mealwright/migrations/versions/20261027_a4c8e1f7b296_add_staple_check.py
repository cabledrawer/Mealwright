"""add staple check

Revision ID: a4c8e1f7b296
Revises: e3b7a95c4d18
Create Date: 2026-10-27 09:00:00

Shopping's "Check you have these" card (0.6 PR 5): when someone taps "Got it" on a staple, the
server must remember it, across phones and restarts, until the plan's use of that staple
changes. One small table, `staple_check`: the ingredient, its household and a short fingerprint
of the planned meals that use it.

Going back drops the table. The only loss is that staples marked "Got it" show on the card again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c8e1f7b296"
down_revision: str | Sequence[str] | None = "e3b7a95c4d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staple_check",
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("need_key", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_staple_check_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_staple_check_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("food_id", name=op.f("pk_staple_check")),
    )
    with op.batch_alter_table("staple_check", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_staple_check_household_id"), ["household_id"])


def downgrade() -> None:
    op.drop_table("staple_check")  # its index goes with it
