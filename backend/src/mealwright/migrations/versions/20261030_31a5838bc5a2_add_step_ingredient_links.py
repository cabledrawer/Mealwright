"""add step ingredient links

Revision ID: 31a5838bc5a2
Revises: b89c3c1918f8
Create Date: 2026-10-30 23:30:00

Which ingredient lines each method step uses (0.7 K1; spec section 6 gaps, "Cook mode
ingredients", cabledrawer 17 Oct: "Data model: step ↔ ingredient links, each marked guessed or set
by hand").

- New table `recipe_step_line`: a step, a line of the same recipe, and `kind`, "guessed" or
  "by_hand". It belongs to a household, and its links to the step and the line are composite
  keys that include `household_id`, so a link can never join two households. It goes with its
  step or its line.
- `recipe_step` and `recipe_line` get a unique (household_id, id), which those keys need.
  Nothing else about them changes.

Going back drops the table and the two unique keys. The only loss is the links.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "31a5838bc5a2"
down_revision: str | Sequence[str] | None = "b89c3c1918f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite adds a unique key by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    for table in ("recipe_line", "recipe_step"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.create_unique_constraint(
                batch_op.f(f"uq_{table}_household_id_id"), ["household_id", "id"]
            )
    op.create_table(
        "recipe_step_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "kind IN ('guessed', 'by_hand')", name=op.f("ck_recipe_step_line_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_recipe_step_line_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "step_id"],
            ["recipe_step.household_id", "recipe_step.id"],
            name="fk_recipe_step_line_household_id_recipe_step",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "line_id"],
            ["recipe_line.household_id", "recipe_line.id"],
            name="fk_recipe_step_line_household_id_recipe_line",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_step_line")),
        sa.UniqueConstraint("step_id", "line_id", name=op.f("uq_recipe_step_line_step_id_line_id")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("recipe_step_line", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_recipe_step_line_household_id"), ["household_id"])
        batch_op.create_index("ix_recipe_step_line_line_id", ["line_id"])


def downgrade() -> None:
    op.drop_table("recipe_step_line")
    for table in ("recipe_step", "recipe_line"):
        with op.batch_alter_table(table, schema=None, table_kwargs=_KEEP) as batch_op:
            batch_op.drop_constraint(batch_op.f(f"uq_{table}_household_id_id"), type_="unique")
