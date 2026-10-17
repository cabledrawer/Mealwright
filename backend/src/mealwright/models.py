"""Database tables.

Every table belongs to a household (`household_id`), so more than one household per
install stays possible later. The household table's own `id` is that household_id.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from mealwright.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Household(Base):
    __tablename__ = "household"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Household settings (docs/dev/api-0.2.md section 3.1). Changeable in Settings (0.8).
    # IANA time zone from the admin's browser, never location. Null: not known yet (UTC).
    time_zone: Mapped[str | None] = mapped_column(String(64))
    # 240 or 250 ml. Null: not chosen yet, 250 is used.
    cup_ml: Mapped[int | None] = mapped_column(Integer)
    undo_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    history_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    use_soon_days: Mapped[int] = mapped_column(Integer, default=2, server_default="2")


class OutboundSwitch(Base):
    """A Privacy switch for one kind of outside connection (Settings → Privacy).

    No row means the switch is off: everything starts off, and stays off until
    the household switches it on.
    """

    __tablename__ = "outbound_switch"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    connection: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Login(Base):
    """Someone who can sign in. Separate from member profiles (0.8), which can exist
    without a login (spec section 3)."""

    __tablename__ = "login"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    # Stored lowercase; unique across the install.
    username: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    # Argon2 hash. Empty for logins that only use single sign-on (0.8).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10))  # "admin" or "member"
    theme: Mapped[str] = mapped_column(String(10), default="auto")  # auto, light, dark
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    """A signed-in device. The cookie holds a random token; only its SHA-256 is stored,
    so a copy of the database can't be used to sign in."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    login_id: Mapped[int] = mapped_column(ForeignKey("login.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    remember: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# --- Places and shops ------------------------------------------------------------------------


class Place(Base):
    """Where food lives at home. `kind` drives the rules (freezer last, To freezer), so
    renaming a place never breaks them."""

    __tablename__ = "place"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))  # fridge, freezer, cupboard
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


DEFAULT_PLACES = (
    ("Fridge", "fridge"),
    ("Freezer", "freezer"),
    ("Cupboard", "cupboard"),
    ("Spice rack", "cupboard"),
)


class Shop(Base):
    __tablename__ = "shop"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    # The shop's aisle order (0.3). Null: the default order.
    aisle_order: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- Foods -------------------------------------------------------------------------------------
# Ids are never reused (sqlite_autoincrement), so Undo can put a deleted row back with its
# old id without clashing with a newer one.


class Food(Base):
    """One thing you buy and cook with. Amounts are in thousandths of the base unit (g, ml
    or items); see mealwright.amounts."""

    __tablename__ = "food"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    counted_as: Mapped[str] = mapped_column(String(10))  # weight, volume, count
    staple: Mapped[bool] = mapped_column(Boolean, default=False)
    count_word: Mapped[str | None] = mapped_column(String(30))
    count_word_plural: Mapped[str | None] = mapped_column(String(30))
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shop.id", ondelete="SET NULL"))
    running_low_milli: Mapped[int | None] = mapped_column(BigInteger)
    # The bundled conversion table row this food's names match, if any.
    table_key: Mapped[str | None] = mapped_column(String(80))
    # Set when merged into another food: hidden, but kept so old links still resolve.
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("food.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FoodName(Base):
    """Another name for a food (thuvaram paruppu, arhar dal → toor dal)."""

    __tablename__ = "food_name"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))


class FoodSize(Base):
    """A way a food is sold: packet = 500 g, dozen = 12, loaf = 20 slices."""

    __tablename__ = "food_size"
    __table_args__ = (
        CheckConstraint("amount_milli > 0", name="amount_positive"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    plural: Mapped[str] = mapped_column(String(40))
    amount_milli: Mapped[int] = mapped_column(BigInteger)
    usual: Mapped[bool] = mapped_column(Boolean, default=False)
    added_when_shopping: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class FoodStandIn(Base):
    """ "Can use instead": `stand_in_id` can stand in for `food_id`. One way."""

    __tablename__ = "food_stand_in"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )
    stand_in_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )


