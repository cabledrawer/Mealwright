"""add whether the household has finished onboarding, and how it wants amounts shown

Revision ID: c7a1e5d3f802
Revises: b2f7c4e8a915
Create Date: 2026-11-13 12:00:00

Full Onboarding (0.9, PR U2), its one database change: two columns on `household`.

- `household.onboarding_done`: false while the household has not yet finished or skipped the
  onboarding steps that follow making the admin account (Amounts, Household, Shops, Starter
  packs). A household made by first-run setup starts false; Skip or Finish sets it true, and
  onboarding never shows again. Every household that already exists has been set up and used,
  so it starts true: nobody who upgrades is sent through onboarding.
- `household.amounts_shown`: "as_written" (the usual) or "metric" (grams and millilitres), the
  Amounts choice from Onboarding and Settings (spec "Amounts shown in 1.0"). Every household
  starts as "as_written", which is how amounts have always been shown.

Going back drops the two columns: only those two answers are lost.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a1e5d3f802"
down_revision: str | Sequence[str] | None = "b2f7c4e8a915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("onboarding_done", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "amounts_shown",
                sa.String(length=10),
                server_default="as_written",
                nullable=False,
            )
        )
    op.execute("UPDATE household SET onboarding_done = 1")


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("amounts_shown")
        batch_op.drop_column("onboarding_done")
