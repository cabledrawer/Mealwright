"""add API tokens

Revision ID: c3a7e5d1f824
Revises: c1d5e9a3f702
Create Date: 2026-11-14 09:00:00

API tokens (0.9, PR O2), its one database change: a new, empty table `api_token`. Each row is
one token an admin made for a script or another app: its name, read only or full, when it was
made and last used, when it stops working (empty: never), and when it was deleted. Only the
token's SHA-256 is stored, never the token itself.

Going back drops the table: every token stops working, and nothing else changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a7e5d1f824"
down_revision: str | Sequence[str] | None = "c1d5e9a3f702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('read', 'full')", name=op.f("ck_api_token_scope_known")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_api_token_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"],
            ["login.id"],
            name=op.f("fk_api_token_login_id_login"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_token_token_hash")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("api_token", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_token_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_api_token_login_id"), ["login_id"])


def downgrade() -> None:
    with op.batch_alter_table("api_token", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_token_login_id"))
        batch_op.drop_index(batch_op.f("ix_api_token_household_id"))
    op.drop_table("api_token")
