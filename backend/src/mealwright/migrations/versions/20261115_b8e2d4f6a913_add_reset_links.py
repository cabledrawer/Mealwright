"""reset password links, and when a link was used

Revision ID: b8e2d4f6a913
Revises: d3a9f1c7e254
Create Date: 2026-11-15 10:00:00

0.9.5 step 16b (cabledrawer 13 Nov): two new columns.

- `join_link.kind`: "join" (a sign-in link, for a login with no password yet) or "reset" (a
  Reset password link an admin made, for a login that has one). Every existing link is "join".
- `login.link_used_at`: when a sign-in or Reset password link last set this login's password,
  so the Person page can say "Link used today 21:40". Every existing login has it empty.

Going back drops both columns and any unused Reset password link (without its kind it would read
as a sign-in link): only those links and the "Link used" times are lost.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2d4f6a913"
down_revision: str | Sequence[str] | None = "d3a9f1c7e254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("join_link", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=10), nullable=False, server_default="join")
        )
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.add_column(sa.Column("link_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("DELETE FROM join_link WHERE kind = 'reset'")
    with op.batch_alter_table("login", schema=None) as batch_op:
        batch_op.drop_column("link_used_at")
    with op.batch_alter_table("join_link", schema=None) as batch_op:
        batch_op.drop_column("kind")
