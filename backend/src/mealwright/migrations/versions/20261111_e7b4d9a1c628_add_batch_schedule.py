"""add the Batch cook schedule snapshot and its progress

Revision ID: e7b4d9a1c628
Revises: d5a2c7e9b316
Create Date: 2026-11-11 18:00:00

Batch cook (Experimental), database change 3 of 3 (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov).

- `batch_session.schedule`, `schedule_basis` and `schedule_made_at`: the schedule as it was made
  when batch cook mode was started (a snapshot), what it was made from (so "Plan again" is offered
  when a recipe or the kitchen changed) and when. All empty until the mode is started.
- New table `batch_task_progress`: one row for each task that is done or whose timer was started,
  so a reload, another device or a closed tab carries on where it was. It belongs to a household
  and goes with its session.

Going back drops the table and the three columns. What is lost: the schedules and where each
session was up to (the sessions themselves stay).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b4d9a1c628"
down_revision: str | Sequence[str] | None = "d5a2c7e9b316"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("batch_session", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("schedule", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("schedule_basis", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("schedule_made_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_table(
        "batch_task_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=16), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id", "session_id"],
            ["batch_session.household_id", "batch_session.id"],
            name=op.f("fk_batch_task_progress_household_id_batch_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_batch_task_progress_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_task_progress")),
        sa.UniqueConstraint(
            "session_id", "task_id", name=op.f("uq_batch_task_progress_session_id_task_id")
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("batch_task_progress", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_batch_task_progress_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_batch_task_progress_session_id"), ["session_id"])


def downgrade() -> None:
    op.drop_table("batch_task_progress")
    with op.batch_alter_table("batch_session", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("schedule_made_at")
        batch_op.drop_column("schedule_basis")
        batch_op.drop_column("schedule")
