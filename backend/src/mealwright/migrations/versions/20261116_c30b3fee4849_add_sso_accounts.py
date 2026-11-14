"""single sign-on accounts that wait for an admin

Revision ID: c30b3fee4849
Revises: b8e2d4f6a913
Create Date: 2026-11-16 10:00:00

0.9.5 step 16c (Pe3/M2, cabledrawer 13 Nov): a first single sign-on sign-in is linked automatically
only to the person with exactly the same username; anyone else waits until an admin says who they
are ("Who is this?"). A new table, `sso_account`, keeps each account the sign-in server signed in
here: who is waiting, who an admin refused, and who was unlinked by hand (so neither is linked
automatically again). Nothing else changes, and existing logins keep their links.

Going back drops the table: waiting sign-ins, refusals and Unlinks are forgotten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c30b3fee4849"
down_revision: str | Sequence[str] | None = "b8e2d4f6a913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sso_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_sso_account_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sso_account")),
        sa.UniqueConstraint("household_id", "issuer", "subject", name="uq_sso_account"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("sso_account", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sso_account_household_id"), ["household_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("sso_account", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sso_account_household_id"))
    op.drop_table("sso_account")
