"""add where each sign-in is from, and when a password was last changed

Revision ID: b4f8e2a6c917
Revises: b4e8c2a6d917
Create Date: 2026-11-13 09:00:00

Sign-in hardening (0.9, PR A2), its one database change.

- `session.device`: a short name for the device a sign-in came from, such as "iPhone · Safari",
  for Settings' "Where you're signed in" list. Only this short name is kept, never the browser's
  whole User-Agent. Empty for sessions from before (they show as "Unknown device").
- `login.password_changed_at`: when the password was last changed, for "Last changed 2 Oct".
  Empty for passwords set before.

Both start empty, so nothing is lost or changed going forward. Going back drops the two columns:
what is lost is only those device names and dates; every login and session stays.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4f8e2a6c917"
down_revision: str | Sequence[str] | None = "b4e8c2a6d917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("device", sa.String(length=60), nullable=True))
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.drop_column("password_changed_at")
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_column("device")
