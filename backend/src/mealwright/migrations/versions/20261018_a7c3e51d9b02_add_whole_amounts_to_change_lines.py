"""add whole amounts to change lines

Revision ID: a7c3e51d9b02
Revises: b4391aaf7695
Create Date: 2026-10-18 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e51d9b02"
down_revision: str | Sequence[str] | None = "b4391aaf7695"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null for lines recorded before 0.2.1: Recent changes keeps its old wording for them.
    with op.batch_alter_table("change_line", schema=None) as batch_op:
        batch_op.add_column(sa.Column("total_before_milli", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("total_after_milli", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("change_line", schema=None) as batch_op:
        batch_op.drop_column("total_after_milli")
        batch_op.drop_column("total_before_milli")
