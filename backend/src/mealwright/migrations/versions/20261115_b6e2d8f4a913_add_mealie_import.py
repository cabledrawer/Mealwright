"""add Import from Mealie: the import record, and which ingredients and drafts it made

Revision ID: b6e2d8f4a913
Revises: b8e2d4f6a913
Create Date: 2026-11-15 09:00:00

0.9.5 Import from Mealie (cabledrawer 13 Nov). New table `mealie_import` (household_id, state,
the stored file's name and key, the preview, the choices, progress and results, who started it
and when). `food.mealie_import_id` and `import_draft.mealie_import_id` say which import made an
ingredient or a draft ("from Mealie", the Drafts filter, and the import's one Undo), and a draft
may now be `source_kind` 'mealie'.

Going back: the Mealie drafts are deleted (their photos with them, by the hourly tidy-up of
photos with no record), the two columns and the table are dropped. Recipes and ingredients an
import made stay as they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e2d8f4a913"
down_revision: str | Sequence[str] | None = "b8e2d4f6a913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite changes a table by copying it; this keeps "never reuse an id" on the copy.
_KEEP = {"sqlite_autoincrement": True}


def upgrade() -> None:
    op.create_table(
        "mealie_import",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("file_key", sa.String(length=64), nullable=True),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("started_by_login_id", sa.Integer(), nullable=True),
        sa.Column("started_by_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('ready', 'running', 'done', 'failed', 'undone', 'gone')",
            name=op.f("ck_mealie_import_state_known"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_mealie_import_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_login_id"],
            ["login.id"],
            name=op.f("fk_mealie_import_started_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mealie_import")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("mealie_import", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mealie_import_household_id"), ["household_id"], unique=False
        )
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("mealie_import_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_food_mealie_import_id"), ["mealie_import_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_food_mealie_import_id_mealie_import"),
            "mealie_import",
            ["mealie_import_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("import_draft", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.add_column(sa.Column("mealie_import_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_import_draft_mealie_import_id"), ["mealie_import_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_import_draft_mealie_import_id_mealie_import"),
            "mealie_import",
            ["mealie_import_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(batch_op.f("ck_import_draft_source_kind_known"), type_="check")
        batch_op.create_check_constraint(
            batch_op.f("ck_import_draft_source_kind_known"),
            "source_kind IN ('link', 'text', 'mealie')",
        )


def downgrade() -> None:
    op.execute("UPDATE recipe_photo SET draft_id = NULL WHERE draft_id IN"
               " (SELECT id FROM import_draft WHERE source_kind = 'mealie')")  # fmt: skip
    op.execute("DELETE FROM import_draft WHERE source_kind = 'mealie'")
    with op.batch_alter_table("import_draft", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_import_draft_source_kind_known"), type_="check")
        batch_op.create_check_constraint(
            batch_op.f("ck_import_draft_source_kind_known"), "source_kind IN ('link', 'text')"
        )
        batch_op.drop_constraint(
            batch_op.f("fk_import_draft_mealie_import_id_mealie_import"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_import_draft_mealie_import_id"))
        batch_op.drop_column("mealie_import_id")
    with op.batch_alter_table("food", schema=None, table_kwargs=_KEEP) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_food_mealie_import_id_mealie_import"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_food_mealie_import_id"))
        batch_op.drop_column("mealie_import_id")
    with op.batch_alter_table("mealie_import", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mealie_import_household_id"))
    op.drop_table("mealie_import")
