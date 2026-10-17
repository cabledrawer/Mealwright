"""add change log and merge history

Revision ID: 8ff55379e5fa
Revises: 28868ef58fd5
Create Date: 2026-10-17 19:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8ff55379e5fa"
down_revision: str | Sequence[str] | None = "28868ef58fd5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("request", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=True),
        sa.Column("login_name", sa.String(length=100), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("undo_data", sa.JSON(), nullable=True),
        sa.Column("undone_by_change_id", sa.Integer(), nullable=True),
        sa.Column("undoes_change_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_change_food_id_food"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_change_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"], ["login.id"], name=op.f("fk_change_login_id_login"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["undoes_change_id"], ["change.id"], name=op.f("fk_change_undoes_change_id_change")
        ),
        sa.ForeignKeyConstraint(
            ["undone_by_change_id"],
            ["change.id"],
            name=op.f("fk_change_undone_by_change_id_change"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change")),
        sa.UniqueConstraint("household_id", "idempotency_key", name=op.f("uq_change_household_id")),
    )
    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_change_at"), ["at"], unique=False)
        batch_op.create_index(batch_op.f("ix_change_food_id"), ["food_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_change_household_id"), ["household_id"], unique=False)

    op.create_table(
        "food_merge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("from_food_id", sa.Integer(), nullable=False),
        sa.Column("into_food_id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("split_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_food_merge_change_id_change"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["from_food_id"],
            ["food.id"],
            name=op.f("fk_food_merge_from_food_id_food"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_merge_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["into_food_id"],
            ["food.id"],
            name=op.f("fk_food_merge_into_food_id_food"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_merge")),
    )
    with op.batch_alter_table("food_merge", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_food_merge_household_id"), ["household_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("food_merge", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_merge_household_id"))

    op.drop_table("food_merge")

    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_change_household_id"))
        batch_op.drop_index(batch_op.f("ix_change_food_id"))
        batch_op.drop_index(batch_op.f("ix_change_at"))

    op.drop_table("change")
