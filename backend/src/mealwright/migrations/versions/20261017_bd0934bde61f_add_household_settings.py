"""add household settings

Revision ID: bd0934bde61f
Revises: d60b64f1e4ff
Create Date: 2026-10-17 19:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bd0934bde61f"
down_revision: str | Sequence[str] | None = "d60b64f1e4ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(sa.Column("time_zone", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("cup_ml", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("undo_days", sa.Integer(), server_default="7", nullable=False)
        )
        batch_op.add_column(
            sa.Column("history_months", sa.Integer(), server_default="12", nullable=False)
        )
        batch_op.add_column(
            sa.Column("use_soon_days", sa.Integer(), server_default="2", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("use_soon_days")
        batch_op.drop_column("history_months")
        batch_op.drop_column("undo_days")
        batch_op.drop_column("cup_ml")
        batch_op.drop_column("time_zone")
