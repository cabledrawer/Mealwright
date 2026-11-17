"""never reuse change_line and food_merge ids

Revision ID: e5b9c3a7d1f2
Revises: d7a3e1b5c924
Create Date: 2026-11-17 14:00:00

B7 low (proposed, for cabledrawer): a stock change's lines and an ingredient's merge history are
looked up by number when something is undone, and without "never reuse an id" the next row made
could take the number of one that was deleted (history thinning removes old lines). The two
tables are rebuilt with `AUTOINCREMENT`, as `place` and `shop` were (d4f8b2c1a695). Every row,
id, index and link stays as it was; only new ids change (the counter starts at the highest id
left, so a top id deleted before this upgrade can come back once). Nothing points at either
table. Going back rebuilds them without it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5b9c3a7d1f2"
down_revision: str | Sequence[str] | None = "d7a3e1b5c924"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("change_line", "food_merge")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(
            table, schema=None, recreate="always", table_kwargs={"sqlite_autoincrement": True}
        ):
            pass


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None, recreate="always"):
            pass
