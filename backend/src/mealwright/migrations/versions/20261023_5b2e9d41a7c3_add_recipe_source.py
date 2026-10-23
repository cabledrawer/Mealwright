"""add recipe source

Revision ID: 5b2e9d41a7c3
Revises: 63a26f6309e7
Create Date: 2026-10-23 12:00:00

Where an imported recipe came from (spec section 6, "Recipe import, decided for 0.5"; cabledrawer
22 Oct, question 1): the web address it was read from, the day it was imported and the author's
name from the page. Three new, optional columns on `recipe`; every recipe already there has
none of them, and nothing else changes. Going back drops the three columns and what they hold.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b2e9d41a7c3"
down_revision: str | Sequence[str] | None = "63a26f6309e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite changes a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("recipe", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("source_url", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("source_author", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipe", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("source_author")
        batch_op.drop_column("imported_at")
        batch_op.drop_column("source_url")
