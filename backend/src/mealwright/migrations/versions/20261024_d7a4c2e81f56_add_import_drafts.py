"""add import drafts

Revision ID: d7a4c2e81f56
Revises: 5b2e9d41a7c3
Create Date: 2026-10-24 01:40:00

Drafts (spec section 6, "Drafts (cabledrawer 21 Oct)"; the database change was approved by cabledrawer
on 22 Oct: "drafts table, photo -> draft", nothing else).

- A new table, `import_draft`: an import left unfinished. It belongs to a household, and keeps
  the link or pasted text, what Mealwright read, the choices made so far, who started it, when
  it was last changed and (when it is deleted) when it was hidden.
- `recipe_photo.draft_id`: the draft that is keeping a downloaded photo. Empty for every photo
  already there.

Going back drops the table and the column, and deletes the photo records the drafts held (the
older version has no draft to hold them). Their files stay in the data folder until the older
version's hourly job finds them. Recipes, their photos and everything else are kept.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a4c2e81f56"
down_revision: str | Sequence[str] | None = "5b2e9d41a7c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite changes a column by copying the table; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    op.create_table(
        "import_draft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=8), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("site", sa.String(length=253), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("review", sa.JSON(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("lines_total", sa.Integer(), nullable=False),
        sa.Column("lines_checked", sa.Integer(), nullable=False),
        sa.Column("started_by_login_id", sa.Integer(), nullable=True),
        sa.Column("started_by_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('link', 'text')", name=op.f("ck_import_draft_source_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_import_draft_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_login_id"],
            ["login.id"],
            name=op.f("fk_import_draft_started_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_draft")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("import_draft", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_import_draft_household_id"), ["household_id"], unique=False
        )

    with op.batch_alter_table("recipe_photo", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("draft_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_recipe_photo_draft_id"), ["draft_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_recipe_photo_draft_id_import_draft"),
            "import_draft",
            ["draft_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.execute("DELETE FROM recipe_photo WHERE draft_id IS NOT NULL")
    with op.batch_alter_table("recipe_photo", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_recipe_photo_draft_id_import_draft"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_recipe_photo_draft_id"))
        batch_op.drop_column("draft_id")

    with op.batch_alter_table("import_draft", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_import_draft_household_id"))

    op.drop_table("import_draft")
