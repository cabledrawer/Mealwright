"""never reuse place and shop ids

Revision ID: d4f8b2c1a695
Revises: c7e2f4a9b816
Create Date: 2026-11-08 12:00:00

Places and shops can be removed (0.8), and without "never reuse an id" the next place or shop
made, in any household, was given the id of a removed one: an Undo then put back a pointer to
somebody else's row. The two tables are rebuilt with `AUTOINCREMENT`, as the other tables that
have an Undo already are. Every row, id, index and link stays as it was; only new ids change
(a removed id is never used again). Going back rebuilds them without it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4f8b2c1a695"
down_revision: str | Sequence[str] | None = "c7e2f4a9b816"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("place", "shop")


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
