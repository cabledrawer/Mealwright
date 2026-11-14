"""add the household's "Include photos" backup setting

Revision ID: c6a1f3b9d805
Revises: b8e2d4f6a913
Create Date: 2026-11-16 09:00:00

0.9.5 step 16f (D2, cabledrawer 13 Nov): backups and the safety copy made before an upgrade include
the recipe photos, with an option to leave them out. One column on `household`:

- `backup_photos`: true (photos are included, the usual) or false. Every household that exists
  gets true.

Going back drops the column. What is lost: a household's choice to leave photos out (it is back
to including them when the column comes again). The backup files and their photo folders stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6a1f3b9d805"
down_revision: str | Sequence[str] | None = "b8e2d4f6a913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("backup_photos", sa.Boolean(), server_default=sa.text("1"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("backup_photos")
