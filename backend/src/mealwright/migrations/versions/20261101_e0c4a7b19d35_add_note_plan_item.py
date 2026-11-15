"""add note plan item

Revision ID: e0c4a7b19d35
Revises: 6612736d5aae
Create Date: 2026-11-01 09:00:00

A "Note" plan item (0.7 P1; spec, "From the 28 Oct review of v0.6.0": eating out, takeaway, "at
Tess's"). A meal item may now be of kind `note`: no recipe, tub or ingredient, only its text in
`name`. Only the "exactly one of" rule on `meal_item` changes; no row and no column.

Going back removes the notes (the old rule would refuse them) and any meal that held nothing
else. The only loss is the notes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e0c4a7b19d35"
down_revision: str | Sequence[str] | None = "6612736d5aae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite changes a rule by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}

_BEFORE = (
    "(kind = 'recipe' AND tub_id IS NULL AND food_id IS NULL"
    " AND (recipe_id IS NOT NULL OR name IS NOT NULL))"
    " OR (kind = 'ingredient' AND recipe_id IS NULL AND tub_id IS NULL"
    " AND (food_id IS NOT NULL OR name IS NOT NULL))"
    " OR (kind = 'tub' AND tub_id IS NOT NULL AND recipe_id IS NULL AND food_id IS NULL)"
)
_AFTER = (
    _BEFORE + " OR (kind = 'note' AND recipe_id IS NULL AND tub_id IS NULL AND food_id IS NULL"
    " AND name IS NOT NULL)"
)


def _swap(rule: str) -> None:
    with op.batch_alter_table("meal_item", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_meal_item_one_of"), type_="check")
        batch_op.create_check_constraint(batch_op.f("ck_meal_item_one_of"), rule)


def upgrade() -> None:
    _swap(_AFTER)


def downgrade() -> None:
    # A batch cooked for a meal that held only a note (its recipe was taken out since) forgets
    # the link first, as `delete_meal` does: the database refuses to delete a meal it points at.
    op.execute(
        "UPDATE batch_cook SET cook_meal_id = NULL WHERE cook_meal_id IN"
        " (SELECT meal_id FROM meal_item WHERE kind = 'note')"
        " AND cook_meal_id NOT IN (SELECT meal_id FROM meal_item WHERE kind != 'note')"
    )
    # A meal the notes were the only thing in goes (with its notes); the other notes go next.
    op.execute(
        "DELETE FROM meal WHERE id IN (SELECT meal_id FROM meal_item WHERE kind = 'note')"
        " AND id NOT IN (SELECT meal_id FROM meal_item WHERE kind != 'note')"
    )
    op.execute("DELETE FROM meal_item WHERE kind = 'note'")
    _swap(_BEFORE)
