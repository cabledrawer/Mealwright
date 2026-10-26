"""add plan tables

Revision ID: e3b7a95c4d18
Revises: d7a4c2e81f56
Create Date: 2026-10-26 09:00:00

The meal plan's data (0.6 PR 2; cabledrawer's kickoff, 26 Oct: "Data model (meal slots, meals, meal
items, batch cooks, tubs, tub use-by defaults 3 days fridge / 3 months freezer). Database
change: full review, upgrade/downgrade tests.").

- New tables: `meal_slot`, `meal`, `batch_cook`, `tub` and `meal_item`. Each belongs to a
  household. A batch cook can point at the meal it was cooked for. Links between them are
  composite keys that include `household_id`, so a link can never reach into another household.
- `household`: `tub_fridge_days` (3), `tub_freezer_months` (3), `plan_ahead_days` (7) and
  `week_starts_on` (1, Monday).
- Every existing household gets its four slots: Breakfast, Lunch, Snack (off), Dinner.

Going back drops the five tables and the four columns. The plan is lost; recipes, ingredients,
stock and everything else are kept.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b7a95c4d18"
down_revision: str | Sequence[str] | None = "d7a4c2e81f56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copied, not imported, so this migration never changes when the app does.
DEFAULT_SLOTS = (("Breakfast", True), ("Lunch", True), ("Snack", False), ("Dinner", True))


def _household_column() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("household_id", sa.Integer(), nullable=False)


def _household_key(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["household_id"],
        ["household.id"],
        name=op.f(f"fk_{table}_household_id_household"),
        ondelete="CASCADE",
    )


def _index(table: str) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f"ix_{table}_household_id"), ["household_id"])


def upgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        for name, default in (
            ("tub_fridge_days", "3"),
            ("tub_freezer_months", "3"),
            ("plan_ahead_days", "7"),
            ("week_starts_on", "1"),
        ):
            batch_op.add_column(
                sa.Column(name, sa.Integer(), server_default=default, nullable=False)
            )

    op.create_table(
        "meal_slot",
        sa.Column("id", sa.Integer(), nullable=False),
        _household_column(),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        _household_key("meal_slot"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_slot")),
        sa.UniqueConstraint("household_id", "id", name=op.f("uq_meal_slot_household_id_id")),
        sqlite_autoincrement=True,
    )
    _index("meal_slot")

    op.create_table(
        "meal",
        sa.Column("id", sa.Integer(), nullable=False),
        _household_column(),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="planned", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned', 'cooked', 'didnt', 'moved')",
            name=op.f("ck_meal_status_known"),
        ),
        _household_key("meal"),
        sa.ForeignKeyConstraint(
            ["household_id", "slot_id"],
            ["meal_slot.household_id", "meal_slot.id"],
            name="fk_meal_household_id_meal_slot",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal")),
        sa.UniqueConstraint("household_id", "id", name=op.f("uq_meal_household_id_id")),
        sa.UniqueConstraint(
            "household_id", "day", "slot_id", name=op.f("uq_meal_household_id_day_slot_id")
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("meal", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_household_id"), ["household_id"])
        batch_op.create_index("ix_meal_household_id_day", ["household_id", "day"])

    op.create_table(
        "batch_cook",
        sa.Column("id", sa.Integer(), nullable=False),
        _household_column(),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("recipe_name", sa.String(length=200), nullable=False),
        sa.Column("cook_meal_id", sa.Integer(), nullable=True),
        sa.Column("cooked_on", sa.Date(), nullable=False),
        sa.Column("tub_count", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=14), server_default="pick", nullable=False),
        sa.Column("prep_note", sa.String(length=500), nullable=True),
        sa.Column("colour", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pattern IN ('lunches', 'lunch_dinner', 'dinners', 'pick')",
            name=op.f("ck_batch_cook_pattern_known"),
        ),
        sa.CheckConstraint(
            "tub_count >= 1 AND tub_count <= 99", name=op.f("ck_batch_cook_tub_count_range")
        ),
        _household_key("batch_cook"),
        sa.ForeignKeyConstraint(
            ["household_id", "cook_meal_id"],
            ["meal.household_id", "meal.id"],
            name="fk_batch_cook_household_id_meal",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_batch_cook_recipe_id_recipe"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_cook")),
        sa.UniqueConstraint("household_id", "id", name=op.f("uq_batch_cook_household_id_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("batch_cook", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_batch_cook_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_batch_cook_recipe_id"), ["recipe_id"])
        batch_op.create_index(batch_op.f("ix_batch_cook_cook_meal_id"), ["cook_meal_id"])

    op.create_table(
        "tub",
        sa.Column("id", sa.Integer(), nullable=False),
        _household_column(),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("amount_quarters", sa.Integer(), server_default="4", nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=True),
        sa.Column("member_login_id", sa.Integer(), nullable=True),
        sa.Column("use_by", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount_quarters >= 0 AND amount_quarters <= 4",
            name=op.f("ck_tub_quarters_range"),
        ),
        _household_key("tub"),
        sa.ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["batch_cook.household_id", "batch_cook.id"],
            name="fk_tub_household_id_batch_cook",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["place.id"], name=op.f("fk_tub_place_id_place"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["member_login_id"],
            ["login.id"],
            name=op.f("fk_tub_member_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tub")),
        sa.UniqueConstraint("household_id", "id", name=op.f("uq_tub_household_id_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("tub", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tub_household_id"), ["household_id"])
        batch_op.create_index("ix_tub_household_id_batch_id", ["household_id", "batch_id"])

    op.create_table(
        "meal_item",
        sa.Column("id", sa.Integer(), nullable=False),
        _household_column(),
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("tub_id", sa.Integer(), nullable=True),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(CASE WHEN recipe_id IS NULL THEN 0 ELSE 1 END)"
            " + (CASE WHEN tub_id IS NULL THEN 0 ELSE 1 END)"
            " + (CASE WHEN food_id IS NULL THEN 0 ELSE 1 END) = 1",
            name=op.f("ck_meal_item_one_of"),
        ),
        sa.CheckConstraint(
            "servings IS NULL OR (recipe_id IS NOT NULL AND servings >= 1 AND servings <= 99)",
            name=op.f("ck_meal_item_servings_range"),
        ),
        _household_key("meal_item"),
        sa.ForeignKeyConstraint(
            ["household_id", "meal_id"],
            ["meal.household_id", "meal.id"],
            name="fk_meal_item_household_id_meal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "tub_id"],
            ["tub.household_id", "tub.id"],
            name="fk_meal_item_household_id_tub",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_meal_item_recipe_id_recipe"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_meal_item_food_id_food"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_item")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("meal_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_item_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_meal_item_recipe_id"), ["recipe_id"])
        batch_op.create_index(batch_op.f("ix_meal_item_food_id"), ["food_id"])
        batch_op.create_index(
            "ix_meal_item_household_id_meal_id", ["household_id", "meal_id", "position"]
        )
        batch_op.create_index("uq_meal_item_tub_id", ["tub_id"], unique=True)

    # The four default slots for every household that already exists.
    slot = sa.table(
        "meal_slot",
        sa.column("household_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("position", sa.Integer),
        sa.column("enabled", sa.Boolean),
    )
    households = op.get_bind().execute(sa.text("SELECT id FROM household")).scalars().all()
    rows = [
        {"household_id": household, "name": name, "position": position, "enabled": enabled}
        for household in households
        for position, (name, enabled) in enumerate(DEFAULT_SLOTS)
    ]
    if rows:
        op.bulk_insert(slot, rows)


def downgrade() -> None:
    for table in ("meal_item", "tub", "batch_cook", "meal", "meal_slot"):
        op.drop_table(table)  # their indexes go with them

    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("week_starts_on")
        batch_op.drop_column("plan_ahead_days")
        batch_op.drop_column("tub_freezer_months")
        batch_op.drop_column("tub_fridge_days")
