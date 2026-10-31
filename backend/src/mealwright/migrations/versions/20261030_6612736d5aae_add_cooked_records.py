"""add cooked records

Revision ID: 6612736d5aae
Revises: 31a5838bc5a2
Create Date: 2026-10-30 23:45:00

The cooked record (0.7 K1; spec section 6, "Plan and batch cooks", cabledrawer 17 Oct: "a cooked
record per meal or batch (a snapshot of the recipe as cooked plus its stock changes)").

- New table `cooked_record`: for one meal item or one batch cook (never both), the recipe as it
  was cooked (a JSON snapshot), how many portions, who cooked it and when, and the change in the
  change log that holds its stock changes. It belongs to a household; its links to the meal
  item and the batch cook are composite keys that include `household_id`, so a record can never
  reach into another household. It goes with its meal item or batch cook. The recipe and the
  change are plain links that empty when those are deleted; the snapshot keeps the recipe.
- `meal_item` gets a unique (household_id, id), which the key to it needs. Nothing else about
  it changes.

Going back drops the table and the unique key. The only loss is the records.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6612736d5aae"
down_revision: str | Sequence[str] | None = "31a5838bc5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite adds a unique key by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.create_unique_constraint(
            batch_op.f("uq_meal_item_household_id_id"), ["household_id", "id"]
        )
    op.create_table(
        "cooked_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("meal_item_id", sa.Integer(), nullable=True),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("portions", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("cooked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooked_by_login_id", sa.Integer(), nullable=True),
        sa.Column("cooked_by_name", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "(meal_item_id IS NULL) != (batch_id IS NULL)",
            name=op.f("ck_cooked_record_meal_item_or_batch"),
        ),
        sa.CheckConstraint(
            "portions >= 1 AND portions <= 999", name=op.f("ck_cooked_record_portions_range")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_cooked_record_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "meal_item_id"],
            ["meal_item.household_id", "meal_item.id"],
            name="fk_cooked_record_household_id_meal_item",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["batch_cook.household_id", "batch_cook.id"],
            name="fk_cooked_record_household_id_batch_cook",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_cooked_record_recipe_id_recipe"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_cooked_record_change_id_change"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cooked_by_login_id"],
            ["login.id"],
            name=op.f("fk_cooked_record_cooked_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cooked_record")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("cooked_record", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cooked_record_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_cooked_record_recipe_id"), ["recipe_id"])
        batch_op.create_index(batch_op.f("ix_cooked_record_change_id"), ["change_id"])
        batch_op.create_index("uq_cooked_record_meal_item_id", ["meal_item_id"], unique=True)
        batch_op.create_index("uq_cooked_record_batch_id", ["batch_id"], unique=True)


def downgrade() -> None:
    op.drop_table("cooked_record")
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_meal_item_household_id_id"), type_="unique")
