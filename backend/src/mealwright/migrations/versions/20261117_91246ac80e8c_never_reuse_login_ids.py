"""never reuse login ids

Revision ID: 91246ac80e8c
Revises: c30b3fee4849
Create Date: 2026-11-17 12:00:00

D1/S5 (cabledrawer 13 Nov): login numbers are never reused, not even after Delete everything.
Without
"never reuse an id", the first login made after Delete everything (or after the newest login was
removed) was given the number of the one gone: anything that still named that number (a sign-in
in another browser's memory, a log line, a backup) would point at somebody else. The table is
rebuilt with `AUTOINCREMENT`, as the tables with an Undo already are. Every row, id, index and
link stays as it was; only new ids change (the counter starts at the highest id left). Going
back rebuilds it without.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "91246ac80e8c"
down_revision: str | Sequence[str] | None = "c30b3fee4849"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table(
        "login", schema=None, recreate="always", table_kwargs={"sqlite_autoincrement": True}
    ):
        pass


def downgrade() -> None:
    with op.batch_alter_table("login", schema=None, recreate="always"):
        pass
