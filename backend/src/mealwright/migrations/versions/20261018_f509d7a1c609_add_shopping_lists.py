"""add shopping lists

Revision ID: f509d7a1c609
Revises: a7c3e51d9b02
Create Date: 2026-10-18 00:28:29.910335

"""

import csv
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.resources import files

import sqlalchemy as sa
from alembic import op

revision: str = "f509d7a1c609"
down_revision: str | Sequence[str] | None = "a7c3e51d9b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_list",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("main", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_name", sa.String(length=100), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_action_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_shopping_list_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_list")),
    )
    with op.batch_alter_table("shopping_list", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_shopping_list_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(
            "uq_shopping_list_one_main",
            ["household_id"],
            unique=True,
            sqlite_where=sa.text("main"),
            postgresql_where=sa.text("main"),
        )

    # Every existing household gets its main list, "This week" (sync protocol 3.1).
    connection = op.get_bind()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    for (household_id,) in connection.execute(sa.text("SELECT id FROM household")).fetchall():
        connection.execute(
            sa.text(
                "INSERT INTO shopping_list (id, household_id, name, main, position, created_at,"
                " created_by_name, version) VALUES (:id, :household_id, 'This week', :main, 0,"
                " :now, '', 0)"
            ).bindparams(sa.bindparam("main", type_=sa.Boolean())),
            {"id": str(uuid.uuid4()), "household_id": household_id, "main": True, "now": now},
        )

    op.create_table(
        "list_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=True),
        sa.Column("amount_milli", sa.BigInteger(), nullable=True),
        sa.Column("size_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("hand_edited", sa.Boolean(), nullable=False),
        sa.Column("put_away_place_id", sa.Integer(), nullable=True),
        sa.Column("ticked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ticked_by_login_id", sa.Integer(), nullable=True),
        sa.Column("ticked_by_name", sa.String(length=100), nullable=True),
        sa.Column("ticked_device_id", sa.String(length=36), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by_login_id", sa.Integer(), nullable=True),
        sa.Column("added_by_name", sa.String(length=100), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_name", sa.String(length=100), nullable=True),
        sa.Column("deleted_action_id", sa.String(length=64), nullable=True),
        sa.Column("merged_into_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_login_id"],
            ["login.id"],
            name=op.f("fk_list_item_added_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["food_id"], ["food.id"], name=op.f("fk_list_item_food_id_food")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_list_item_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_list.id"],
            name=op.f("fk_list_item_list_id_shopping_list"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["put_away_place_id"],
            ["place.id"],
            name=op.f("fk_list_item_put_away_place_id_place"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shop.id"], name=op.f("fk_list_item_shop_id_shop"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["size_id"],
            ["food_size.id"],
            name=op.f("fk_list_item_size_id_food_size"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticked_by_login_id"],
            ["login.id"],
            name=op.f("fk_list_item_ticked_by_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_item")),
    )
    with op.batch_alter_table("list_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_list_item_food_id"), ["food_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_list_item_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(
            "ix_list_item_household_id_list_id_food_id_shop_id",
            ["household_id", "list_id", "food_id", "shop_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_list_item_household_id_version", ["household_id", "version"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_list_item_list_id"), ["list_id"], unique=False)

    op.create_table(
        "sync_action",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=True),
        sa.Column("login_name", sa.String(length=100), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("list_id", sa.String(length=36), nullable=True),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("seen", sa.BigInteger(), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("undone_by_action_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_sync_action_change_id_change"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_sync_action_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"],
            ["login.id"],
            name=op.f("fk_sync_action_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("household_id", "id", name=op.f("pk_sync_action")),
        sa.UniqueConstraint("household_id", "seq", name=op.f("uq_sync_action_household_id")),
    )
    with op.batch_alter_table("sync_action", schema=None) as batch_op:
        batch_op.create_index(
            "ix_sync_action_household_id_item_id_seq",
            ["household_id", "item_id", "seq"],
            unique=False,
        )

    op.create_table(
        "double_tick",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("tick_ids", sa.JSON(), nullable=False),
        sa.Column("login_ids", sa.JSON(), nullable=False),
        sa.Column("same_login", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer", sa.String(length=10), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by_name", sa.String(length=100), nullable=True),
        sa.Column("answer_action_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_double_tick_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["list_item.id"],
            name=op.f("fk_double_tick_item_id_list_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_list.id"],
            name=op.f("fk_double_tick_list_id_shopping_list"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_double_tick")),
    )
    with op.batch_alter_table("double_tick", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_double_tick_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_double_tick_list_id"), ["list_id"], unique=False)

    op.create_table(
        "list_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("for_login_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("undo_action_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"], ["food.id"], name=op.f("fk_list_note_food_id_food"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["for_login_id"],
            ["login.id"],
            name=op.f("fk_list_note_for_login_id_login"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_list_note_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["list_item.id"],
            name=op.f("fk_list_note_item_id_list_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_list.id"],
            name=op.f("fk_list_note_list_id_shopping_list"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_note")),
    )
    with op.batch_alter_table("list_note", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_list_note_household_id"), ["household_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_list_note_list_id"), ["list_id"], unique=False)

    op.create_table(
        "list_tick",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=True),
        sa.Column("login_name", sa.String(length=100), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("ticked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=True),
        sa.Column("bought_milli", sa.BigInteger(), nullable=True),
        sa.Column("bought_size_id", sa.Integer(), nullable=True),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by_action_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["bought_size_id"],
            ["food_size.id"],
            name=op.f("fk_list_tick_bought_size_id_food_size"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change.id"],
            name=op.f("fk_list_tick_change_id_change"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_list_tick_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["list_item.id"],
            name=op.f("fk_list_tick_item_id_list_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"],
            ["login.id"],
            name=op.f("fk_list_tick_login_id_login"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["place.id"],
            name=op.f("fk_list_tick_place_id_place"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("household_id", "id", name=op.f("pk_list_tick")),
    )
    with op.batch_alter_table("list_tick", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_list_tick_item_id"), ["item_id"], unique=False)

    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tick_id", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "ix_change_household_id_tick_id", ["household_id", "tick_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_change_household_id_list_tick",
            "list_tick",
            ["household_id", "tick_id"],
            ["household_id", "id"],
        )

    with op.batch_alter_table("food", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aisle", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column("version", sa.BigInteger(), server_default="0", nullable=False)
        )

    # Starting aisles for ingredients that already exist: only where the ingredient is
    # already linked to a row of the bundled table (0.2 stored that link in food.table_key
    # by exact name). No guessing; everything else stays empty and shows under Other.
    source = files("mealwright") / "data" / "food-conversions.csv"
    with source.open(encoding="utf-8") as handle:
        rows = csv.DictReader(line for line in handle if not line.startswith("#"))
        aisles = {row["key"]: row["aisle"] for row in rows if row.get("aisle")}
    connection = op.get_bind()
    for key, aisle in aisles.items():
        connection.execute(
            sa.text("UPDATE food SET aisle = :aisle WHERE table_key = :key AND aisle IS NULL"),
            {"aisle": aisle, "key": key},
        )

    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("list_seq", sa.BigInteger(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("list_purged_seq", sa.BigInteger(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("household", schema=None) as batch_op:
        batch_op.drop_column("list_purged_seq")
        batch_op.drop_column("list_seq")

    with op.batch_alter_table("food", schema=None) as batch_op:
        batch_op.drop_column("version")
        batch_op.drop_column("aisle")

    with op.batch_alter_table("change", schema=None) as batch_op:
        batch_op.drop_constraint("fk_change_household_id_list_tick", type_="foreignkey")
        batch_op.drop_index("ix_change_household_id_tick_id")
        batch_op.drop_column("tick_id")

    with op.batch_alter_table("list_tick", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_tick_item_id"))

    op.drop_table("list_tick")
    with op.batch_alter_table("list_note", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_note_list_id"))
        batch_op.drop_index(batch_op.f("ix_list_note_household_id"))

    op.drop_table("list_note")
    with op.batch_alter_table("double_tick", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_double_tick_list_id"))
        batch_op.drop_index(batch_op.f("ix_double_tick_household_id"))

    op.drop_table("double_tick")
    with op.batch_alter_table("sync_action", schema=None) as batch_op:
        batch_op.drop_index("ix_sync_action_household_id_item_id_seq")

    op.drop_table("sync_action")
    with op.batch_alter_table("list_item", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_item_list_id"))
        batch_op.drop_index("ix_list_item_household_id_version")
        batch_op.drop_index("ix_list_item_household_id_list_id_food_id_shop_id")
        batch_op.drop_index(batch_op.f("ix_list_item_household_id"))
        batch_op.drop_index(batch_op.f("ix_list_item_food_id"))

    op.drop_table("list_item")
    with op.batch_alter_table("shopping_list", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_shopping_list_one_main",
            sqlite_where=sa.text("main"),
            postgresql_where=sa.text("main"),
        )
        batch_op.drop_index(batch_op.f("ix_shopping_list_household_id"))

    op.drop_table("shopping_list")
