"""mark a login the sign-in server has refused

Revision ID: e5b3c9a1d742
Revises: c3a7e5d1f824
Create Date: 2026-11-14 10:00:00

O2 fix13 (cabledrawer 12 Nov): one new, empty column `login.sso_refused_at`. Set when single sign-on
refuses a login that Mealwright keeps signed in because nobody else can get in; cleared when the
sign-in server accepts them again. While set, the login can't make API tokens, and tokens it made
at or after that time stop. Every existing login has it empty.

Going back drops the column: only the mark is lost.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b3c9a1d742"
down_revision: str | Sequence[str] | None = "c3a7e5d1f824"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sso_refused_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.drop_column("sso_refused_at")
