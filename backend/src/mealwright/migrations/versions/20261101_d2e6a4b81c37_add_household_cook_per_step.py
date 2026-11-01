"""add household cook_per_step

Revision ID: d2e6a4b81c37
Revises: f27b95d1c8a3
Create Date: 2026-11-01 10:00:00

Cook mode's per-step ingredients switch as a household setting (0.7 K4, cabledrawer 1 Nov): one
small column on `household`, `cook_per_step`, off by default. Every household that exists
starts off.

Going back drops the column. The only loss is that a household that had switched it on is
read as off again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e6a4b81c37"
down_revision: str | Sequence[str] | None = "f27b95d1c8a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cook_per_step", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("cook_per_step")
