"""add places and shops

Revision ID: e9d1bba1c1d5
Revises: bd0934bde61f
Create Date: 2026-10-17 19:30:00

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "e9d1bba1c1d5"
down_revision: str | Sequence[str] | None = "bd0934bde61f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copied, not imported, so this migration never changes when the app does.
DEFAULT_PLACES = (
    ("Fridge", "fridge"),
    ("Freezer", "freezer"),
    ("Cupboard", "cupboard"),
    ("Spice rack", "cupboard"),
)


def upgrade() -> None:
    op.create_table(
        "place",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_place_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_place")),
    )
    with op.batch_alter_table("place", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_place_household_id"), ["household_id"], unique=False)

    op.create_table(
        "shop",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("aisle_order", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_shop_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shop")),
    )
    with op.batch_alter_table("shop", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_shop_household_id"), ["household_id"], unique=False)

    # The four default places for every household (spec section 6, "Decided for 0.2").
    place = sa.table(
        "place",
        sa.column("household_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("kind", sa.String),
        sa.column("position", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    households = op.get_bind().execute(sa.text("SELECT id FROM household")).scalars().all()
    rows = [
        {
            "household_id": household,
            "name": name,
            "kind": kind,
            "position": position,
            "created_at": now,
        }
        for household in households
        for position, (name, kind) in enumerate(DEFAULT_PLACES)
    ]
    if rows:
        op.bulk_insert(place, rows)


def downgrade() -> None:
    with op.batch_alter_table("shop", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_shop_household_id"))

    op.drop_table("shop")

    with op.batch_alter_table("place", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_place_household_id"))

    op.drop_table("place")
