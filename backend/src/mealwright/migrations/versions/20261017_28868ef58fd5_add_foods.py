"""add foods

Revision ID: 28868ef58fd5
Revises: e9d1bba1c1d5
Create Date: 2026-10-17 19:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "28868ef58fd5"
down_revision: str | Sequence[str] | None = "e9d1bba1c1d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "food",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("counted_as", sa.String(length=10), nullable=False),
        sa.Column("staple", sa.Boolean(), nullable=False),
        sa.Column("count_word", sa.String(length=30), nullable=True),
        sa.Column("count_word_plural", sa.String(length=30), nullable=True),
        sa.Column("place_id", sa.Integer(), nullable=True),
        sa.Column("shop_id", sa.Integer(), nullable=True),
        sa.Column("running_low_milli", sa.BigInteger(), nullable=True),
        sa.Column("table_key", sa.String(length=80), nullable=True),
        sa.Column("merged_into_id", sa.Integer(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["food.id"], name=op.f("fk_food_merged_into_id_food")
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["place.id"], name=op.f("fk_food_place_id_place"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shop.id"], name=op.f("fk_food_shop_id_shop"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("food", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_food_household_id"), ["household_id"], unique=False)

    op.create_table(
        "food_name",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_food_name_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_name_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_name")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("food_name", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_food_name_food_id"), ["food_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_food_name_household_id"), ["household_id"], unique=False
        )

    op.create_table(
        "food_size",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("plural", sa.String(length=40), nullable=False),
        sa.Column("amount_milli", sa.BigInteger(), nullable=False),
        sa.Column("usual", sa.Boolean(), nullable=False),
        sa.Column("added_when_shopping", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount_milli > 0", name=op.f("ck_food_size_amount_positive")),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_food_size_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_size_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_size")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("food_size", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_food_size_food_id"), ["food_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_food_size_household_id"), ["household_id"], unique=False
        )

    op.create_table(
        "food_stand_in",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("stand_in_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_food_stand_in_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_stand_in_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stand_in_id"],
            ["food.id"],
            name=op.f("fk_food_stand_in_stand_in_id_food"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("food_id", "stand_in_id", name=op.f("pk_food_stand_in")),
    )
    with op.batch_alter_table("food_stand_in", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_food_stand_in_household_id"), ["household_id"], unique=False
        )

    op.create_table(
        "food_conversion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("value_milli", sa.BigInteger(), nullable=False),
        sa.Column("answered_by_name", sa.String(length=100), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["food.id"],
            name=op.f("fk_food_conversion_food_id_food"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_conversion_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_conversion")),
        sa.UniqueConstraint("food_id", "kind", name=op.f("uq_food_conversion_food_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("food_conversion", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_food_conversion_food_id"), ["food_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_food_conversion_household_id"), ["household_id"], unique=False
        )

    op.create_table(
        "food_not_same",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("food_a_id", sa.Integer(), nullable=False),
        sa.Column("food_b_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_a_id"],
            ["food.id"],
            name=op.f("fk_food_not_same_food_a_id_food"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["food_b_id"],
            ["food.id"],
            name=op.f("fk_food_not_same_food_b_id_food"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_food_not_same_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("food_a_id", "food_b_id", name=op.f("pk_food_not_same")),
    )
    with op.batch_alter_table("food_not_same", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_food_not_same_household_id"), ["household_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("food_not_same", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_not_same_household_id"))

    op.drop_table("food_not_same")

    with op.batch_alter_table("food_conversion", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_conversion_household_id"))
        batch_op.drop_index(batch_op.f("ix_food_conversion_food_id"))

    op.drop_table("food_conversion")

    with op.batch_alter_table("food_stand_in", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_stand_in_household_id"))

    op.drop_table("food_stand_in")

    with op.batch_alter_table("food_size", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_size_household_id"))
        batch_op.drop_index(batch_op.f("ix_food_size_food_id"))

    op.drop_table("food_size")

    with op.batch_alter_table("food_name", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_name_household_id"))
        batch_op.drop_index(batch_op.f("ix_food_name_food_id"))

    op.drop_table("food_name")

    with op.batch_alter_table("food", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_food_household_id"))

    op.drop_table("food")
