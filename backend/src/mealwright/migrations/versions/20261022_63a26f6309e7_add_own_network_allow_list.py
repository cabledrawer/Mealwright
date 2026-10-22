"""add own network allow list

Revision ID: 63a26f6309e7
Revises: 97d61f9dd082
Create Date: 2026-10-22 20:19:13.920722

"Your own network" (spec section 6, "Recipe import, decided for 0.5", and section 7): the
places on the household's own network that Mealwright may visit, such as a home wiki. A new table,
own_network_entry, that starts empty; nothing existing changes. Going back drops the table
and its entries.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "63a26f6309e7"
down_revision: str | Sequence[str] | None = "97d61f9dd082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "own_network_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("value", sa.String(length=260), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by_login_id", sa.Integer(), nullable=True),
        sa.Column("added_by_name", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "kind IN ('name', 'address', 'range')", name=op.f("ck_own_network_entry_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["added_by_login_id"],
            ["login.id"],
            name=op.f("fk_own_network_entry_added_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_own_network_entry_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_own_network_entry")),
        sa.UniqueConstraint(
            "household_id", "value", name=op.f("uq_own_network_entry_household_id")
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("own_network_entry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_own_network_entry_household_id"), ["household_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("own_network_entry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_own_network_entry_household_id"))

    op.drop_table("own_network_entry")
