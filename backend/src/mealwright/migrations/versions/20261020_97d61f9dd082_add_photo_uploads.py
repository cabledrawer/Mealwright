"""add photo uploads

Revision ID: 97d61f9dd082
Revises: c5e8a1f3b7d2
Create Date: 2026-10-20 09:00:00

A photo is uploaded before its recipe is saved (cabledrawer 20 Oct), so a photo record can be
without a recipe for a while, and each photo now has a second, smaller copy for the list.

- recipe_photo.recipe_id may be empty (an upload not saved on a recipe yet).
- recipe_photo.list_width and list_height: the size of the list copy. A record made before
  this (there can't be any with files: 0.4's first pull request had no way to upload)
  gets 0 and 0.

Going back deletes the uploads that aren't on a recipe, because the older table needs a
recipe on every photo. Their files stay in the data folder until the newer version's
hourly job finds them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "97d61f9dd082"
down_revision: str | Sequence[str] | None = "c5e8a1f3b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite changes a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    with op.batch_alter_table("recipe_photo", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.alter_column("recipe_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(
            sa.Column("list_width", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("list_height", sa.Integer(), nullable=False, server_default="0")
        )
    # The 0 was only for rows already there; new rows always give the size.
    with op.batch_alter_table("recipe_photo", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.alter_column("list_width", existing_type=sa.Integer(), server_default=None)
        batch_op.alter_column("list_height", existing_type=sa.Integer(), server_default=None)


def downgrade() -> None:
    op.execute("DELETE FROM recipe_photo WHERE recipe_id IS NULL")
    with op.batch_alter_table("recipe_photo", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_column("list_height")
        batch_op.drop_column("list_width")
        batch_op.alter_column("recipe_id", existing_type=sa.Integer(), nullable=False)
