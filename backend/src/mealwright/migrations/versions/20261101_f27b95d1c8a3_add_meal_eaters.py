"""add meal eaters

Revision ID: f27b95d1c8a3
Revises: e0c4a7b19d35
Create Date: 2026-11-01 10:00:00

Who is eating a meal (0.7 P1; spec, "The Plan redesign": "Click a meal → Serves - N + and who's
eating, right there (F57)").

- New table `meal_eater`: one row per person ticked for a meal; no rows means everyone. It
  belongs to a household; its link to the meal is a composite key that includes `household_id`,
  so a row can never reach into another household, and it goes with its meal. The person is a
  login (proposed, for cabledrawer: by sign-in until member profiles arrive in 0.8, as tubs are) and
  goes with the login.

Going back drops the table. The only loss is who was ticked.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f27b95d1c8a3"
down_revision: str | Sequence[str] | None = "e0c4a7b19d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_eater",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_meal_eater_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "meal_id"],
            ["meal.household_id", "meal.id"],
            name="fk_meal_eater_household_id_meal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"],
            ["login.id"],
            name=op.f("fk_meal_eater_login_id_login"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_eater")),
        sa.UniqueConstraint("meal_id", "login_id", name="uq_meal_eater_meal_id_login_id"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("meal_eater", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_eater_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_meal_eater_meal_id"), ["meal_id"])
        batch_op.create_index(batch_op.f("ix_meal_eater_login_id"), ["login_id"])


def downgrade() -> None:
    op.drop_table("meal_eater")
