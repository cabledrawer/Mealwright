"""add recipe methods

Revision ID: f1a6d3c8e502
Revises: e8a3c5b1d7f9
Create Date: 2026-11-10 20:00:00

Two cooking methods (0.8 wave 5, M2; cabledrawer 31 Oct and 9 Nov).

- `recipe_method`: a recipe has one method or two, each with a name, its own time and a
  `last_used_at` (the one used last is pre-picked when the recipe is planned). Every existing
  recipe gets one method (position 0, no name) holding its time; its lines and steps are put in
  it, so nothing is lost and nothing reads differently. The recipe's own `time_minutes` stays,
  equal to the first method's time, so old readers still find it.
- `recipe_line.method_id` and `recipe_step.method_id`: the method a line or step is in. Null
  means the recipe's first method (code that doesn't know about methods keeps working).
- `meal_item.method_id`: the method a planned recipe will be cooked with. Empty to begin with:
  a meal made before this uses the recipe's first method, which is its only one.

Going back drops the column and the table. What is lost: the second method of any recipe that
has one (its lines and steps are deleted, so the first method is left as the recipe), the
method names and times of the second, and each planned meal's pick.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a6d3c8e502"
down_revision: str | Sequence[str] | None = "e8a3c5b1d7f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite drops a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    op.create_table(
        "recipe_method",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), server_default="", nullable=False),
        sa.Column("time_minutes", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("position IN (0, 1)", name=op.f("ck_recipe_method_position_known")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_recipe_method_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_recipe_method_recipe_id_recipe"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_method")),
        sa.UniqueConstraint("recipe_id", "position", name="uq_recipe_method_recipe_id_position"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("recipe_method", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_recipe_method_household_id"), ["household_id"])

    for table in ("recipe_line", "recipe_step"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.add_column(sa.Column("method_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                batch_op.f(f"fk_{table}_method_id_recipe_method"),
                "recipe_method",
                ["method_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(batch_op.f(f"ix_{table}_method_id"), ["method_id"])
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("method_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_meal_item_method_id_recipe_method"),
            "recipe_method",
            ["method_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_meal_item_method_id"), ["method_id"])

    # Every recipe becomes a recipe with one method that holds its time, lines and steps.
    op.execute(
        "INSERT INTO recipe_method (household_id, recipe_id, position, name, time_minutes)"
        " SELECT household_id, id, 0, '', time_minutes FROM recipe ORDER BY id"
    )
    # Written out for each table: no SQL is built from strings (Bandit B608).
    op.execute(
        "UPDATE recipe_line SET method_id = (SELECT m.id FROM recipe_method m"
        " WHERE m.recipe_id = recipe_line.recipe_id AND m.position = 0)"
    )
    op.execute(
        "UPDATE recipe_step SET method_id = (SELECT m.id FROM recipe_method m"
        " WHERE m.recipe_id = recipe_step.recipe_id AND m.position = 0)"
    )


def downgrade() -> None:
    # The second method of a recipe goes, with its lines and steps. Its ingredient links go too.
    op.execute(
        "DELETE FROM recipe_step_line WHERE step_id IN (SELECT s.id FROM recipe_step s"
        " JOIN recipe_method m ON m.id = s.method_id WHERE m.position = 1)"
        " OR line_id IN (SELECT l.id FROM recipe_line l"
        " JOIN recipe_method m ON m.id = l.method_id WHERE m.position = 1)"
    )
    op.execute(
        "DELETE FROM recipe_step WHERE method_id IN"
        " (SELECT id FROM recipe_method WHERE position = 1)"
    )
    op.execute(
        "DELETE FROM recipe_line WHERE method_id IN"
        " (SELECT id FROM recipe_method WHERE position = 1)"
    )
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meal_item_method_id"))
        batch_op.drop_constraint(batch_op.f("fk_meal_item_method_id_recipe_method"), "foreignkey")
        batch_op.drop_column("method_id")
    for table in ("recipe_step", "recipe_line"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table}_method_id"))
            batch_op.drop_constraint(
                batch_op.f(f"fk_{table}_method_id_recipe_method"), "foreignkey"
            )
            batch_op.drop_column("method_id")
    op.drop_table("recipe_method")
