"""keep the names rows used to have, for as long as log lines live

Revision ID: d3a9f1c7e254
Revises: e5b3c9a1d742
Create Date: 2026-11-14 09:00:00

Beta fix5 (proposed, for cabledrawer): "Report a problem" removes a name from the log lines also
after the person, recipe, ingredient, tag, shop, place, list or household that had it has been
renamed or deleted. New table `former_name` (household_id, kind, name, at), empty: a session
hook fills it, and the nightly log tidy deletes rows older than the log files (14 days) plus a
day. It is empty after this change; older renames are still found through the undo data of
Recent changes.

Going back drops the table: only the kept old names are lost.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a9f1c7e254"
down_revision: str | Sequence[str] | None = "e5b3c9a1d742"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "former_name",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_former_name_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_former_name")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("former_name", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_former_name_at"), ["at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_former_name_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(
            "ix_former_name_household_id_kind_name", ["household_id", "kind", "name"], unique=False
        )


def downgrade() -> None:
    op.drop_table("former_name")
