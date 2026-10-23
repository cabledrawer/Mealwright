"""Database tables.

Every table belongs to a household (`household_id`), so more than one household per
install stays possible later. The household table's own `id` is that household_id.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mealwright.db import Base

# How far the server's clock is moved: for the browser tests only, so they run on one fixed
# date and time (backend/scripts/e2e_server.py sets it before the server starts). No setting,
# file or environment variable reads it or changes it, and that script is not installed or in
# the image, so in a real install it is always zero (tests/test_test_clock.py).
TEST_CLOCK_SHIFT = timedelta(0)


def utcnow() -> datetime:
    """Now, in UTC: every time the server stores or compares (moved only in browser tests)."""
    return datetime.now(UTC) + TEST_CLOCK_SHIFT


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
    # The shopping-list counter (docs/dev/sync-protocol.md 3.7): the number of the last
    # recorded list change, and the highest version whose rows the tidy-up has deleted.
    list_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    list_purged_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


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


class OwnNetworkEntry(Base):
    """One entry on "Your own network" (Settings → Privacy, under Outside connections): a
    place on the household's own network that Mealwright may visit, such as a home wiki.
    Everything else on a private, internal or loopback address is blocked (spec section 7;
    `mealwright.own_network`). It starts empty. Recipe import uses it from 0.5, and
    notifications and single sign-on from 0.8.

    `kind` is "name" (a host name, lower case), "address" (one IP address) or "range" (a
    CIDR range), and `value` is the tidied text. The server itself (`localhost`), link-local
    and cloud "metadata" addresses stay blocked even if listed.

    Stored with the household, like the Privacy switches: with one household per install
    it covers the whole server. From the spec (section 6, "Recipe import, decided for 0.5"):
    "If more than one household per install ever arrives, this list becomes a server-level
    setting that only the server's admin can change, so one household's admin can never
    open the server's own network for everyone."
    """

    __tablename__ = "own_network_entry"
    __table_args__ = (
        UniqueConstraint("household_id", "value"),
        CheckConstraint("kind IN ('name', 'address', 'range')", name="kind_known"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[str] = mapped_column(String(260))  # a host name is at most 253 characters
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    added_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    added_by_name: Mapped[str] = mapped_column(String(100), default="")


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
    # Which aisle it's in (mealwright.aisles keys). Null shows under Other.
    aisle: Mapped[str | None] = mapped_column(String(20))
    # The shopping-list counter value of the last change a list shows (sync protocol 3.7).
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


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
    __table_args__ = (
        UniqueConstraint("household_id", "idempotency_key"),
        # No ON DELETE action (sync protocol 3.7): the tidy-up empties tick_id first.
        ForeignKeyConstraint(
            ["household_id", "tick_id"],
            ["list_tick.household_id", "list_tick.id"],
            use_alter=True,
            name="fk_change_household_id_list_tick",
        ),
        Index("ix_change_household_id_tick_id", "household_id", "tick_id"),
    )

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
    # The purchase (list_tick.id) this change was made for (sync protocol 3.7).
    tick_id: Mapped[str | None] = mapped_column(String(64))


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


# --- Shopping lists (docs/dev/sync-protocol.md section 3) ----------------------------------------
# Lists, items and actions use phone-made UUIDs, so a phone can make and name them offline.
# Amounts are milli base units, like stock_lot.


class ShoppingList(Base):
    __tablename__ = "shopping_list"
    __table_args__ = (
        # Exactly one main list per household.
        Index(
            "uq_shopping_list_one_main",
            "household_id",
            unique=True,
            sqlite_where=text("main"),
            postgresql_where=text("main"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))  # not unique
    main: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_name: Mapped[str] = mapped_column(String(100), default="")
    # A removed list is hidden, not frozen. Never set on the main list.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_action_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(BigInteger, default=0)


class ListItem(Base):
    __tablename__ = "list_item"
    __table_args__ = (
        Index("ix_list_item_household_id_version", "household_id", "version"),
        Index(
            "ix_list_item_household_id_list_id_food_id_shop_id",
            "household_id",
            "list_id",
            "food_id",
            "shop_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    list_id: Mapped[str] = mapped_column(
        ForeignKey("shopping_list.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id"), index=True)
    # Null: "Any shop".
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shop.id", ondelete="SET NULL"))
    amount_milli: Mapped[int | None] = mapped_column(BigInteger)
    size_id: Mapped[int | None] = mapped_column(ForeignKey("food_size.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(10), default="typed")  # typed, plan
    hand_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    put_away_place_id: Mapped[int | None] = mapped_column(
        ForeignKey("place.id", ondelete="SET NULL")
    )
    # A copy of the first standing tick, kept in step with list_tick by the server.
    ticked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ticked_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    ticked_by_name: Mapped[str | None] = mapped_column(String(100))
    ticked_device_id: Mapped[str | None] = mapped_column(String(36))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    added_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    added_by_name: Mapped[str] = mapped_column(String(100), default="")
    # The tombstone: a deleted item stays so an old queue can't bring it back.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_name: Mapped[str | None] = mapped_column(String(100))
    deleted_action_id: Mapped[str | None] = mapped_column(String(64))
    merged_into_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(BigInteger, default=0)


class ListTick(Base):
    """One purchase: one standing tick with its own pantry stock."""

    __tablename__ = "list_tick"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the tick action's ID
    item_id: Mapped[str] = mapped_column(ForeignKey("list_item.id", ondelete="CASCADE"), index=True)
    login_id: Mapped[int | None] = mapped_column(ForeignKey("login.id", ondelete="SET NULL"))
    login_name: Mapped[str] = mapped_column(String(100))
    device_id: Mapped[str | None] = mapped_column(String(36))
    ticked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    bought_milli: Mapped[int | None] = mapped_column(BigInteger)
    bought_size_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_size.id", ondelete="SET NULL")
    )
    change_id: Mapped[int | None] = mapped_column(ForeignKey("change.id", ondelete="SET NULL"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by_action_id: Mapped[str | None] = mapped_column(String(64))


class SyncAction(Base):
    """The sync log: every recorded list action (repeat-detection, order, Undo)."""

    __tablename__ = "sync_action"
    __table_args__ = (
        UniqueConstraint("household_id", "seq"),
        Index("ix_sync_action_household_id_item_id_seq", "household_id", "item_id", "seq"),
    )

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(30))
    login_id: Mapped[int | None] = mapped_column(ForeignKey("login.id", ondelete="SET NULL"))
    login_name: Mapped[str] = mapped_column(String(100))
    device_id: Mapped[str | None] = mapped_column(String(36))
    list_id: Mapped[str | None] = mapped_column(String(36))
    item_id: Mapped[str | None] = mapped_column(String(36))
    seen: Mapped[int | None] = mapped_column(BigInteger)
    made_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10))  # applied, merged, ignored
    reason: Mapped[str | None] = mapped_column(String(30))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("change.id", ondelete="SET NULL"))
    undone_by_action_id: Mapped[str | None] = mapped_column(String(64))


class ListNote(Base):
    """A quiet note on Shopping ("Wren added milk too") with Undo and a dismiss button."""

    __tablename__ = "list_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    list_id: Mapped[str] = mapped_column(
        ForeignKey("shopping_list.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str | None] = mapped_column(ForeignKey("list_item.id", ondelete="CASCADE"))
    food_id: Mapped[int | None] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"))
    for_login_id: Mapped[int] = mapped_column(ForeignKey("login.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # N1 to N7
    text: Mapped[str] = mapped_column(String(300))
    undo_action_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    gone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=0)


class DoubleTick(Base):
    """The "Did you buy 2?" question, until it's answered."""

    __tablename__ = "double_tick"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    list_id: Mapped[str] = mapped_column(
        ForeignKey("shopping_list.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("list_item.id", ondelete="CASCADE"))
    tick_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    login_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    same_login: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answer: Mapped[str | None] = mapped_column(String(10))  # two, one, none
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by_name: Mapped[str | None] = mapped_column(String(100))
    answer_action_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(BigInteger, default=0)


# --- Recipes (docs/dev/api-0.4-recipes.md) -------------------------------------------------------
# Amounts on a recipe line are thousandths of the unit the person typed (2 tbsp is 2000), not of
# a base unit: the recipe keeps its own wording. Ids are never reused (sqlite_autoincrement), so
# Undo can put a deleted recipe back with its old id and the lines that use it still point at it.


class Recipe(Base):
    __tablename__ = "recipe"
    __table_args__ = (
        CheckConstraint("serves IS NULL OR (serves >= 1 AND serves <= 99)", name="serves_range"),
        CheckConstraint("version >= 1", name="version_positive"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(200))
    # Whole minutes, in total. Null: not given.
    time_minutes: Mapped[int | None] = mapped_column(Integer)
    # 1 to 99. Null: not given (a batter or a powder).
    serves: Mapped[int | None] = mapped_column(Integer)
    # "Makes 1.5 litres": thousandths of the unit; the unit is g, kg, ml, l or a count word.
    makes_milli: Mapped[int | None] = mapped_column(BigInteger)
    makes_unit: Mapped[str | None] = mapped_column(String(30))
    # Made ahead (keeps in the pantry): its own pantry ingredient, made when the recipe is saved.
    made_ahead: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    homemade_food_id: Mapped[int | None] = mapped_column(
        ForeignKey("food.id", ondelete="SET NULL"), index=True
    )
    # Per serving, in thousandths (kcal, g). Null means unknown: never stored as 0.
    kcal_milli: Mapped[int | None] = mapped_column(BigInteger)
    protein_milli: Mapped[int | None] = mapped_column(BigInteger)
    carbs_milli: Mapped[int | None] = mapped_column(BigInteger)
    fat_milli: Mapped[int | None] = mapped_column(BigInteger)
    fibre_milli: Mapped[int | None] = mapped_column(BigInteger)
    # Plain text ("Amma's", a book title). The server never visits it.
    source_note: Mapped[str | None] = mapped_column(String(500))
    # An imported recipe keeps where it came from (cabledrawer 22 Oct, question 1): the web address
    # it was read from, the day it was imported and the author's name from the page. The server
    # never visits the address again; opening it is the person's own click.
    source_url: Mapped[str | None] = mapped_column(String(2000))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_author: Mapped[str | None] = mapped_column(String(200))
    # Starts at 1; every save adds 1 (two people editing: the second save is stopped).
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    updated_by_name: Mapped[str] = mapped_column(String(100), default="")
    # A deleted recipe is hidden for the undo window (7 days), then deleted for good.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecipeLine(Base):
    """One ingredient line of a recipe, or a heading ("For the tempering") between them."""

    __tablename__ = "recipe_line"
    __table_args__ = (
        CheckConstraint("kind IN ('ingredient', 'heading')", name="kind_known"),
        CheckConstraint("food_id IS NULL OR sub_recipe_id IS NULL", name="one_link"),
        Index("ix_recipe_line_recipe_id_position", "recipe_id", "position"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="ingredient")
    # The words as typed ("thuvaram paruppu"), or a heading's text. Kept when the link goes.
    words: Mapped[str] = mapped_column(String(200))
    # Optional. Thousandths of the unit: 1½ is 1500.
    amount_milli: Mapped[int | None] = mapped_column(BigInteger)
    # g, kg, ml, l, tsp, tbsp, cup, pinch. Null with no size: a count ("10 shallots").
    unit: Mapped[str | None] = mapped_column(String(10))
    # One of the linked ingredient's own sizes ("1 packet").
    size_id: Mapped[int | None] = mapped_column(ForeignKey("food_size.id", ondelete="SET NULL"))
    # An ingredient or another recipe, never both. A line can also have no link at all: its
    # ingredient was removed (the words stay, "not linked"), or the recipe it used was
    # deleted and the undo window has passed. While that recipe can still be undone the
    # link stays, and the line shows "recipe removed".
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("food.id", ondelete="SET NULL"), index=True
    )
    sub_recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="SET NULL"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(200))


class RecipeStep(Base):
    """One method step, or a heading, in order. Plain text."""

    __tablename__ = "recipe_step"
    __table_args__ = (
        CheckConstraint("kind IN ('step', 'heading')", name="kind_known"),
        Index("ix_recipe_step_recipe_id_position", "recipe_id", "position"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="step")
    text: Mapped[str] = mapped_column(String(5000))


class Tag(Base):
    """A tag the household made up ("Batch-friendly", "Quick"). Typed on a recipe, never
    managed on a screen of its own."""

    __tablename__ = "tag"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))


class RecipeTag(Base):
    __tablename__ = "recipe_tag"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class RecipePhoto(Base):
    """A recipe's one photo (cabledrawer 19 Oct, questions 6, 8, 36 and 37). Only the cleaned
    copies are kept, never the uploaded file: two JPEGs on the data volume, in the
    household's own folder, under a random `file_key` (mealwright.photos). An upload is
    saved here at once with no recipe; the recipe's own Save attaches it (cabledrawer 20 Oct),
    and an upload no recipe took within 24 hours is deleted by the hourly job."""

    __tablename__ = "recipe_photo"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    # Null: uploaded, not saved on a recipe yet.
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), unique=True
    )
    # A random name; the files are `photos/<household_id>/<file_key>.jpg` and
    # `<file_key>-list.jpg` in the data folder.
    file_key: Mapped[str] = mapped_column(String(64))
    # The large copy (longest side at most 1600 px) and the list copy.
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    list_width: Mapped[int] = mapped_column(Integer)
    list_height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)  # both files together
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    added_by_name: Mapped[str] = mapped_column(String(100), default="")
