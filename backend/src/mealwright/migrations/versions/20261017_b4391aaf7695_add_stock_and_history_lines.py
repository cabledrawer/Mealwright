"""add stock and history lines

Revision ID: b4391aaf7695
Revises: 8ff55379e5fa
Create Date: 2026-10-17 19:51:40.793898

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4391aaf7695"
down_revision: str | Sequence[str] | None = "8ff55379e5fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_month",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount_milli", sa.BigInteger(), nullable=False),
        sa.Column("changes", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_change_month_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_change_month_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "month", "food_id", "kind", name=op.f("pk_change_month")
        ),
    )
    op.create_table(
        "stock_lot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("amount_milli", sa.BigInteger(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=True),
        sa.Column("use_by", sa.Date(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_on", sa.Date(), nullable=True),
        sa.Column("emptied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_milli >= 0", name=op.f("ck_stock_lot_never_below_zero")),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_stock_lot_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_stock_lot_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["place.id"], name=op.f("fk_stock_lot_place_id_place")
        ),
        sa.ForeignKeyConstraint(
            ["size_id"],
            ["food_size.id"],
            name=op.f("fk_stock_lot_size_id_food_size"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_lot")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("stock_lot", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stock_lot_food_id"), ["food_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_stock_lot_household_id"), ["household_id"], unique=False
        )

    op.create_table(
        "change_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("amount_before_milli", sa.BigInteger(), nullable=False),
        sa.Column("amount_after_milli", sa.BigInteger(), nullable=False),
        sa.Column("place_before_id", sa.Integer(), nullable=True),
        sa.Column("place_after_id", sa.Integer(), nullable=True),
        sa.Column("use_by_before", sa.Date(), nullable=True),
        sa.Column("use_by_after", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_change_line_change_id_change"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_change_line_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_change_line_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["stock_lot.id"],
            name=op.f("fk_change_line_lot_id_stock_lot"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["place_after_id"], ["place.id"], name=op.f("fk_change_line_place_after_id_place")
        ),
        sa.ForeignKeyConstraint(
            ["place_before_id"], ["place.id"], name=op.f("fk_change_line_place_before_id_place")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_line")),
    )
    with op.batch_alter_table("change_line", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_change_line_change_id"), ["change_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_change_line_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_change_line_lot_id"), ["lot_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("change_line", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_change_line_lot_id"))
        batch_op.drop_index(batch_op.f("ix_change_line_household_id"))
        batch_op.drop_index(batch_op.f("ix_change_line_change_id"))

    op.drop_table("change_line")
    with op.batch_alter_table("stock_lot", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_lot_household_id"))
        batch_op.drop_index(batch_op.f("ix_stock_lot_food_id"))

    op.drop_table("stock_lot")
    op.drop_table("change_month")