class FoodConversion(Base):
    """The household's own "ask once" answer for a food. Always wins over the bundled
    table; app updates never touch it."""

    __tablename__ = "food_conversion"
    __table_args__ = (
        UniqueConstraint("food_id", "kind"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # weight_per_ml, item_weight
    # mg per ml, or mg per item.
    value_milli: Mapped[int] = mapped_column(BigInteger)
    answered_by_name: Mapped[str] = mapped_column(String(100))
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FoodNotSame(Base):
    """ "Not the same": a pair of foods never shown as "Maybe the same" again."""

    __tablename__ = "food_not_same"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_a_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )
    food_b_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )


# --- History ------------------------------------------------------------------------------------


class Change(Base):
    """One thing someone did: one row in Recent changes, one Undo button."""

    __tablename__ = "change"
    __table_args__ = (UniqueConstraint("household_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    # The client-made ID (Idempotency-Key), so a retried request isn't applied twice.
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    request: Mapped[str] = mapped_column(String(200), default="")  # "POST /api/v1/foods"
    kind: Mapped[str] = mapped_column(String(20))
    login_id: Mapped[int | None] = mapped_column(ForeignKey("login.id", ondelete="SET NULL"))
    login_name: Mapped[str] = mapped_column(String(100))
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("food.id", ondelete="SET NULL"), index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    summary: Mapped[str] = mapped_column(String(300))
    undo_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Indexed: deleting old changes checks these links, and without an index every
    # deleted row would scan the whole table.
    undone_by_change_id: Mapped[int | None] = mapped_column(ForeignKey("change.id"), index=True)
    undoes_change_id: Mapped[int | None] = mapped_column(ForeignKey("change.id"), index=True)


class FoodMerge(Base):
    """Merge history: old links to `from_food_id` resolve to the food it went into."""

    __tablename__ = "food_merge"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    from_food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"))
    into_food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"))
    change_id: Mapped[int | None] = mapped_column(
        ForeignKey("change.id", ondelete="SET NULL"), index=True
    )
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    split_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Stock ------------------------------------------------------------------------------------


class StockLot(Base):
    """One packet, one bag of spinach, one tray of eggs: each kept on its own, so the one
    that goes off first is used first (spec section 6, "Stock")."""

    __tablename__ = "stock_lot"
    __table_args__ = (
        CheckConstraint("amount_milli >= 0", name="never_below_zero"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id"))
    amount_milli: Mapped[int] = mapped_column(BigInteger)
    # What it was bought as, for display ("bought as a dozen"). Null: typed grams.
    size_id: Mapped[int | None] = mapped_column(ForeignKey("food_size.id", ondelete="SET NULL"))
    use_by: Mapped[date | None] = mapped_column(Date)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    frozen_on: Mapped[date | None] = mapped_column(Date)
    # Set when it reaches zero. Empty lots stay (hidden) for the undo window, then go.
    emptied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeLine(Base):
    """One stock lot touched by a change: before → after."""

    __tablename__ = "change_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    change_id: Mapped[int] = mapped_column(ForeignKey("change.id", ondelete="CASCADE"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"))
    lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_lot.id", ondelete="SET NULL"), index=True
    )
    amount_before_milli: Mapped[int] = mapped_column(BigInteger)
    amount_after_milli: Mapped[int] = mapped_column(BigInteger)
    place_before_id: Mapped[int | None] = mapped_column(ForeignKey("place.id"))
    place_after_id: Mapped[int | None] = mapped_column(ForeignKey("place.id"))
    use_by_before: Mapped[date | None] = mapped_column(Date)
    use_by_after: Mapped[date | None] = mapped_column(Date)
    # The ingredient's whole amount in this packet's place before and after the change,
    # counting its other packets too. Null on lines recorded before 0.2.1.
    total_before_milli: Mapped[int | None] = mapped_column(BigInteger)
    total_after_milli: Mapped[int | None] = mapped_column(BigInteger)


class ChangeMonth(Base):
    """Thinned history: a month's stock changes for one food, added up."""

    __tablename__ = "change_month"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # "2025-10"
    food_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    # Sum of (after - before): bought is positive, used and binned negative.
    amount_milli: Mapped[int] = mapped_column(BigInteger, default=0)
    changes: Mapped[int] = mapped_column(Integer, default=0)
