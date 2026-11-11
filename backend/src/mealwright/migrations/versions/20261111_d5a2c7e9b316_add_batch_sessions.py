"""add batch cook sessions and the Batch cook switch

Revision ID: d5a2c7e9b316
Revises: c3e9a1d7b504
Create Date: 2026-11-11 14:00:00

Batch cook (Experimental), database change 2 of 3 (0.8 wave 6, B2; cabledrawer 28 Oct and 11 Nov).

- New table `batch_session`: one Batch cook session (the cook day, and the rough "about X
  together" and "one by one" minutes it was planned with). It belongs to a household.
- `batch_cook.session_id`: the session a batch cook was made in. Empty for every batch cook made
  before this, and for any made with Cook once on its own. Tied to the session by the household
  as well as the id, like the plan's other links.
- `household.batch_cook_hidden` (no): an admin can hide Batch cook in Settings.

Going back drops the table and both columns. What is lost: the sessions (their recipes keep
their batch cooks, tubs and meals as ordinary Cook once batches) and the Batch cook switch.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5a2c7e9b316"
down_revision: str | Sequence[str] | None = "c3e9a1d7b504"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}
_LINK = "fk_batch_cook_household_id_batch_session"


def upgrade() -> None:
    op.create_table(
        "batch_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("cook_day", sa.Date(), nullable=False),
        sa.Column("together_minutes", sa.Integer(), nullable=True),
        sa.Column("one_by_one_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_batch_session_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_session")),
        sa.UniqueConstraint("household_id", "id", name=op.f("uq_batch_session_household_id_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("batch_session", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_batch_session_household_id"), ["household_id"])
    with op.batch_alter_table("batch_cook", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_batch_cook_session_id"), ["session_id"])
        batch_op.create_foreign_key(
            _LINK, "batch_session", ["household_id", "session_id"], ["household_id", "id"]
        )
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "batch_cook_hidden", sa.Boolean(), server_default=sa.text("0"), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("batch_cook_hidden")
    with op.batch_alter_table("batch_cook", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(_LINK, type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_batch_cook_session_id"))
        batch_op.drop_column("session_id")
    op.drop_table("batch_session")
