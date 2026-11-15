"""the hash of a change's request body

Revision ID: c4f7a2d9e816
Revises: c6a1f3b9d805
Create Date: 2026-11-15 12:00:00

0.9.5 step 11: `change.body_hash`, the SHA-256 of the request body, so a request sent again
with the same Idempotency-Key but a different body is refused (409 key_reused) instead of being
answered as already done. Every existing change has it empty and is checked by method and path
alone, as before. Going back drops the column and loses only the hashes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f7a2d9e816"
down_revision: str | Sequence[str] | None = "c6a1f3b9d805"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.add_column(sa.Column("body_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.drop_column("body_hash")
