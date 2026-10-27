"""add household pints

Revision ID: c5f1b8d2a763
Revises: a4c8e1f7b296
Create Date: 2026-10-27 14:00:00

Which pint a recipe's "pint" means (0.6 PR 7, cabledrawer 24 and 26 Oct): one small column on
`household`, `pints`, "uk" (568 ml) or "us" (473 ml). Every household that exists starts on
"uk", the default.

Going back drops the column. The only loss is that a household that chose US pints is read as
UK again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5f1b8d2a763"
down_revision: str | Sequence[str] | None = "a4c8e1f7b296"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("pints", sa.String(length=2), server_default="uk", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("pints")
