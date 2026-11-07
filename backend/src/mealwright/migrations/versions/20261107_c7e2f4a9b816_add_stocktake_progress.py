"""add stocktake progress

Revision ID: c7e2f4a9b816
Revises: a8c3e5f71d24
Create Date: 2026-11-07 15:00:00

The Stocktake (0.8, F118, cabledrawer 7 Nov): its progress is kept on the server for the household,
so it carries on from any phone and anyone in the household can finish it. Two small tables:

- `stocktake_place`: the places whose stocktake is finished.
- `stocktake_entry`: each ingredient looked at in a place (answered, or only added there).

Going back drops both tables. The only loss is a stocktake that was started and not finished
(the stock counted so far stays).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2f4a9b816"
down_revision: str | Sequence[str] | None = "a8c3e5f71d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocktake_place",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_stocktake_place_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["place.id"],
            name=op.f("fk_stocktake_place_place_id_place"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("household_id", "place_id", name=op.f("pk_stocktake_place")),
    )
    op.create_table(
        "stocktake_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("answered", sa.Boolean(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_stocktake_entry_change_id_change"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["food.id"],
            name=op.f("fk_stocktake_entry_food_id_food"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_stocktake_entry_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["place.id"],
            name=op.f("fk_stocktake_entry_place_id_place"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stocktake_entry")),
        sa.UniqueConstraint("place_id", "food_id", name=op.f("uq_stocktake_entry_place_id")),
    )
    with op.batch_alter_table("stocktake_entry", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stocktake_entry_household_id"), ["household_id"])


def downgrade() -> None:
    op.drop_table("stocktake_entry")  # its index goes with it
    op.drop_table("stocktake_place")
