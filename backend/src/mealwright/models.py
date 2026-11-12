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
    Text,
    UniqueConstraint,
    event,
    false,
    insert,
    select,
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
    # Which pint a recipe's "pint" is: "uk" (568 ml) or "us" (473 ml). 0.6 import pints.
    pints: Mapped[str] = mapped_column(String(2), default="uk", server_default="uk")
    # Cook mode's per-step ingredients (Experimental), off by default. 0.7 K4 (cabledrawer 1 Nov).
    cook_per_step: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    undo_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    history_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    use_soon_days: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # Plan settings (0.6; docs/dev/api-0.2.md section 3.1). Tub life: how long a new tub keeps
    # in the fridge (days) or the freezer (months). Plan ahead: how many days the shopping
    # list looks forward, never asked each time (cabledrawer, 0.6 answer 8). Week start: 1 is
    # Monday ... 7 is Sunday (cabledrawer, 0.6 answer 7).
    tub_fridge_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    tub_freezer_months: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    plan_ahead_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    week_starts_on: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # The shopping-list counter (docs/dev/sync-protocol.md 3.7): the number of the last
    # recorded list change, and the highest version whose rows the tidy-up has deleted.
    list_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    list_purged_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # The kitchen's equipment for Batch cook (Experimental; 0.8 wave 6, B1; cabledrawer 28 Oct): hob
    # rings, pressure cookers (an Instant Pot counts), an oven; `kitchen_asked` is false until
    # the household has answered once (Batch cook asks on first use).
    kitchen_hob_rings: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    kitchen_pressure_cookers: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    kitchen_oven: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    kitchen_asked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # An admin can hide Batch cook (0.8 wave 6, B2): no sidebar entry, no Plan tab, and its
    # suggestions are refused. False (shown) is the usual.
    batch_cook_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )
    # "Who's this?" on shared logins (spec "History and undo", cabledrawer 17 Oct): off by default.
    # Switched on by an admin in Settings → Household (0.9 A1).
    ask_whos_this: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # Backups (0.9, D1; spec section 7, cabledrawer 17 Oct): how often Mealwright backs its database
    # up ("daily", "twice-daily" or "weekly") and how many of those it keeps (1 to 30). The last
    # backup that failed, in plain words, and when: empty while backups work (mealwright.backups).
    backup_every: Mapped[str] = mapped_column(String(12), default="daily", server_default="daily")
    backup_keep: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    backup_problem: Mapped[str | None] = mapped_column(String(300))
    backup_problem_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Full Onboarding (0.9 U2): false until the first admin finishes or skips the steps after
    # making the account; then onboarding never shows again. Households from before are true.
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # How amounts are shown (spec "Amounts shown in 1.0"; 0.9 U2, cabledrawer 12 Nov):
    # "as_written" (the usual) or "metric" (grams and millilitres). Stored only for now.
    amounts_shown: Mapped[str] = mapped_column(
        String(10), default="as_written", server_default="as_written"
    )


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


class SsoSettings(Base):
    """The household's single sign-on (Settings → Sign-in → Single sign-on; 0.9 O1). No row: not
    set up. The client secret is stored sealed (`mealwright.secret_box`), never as typed.

    `group_roles` is a list of {"group": ..., "role": "admin"|"member"}, first match wins with
    Admin before Member. `anyone_else` is what someone in none of those groups gets: "none" (not
    let in) or "member". `redirect_uri` is the address the admin gave the sign-in server; the
    sign-in only ever sends that one, never one built from a request's headers.
    """

    __tablename__ = "sso_settings"
    __table_args__ = (
        CheckConstraint("anyone_else IN ('none', 'member')", name="anyone_else_known"),
    )

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    issuer: Mapped[str] = mapped_column(String(500))
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret_sealed: Mapped[str | None] = mapped_column(Text)
    button_name: Mapped[str] = mapped_column(String(60))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    group_claim: Mapped[str] = mapped_column(String(100), default="groups")
    group_roles: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    anyone_else: Mapped[str] = mapped_column(String(10), default="none")
    make_accounts: Mapped[bool] = mapped_column(Boolean, default=True)
    password_sign_in: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Member(Base):
    """A person in the household (spec section 3, "Users and households"; 0.9 A1): a name, a
    colour and how much they eat, with or without a login. Kids, a baby, or two people who share
    one "family" login are members too. Portions are counted in quarters (4 is one portion).

    Removing someone only marks them (`removed_at`): their meals, tubs and history stay, and
    Recent changes shows "Joss (removed)". cabledrawer 12 Nov: Undo for 7 days."""

    __tablename__ = "member"
    __table_args__ = (
        CheckConstraint("portion_quarters >= 1 AND portion_quarters <= 8", name="portion_range"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    # A palette name from the design ("green", "amber"...). Null: none chosen.
    colour: Mapped[str | None] = mapped_column(String(20))
    portion_quarters: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Login(Base):
    """Someone who can sign in. Separate from member profiles, which can exist without a
    login (spec section 3). Every login has its own member (0.9 A1), so its person's name,
    colour and portion live there; a shared login ("Kitchen tablet") has one too, which
    doesn't eat and is never offered as a person."""

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
    role: Mapped[str] = mapped_column(String(10))  # "admin" or "member" (mealwright.roles)
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), unique=True
    )
    # Used by several people (a kitchen tablet, a "family" login): it asks "Who's this?" when
    # the household has that switched on.
    shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    theme: Mapped[str] = mapped_column(String(10), default="auto")  # auto, light, dark
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the password was last set by its owner or reset-admin (PR A2). Empty for one set
    # before then, or at setup.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Single sign-on (0.9 O1): the identity provider's issuer and subject ("sub") this login
    # signs in as. A login is found only by these two together, never by a name or email
    # address from the provider.
    sso_issuer: Mapped[str | None] = mapped_column(String(500))
    sso_subject: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("sso_issuer", "sso_subject", name="uq_login_sso"),)


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
    # On a shared login: who picked themselves in "Who's this?" on this device (0.9 A1).
    member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id", ondelete="SET NULL"))
    # When they picked themselves: a pick older than 30 minutes no longer counts.
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A short name for the device, such as "iPhone · Safari" (mealwright.devices; PR A2).
    # Only this is kept, never the browser's whole User-Agent. Empty if not recognised.
    device: Mapped[str | None] = mapped_column(String(60))
    # Signed in with single sign-on (0.9 O1): the provider's refresh token, sealed
    # (`mealwright.secret_box`), and when it is next used to check the sign-in is still allowed.
    # Signing out deletes the row, and the token with it.
    sso: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    sso_refresh_sealed: Mapped[str | None] = mapped_column(Text)
    sso_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


TOKEN_SCOPES = ("read", "full")


class ApiToken(Base):
    """An API token for a script or another app (0.9 O2; spec section 7, cabledrawer 17 Oct): read
    only or full, with an optional end date. Only an admin makes one, and it works only while
    the admin who made it is still an admin of the household (proposed, for cabledrawer). The token
    itself (`mw_…`) is shown once and never stored: only its SHA-256, like a session's. Deleting
    one sets `revoked_at`; it then never works again."""

    __tablename__ = "api_token"
    __table_args__ = (
        CheckConstraint("scope IN ('read', 'full')", name="scope_known"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    login_id: Mapped[int] = mapped_column(ForeignKey("login.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(String(4))  # "read" or "full"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Written at most once a minute, like a session's last_seen_at.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # None: never
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JoinLink(Base):
    """A one-time sign-in link an admin made for a person (0.9 A1; cabledrawer 12 Nov): it
    works once, for 24 hours, and the person picks their own password with it. Only the token's
    SHA-256 is stored, like a session's."""

    __tablename__ = "join_link"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    login_id: Mapped[int] = mapped_column(ForeignKey("login.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Places and shops ------------------------------------------------------------------------


class Place(Base):
    """Where food lives at home. `kind` drives the rules (freezer last, To freezer), so
    renaming a place never breaks them."""

    __tablename__ = "place"
    __table_args__ = ({"sqlite_autoincrement": True},)  # a removed id is never handed out again

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
    __table_args__ = ({"sqlite_autoincrement": True},)

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
    # "use_by" or "best_before" when the household chose one (0.8, cabledrawer 7 Nov); null: the
    # default (mealwright.date_kinds).
    date_kind: Mapped[str | None] = mapped_column(String(11))
    # The shopping-list counter value of the last change a list shows (sync protocol 3.7).
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # A staple's restock date (0.7, cabledrawer 20 Oct) is its newest standing "Restocked" tick
    # (`list_tick.restock`), so an untick or Undo puts the date back by itself. This keeps the
    # newest one among purchases the tidy-up has already deleted, or the date typed in the
    # editor (`mealwright.restock`).
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The moment a restock date was typed (or Restocked pressed) in the editor (0.7 K5,
    # cabledrawer 2 Nov: "the date I type wins"). While set, `restocked_at` holds that date and a
    # tick counts only if it was ticked after this moment.
    restock_typed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # The person who did it (0.9 A1): the login's own person, or on a shared login the one
    # picked in "Who's this?". Null: nobody picked, so the login's name is shown.
    member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id", ondelete="SET NULL"))
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
    # A staple ticked: "Restocked" (nothing goes into the pantry; the restock date moves on).
    restock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
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


class StocktakePlace(Base):
    """A place whose stocktake is finished (0.8 S6, cabledrawer 7 Nov). The household's stocktake
    progress lives here and in `StocktakeEntry`, on the server, so any phone can carry on and
    anyone in the household can finish it. A place with no row here is "not finished"; the
    stocktake reopens at the first of those, in the Settings order."""

    __tablename__ = "stocktake_place"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), primary_key=True
    )
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StocktakeEntry(Base):
    """One ingredient in one place, looked at in the stocktake: answered (an answer was
    tapped, `change_id` its stock change, none when there was nothing to change), or only
    added with "+ Something else in the Cupboard" (`answered` false). An Undo of the answer
    makes it unanswered again. Starting a new stocktake deletes them all."""

    __tablename__ = "stocktake_entry"
    __table_args__ = (UniqueConstraint("place_id", "food_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id", ondelete="CASCADE"))
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("change.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- Recipes (docs/dev/api-0.4-recipes.md) -------------------------------------------------------
# Amounts on a recipe line are thousandths of the unit the person typed (2 tbsp is 2000), not of
# a base unit: the recipe keeps its own wording. Ids are never reused (sqlite_autoincrement), so
# Undo can put a deleted recipe back with its old id and the lines that use it still point at it.


class StapleCheck(Base):
    """A staple on Shopping's "Check you have these" card that someone tapped "Got it" for
    (0.6 PR 5). It stays off the card until a meal that uses it, and was not planned when "Got
    it" was said, shows up: `item_ids` are the meal items that used it then (proposed, for
    cabledrawer). Meals going or the days passing never bring it back."""

    __tablename__ = "staple_check"

    food_id: Mapped[int] = mapped_column(
        ForeignKey("food.id", ondelete="CASCADE"), primary_key=True
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    item_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    # When the nutrition figures were last typed or read from a page, and when the ingredient
    # lines last changed (R3): the lines newer than the figures make "Nutrition possibly out
    # of date". Null on a recipe from before: no note.
    nutrition_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class RecipeMethod(Base):
    """One way of cooking a recipe (0.8 wave 5, M2; cabledrawer 31 Oct and 9 Nov): a recipe has one
    method, or two ("Stovetop" and "Instant Pot"), each with its own ingredient lines, steps and
    time. The first (`position` 0) is the recipe as it always was: the recipe's own `time_minutes`
    is kept equal to its time, and a line or step with no `method_id` belongs to it. A one-method
    recipe has no method name. `last_used_at` is when the method was last planned or cooked: the
    one used last is pre-picked when the recipe is added to the plan."""

    __tablename__ = "recipe_method"
    __table_args__ = (
        CheckConstraint("position IN (0, 1)", name="position_known"),
        UniqueConstraint("recipe_id", "position", name="uq_recipe_method_recipe_id_position"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    # "Stovetop". Empty for the only method of a recipe.
    name: Mapped[str] = mapped_column(String(60), default="", server_default="")
    # Whole minutes: the active time, as the recipe's own `time_minutes`. Null: not given.
    time_minutes: Mapped[int | None] = mapped_column(Integer)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecipeLine(Base):
    """One ingredient line of a recipe, or a heading ("For the tempering") between them."""

    __tablename__ = "recipe_line"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_recipe_line_household_id_id"),
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
    # Optional (R3, cabledrawer 6 and 9 Nov): adding the recipe to the plan asks whether it will be
    # used; the shopping list and "Cooked it" count it only when it will.
    optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # The method the line is in (M2). Null: the recipe's first method.
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_method.id", ondelete="CASCADE"), index=True
    )


class RecipeStep(Base):
    """One method step, or a heading, in order. Plain text."""

    __tablename__ = "recipe_step"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_recipe_step_household_id_id"),
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
    optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # A wait on the step (M1): marinate, ferment, soak... The range in whole minutes (the longest
    # is the same when it is one length); `wait_overnight` says the range ends at "overnight"
    # (stored as 12 h so the plan can later work backwards from it). All empty: no wait.
    wait_kind: Mapped[str | None] = mapped_column(String(10))
    wait_min_minutes: Mapped[int | None] = mapped_column(Integer)
    wait_max_minutes: Mapped[int | None] = mapped_column(Integer)
    wait_overnight: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # What a person set by hand for Batch cook (0.8 wave 6, B1): "hands" or "waiting", the
    # minutes, and the equipment ("hob", "pressure", "oven", "none"). Empty: guessed from the
    # step's words each time it is read (`step_timings`), never stored.
    timing_hands: Mapped[str | None] = mapped_column(String(7))
    timing_minutes: Mapped[int | None] = mapped_column(Integer)
    timing_equipment: Mapped[str | None] = mapped_column(String(8))
    # The method the step is in (M2). Null: the recipe's first method.
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_method.id", ondelete="CASCADE"), index=True
    )


class RecipeStepLine(Base):
    """Which ingredient lines a method step uses, for Cook mode's per-step ingredients
    (spec section 6 gaps, "Cook mode ingredients", cabledrawer 17 Oct): each link is guessed
    from the step's words, or set by hand when editing the recipe. Goes with its step or its
    line; the step and the line are always the same household's."""

    __tablename__ = "recipe_step_line"
    __table_args__ = (
        CheckConstraint("kind IN ('guessed', 'by_hand')", name="kind_known"),
        UniqueConstraint("step_id", "line_id", name="uq_recipe_step_line_step_id_line_id"),
        ForeignKeyConstraint(
            ["household_id", "step_id"],
            ["recipe_step.household_id", "recipe_step.id"],
            ondelete="CASCADE",
            name="fk_recipe_step_line_household_id_recipe_step",
        ),
        ForeignKeyConstraint(
            ["household_id", "line_id"],
            ["recipe_line.household_id", "recipe_line.id"],
            ondelete="CASCADE",
            name="fk_recipe_step_line_household_id_recipe_line",
        ),
        Index("ix_recipe_step_line_line_id", "line_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[int] = mapped_column(Integer)
    line_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="by_hand")


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
    # A downloaded photo that an import draft is keeping (cabledrawer 21 Oct): it is the draft's,
    # not a waiting upload, so it isn't deleted after 24 hours and doesn't count towards the
    # 10 waiting. It goes when the draft goes, or becomes the recipe's when the draft is saved.
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_draft.id", ondelete="SET NULL"), index=True
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


class ImportDraft(Base):
    """An import left unfinished (spec section 6, "Drafts (cabledrawer 21 Oct)"). It belongs to the
    household, like a recipe, and anyone in it can carry on. It keeps the link or pasted text,
    what Mealwright read (`review`), every choice so far (`choices`) and, through
    `recipe_photo.draft_id`, the downloaded photo. Nothing in a draft touches Ingredients: the
    new ingredients, staples and other names it holds are only made when the recipe is saved.

    It is deleted quietly 15 days after its last change (`updated_at`). A deleted draft is
    hidden (`removed_at`) for the undo window (7 days), then deleted for good with its photo."""

    __tablename__ = "import_draft"
    __table_args__ = (
        CheckConstraint("source_kind IN ('link', 'text')", name="source_kind_known"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    # "link" or "text", and what was typed in the box (up to 100,000 characters).
    source_kind: Mapped[str] = mapped_column(String(8))
    source_text: Mapped[str] = mapped_column(Text)
    # "bbcgoodfood.com", for the list. Null for pasted text.
    site: Mapped[str | None] = mapped_column(String(253))
    # The recipe's name as it is now in the review's Name box.
    name: Mapped[str] = mapped_column(String(200))
    # What Mealwright read (the import review, as the screen was sent it) and the choices made on
    # it so far: both are only what the screen needs to carry on. Save checks everything again.
    review: Mapped[dict[str, Any]] = mapped_column(JSON)
    choices: Mapped[dict[str, Any]] = mapped_column(JSON)
    # The ingredient lines, and how many of them are tied to an ingredient (matched or chosen),
    # worked out when the draft is saved, for the list ("6 of 9 ingredients checked").
    lines_total: Mapped[int] = mapped_column(Integer, default=0)
    lines_checked: Mapped[int] = mapped_column(Integer, default=0)
    started_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    started_by_name: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The last time anyone changed it: the 15 days count from here.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Plan and cooking (0.6) --------------------------------------------------------------------
# Links between the plan tables are checked by the database to stay inside one household
# (composite keys on (household_id, id)). Links to recipes, ingredients, places and logins are
# plain keys like everywhere else; the server checks the household when it writes them.

# Breakfast, Lunch, Snack (off) and Dinner, in that order (cabledrawer, 0.6 answer 7).
DEFAULT_SLOTS = (
    ("Breakfast", True),
    ("Lunch", True),
    ("Snack", False),
    ("Dinner", True),
)

MEAL_STATUSES = ("planned", "cooked", "didnt", "moved")
SPREAD_PATTERNS = ("lunches", "lunch_dinner", "dinners", "pick")


class MealSlot(Base):
    """Breakfast, Lunch, Dinner...: a row of the plan. Hiding one (`enabled` off) keeps its
    meals. Deleting a slot that still has meals is refused by the database."""

    __tablename__ = "meal_slot"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_meal_slot_household_id_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))


class Meal(Base):
    """What's planned for one date and slot (one meal per date and slot)."""

    __tablename__ = "meal"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_meal_household_id_id"),
        UniqueConstraint("household_id", "day", "slot_id", name="uq_meal_household_id_day_slot_id"),
        CheckConstraint("status IN ('planned', 'cooked', 'didnt', 'moved')", name="status_known"),
        # No ON DELETE action: a slot with meals can't be deleted (hide it instead).
        ForeignKeyConstraint(
            ["household_id", "slot_id"],
            ["meal_slot.household_id", "meal_slot.id"],
            name="fk_meal_household_id_meal_slot",
        ),
        Index("ix_meal_household_id_day", "household_id", "day"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    slot_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="planned", server_default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BatchSession(Base):
    """One Batch cook (Experimental) session (0.8 wave 6, B2; cabledrawer 28 Oct): several recipes
    cooked together on one day, each through Cook once. The session's recipes are its batch
    cooks (`batch_cook.session_id`), in the order they were made; the cook-day meal items are
    theirs by the cook meal. `together_minutes` and `one_by_one_minutes` are the rough times
    shown when it was planned (a snapshot: a recipe edited later does not move them)."""

    __tablename__ = "batch_session"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_batch_session_household_id_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    cook_day: Mapped[date] = mapped_column(Date)
    together_minutes: Mapped[int | None] = mapped_column(Integer)
    one_by_one_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Batch cook mode (0.8 wave 6, B3): the schedule as it was made when the mode was started (a
    # snapshot, so a reload, another phone or a closed tab carries on where it was, and a recipe
    # edited later does not move it), and a fingerprint of what it was made from, so "Plan again"
    # is offered when a recipe or the kitchen has changed since. Both empty until it is started.
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    schedule_basis: Mapped[str | None] = mapped_column(String(64))
    schedule_made_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchTaskProgress(Base):
    """Where a Batch cook session is up to (0.8 wave 6, B3): one row for each task of the
    schedule that is done or whose timer has been started. A row of its own for each task (not
    one JSON on the session) so two phones marking different tasks never overwrite each other.
    Goes with its session; "Plan again" clears them."""

    __tablename__ = "batch_task_progress"
    __table_args__ = (
        UniqueConstraint("session_id", "task_id", name="uq_batch_task_progress_session_id_task_id"),
        ForeignKeyConstraint(
            ["household_id", "session_id"],
            ["batch_session.household_id", "batch_session.id"],
            ondelete="CASCADE",
            name="fk_batch_task_progress_household_id_batch_session",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[str] = mapped_column(String(16))  # "t1"... as in the schedule
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchCook(Base):
    """One "Cook once, eat for..." session: a recipe cooked on a day into several tubs."""

    __tablename__ = "batch_cook"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_batch_cook_household_id_id"),
        CheckConstraint(
            "pattern IN ('lunches', 'lunch_dinner', 'dinners', 'pick')", name="pattern_known"
        ),
        CheckConstraint("tub_count >= 1 AND tub_count <= 99", name="tub_count_range"),
        # The meal it was cooked for (the cook-day meal). No ON DELETE action, because
        # "set null" on a key that holds household_id would empty that too: the server clears
        # the link first (`mealwright.plan.delete_meal`), and the database refuses otherwise.
        ForeignKeyConstraint(
            ["household_id", "cook_meal_id"],
            ["meal.household_id", "meal.id"],
            name="fk_batch_cook_household_id_meal",
        ),
        # The Batch cook session it was made in, if any. Same rule: the server clears or removes
        # it first, the database refuses otherwise.
        ForeignKeyConstraint(
            ["household_id", "session_id"],
            ["batch_session.household_id", "batch_session.id"],
            name="fk_batch_cook_household_id_batch_session",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    # Proposed, for cabledrawer: if the recipe is deleted for good the batch (and the tubs in the
    # freezer) stay, and read by the name kept here.
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="SET NULL"), index=True
    )
    recipe_name: Mapped[str] = mapped_column(String(200))
    cook_meal_id: Mapped[int | None] = mapped_column(Integer, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, index=True)
    cooked_on: Mapped[date] = mapped_column(Date)
    tub_count: Mapped[int] = mapped_column(Integer)
    pattern: Mapped[str] = mapped_column(String(14), default="pick", server_default="pick")
    prep_note: Mapped[str | None] = mapped_column(String(500))
    # A palette name from the design ("green", "amber"...). Null: none chosen.
    colour: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Tub(Base):
    """One tub made by a batch cook. In a place (fridge, freezer), or put into a meal (a
    meal item points at it), or neither ("tubs left"). `amount_quarters` is what's left:
    4 is a full tub, 0 is eaten."""

    __tablename__ = "tub"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_tub_household_id_id"),
        CheckConstraint("amount_quarters >= 0 AND amount_quarters <= 4", name="quarters_range"),
        ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["batch_cook.household_id", "batch_cook.id"],
            ondelete="CASCADE",
            name="fk_tub_household_id_batch_cook",
        ),
        Index("ix_tub_household_id_batch_id", "household_id", "batch_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[int] = mapped_column(Integer)
    amount_quarters: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    # Whose tub it is: a person of the household (0.9 A1; by sign-in before).
    member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id", ondelete="SET NULL"))
    use_by: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Exactly one of recipe, tub, ingredient or note. A recipe or ingredient item whose recipe or
# ingredient was deleted for good has no link left, only its kept name. A note ("eating out",
# "at Amma's"; 0.7 P1) has no link at all, only its text in `name`.
MEAL_ITEM_ONE_OF = (
    "(kind = 'recipe' AND tub_id IS NULL AND food_id IS NULL"
    " AND (recipe_id IS NOT NULL OR name IS NOT NULL))"
    " OR (kind = 'ingredient' AND recipe_id IS NULL AND tub_id IS NULL"
    " AND (food_id IS NOT NULL OR name IS NOT NULL))"
    " OR (kind = 'tub' AND tub_id IS NOT NULL AND recipe_id IS NULL AND food_id IS NULL)"
    " OR (kind = 'note' AND recipe_id IS NULL AND tub_id IS NULL AND food_id IS NULL"
    " AND name IS NOT NULL)"
)


class MealItem(Base):
    """One thing in a meal: a recipe, a tub, a plain ingredient ("Fruit") or a note ("Eating
    out"), exactly one.
    A recipe or ingredient deleted for good leaves its item with its name, so past meals still
    show what was eaten (cabledrawer 26 Oct, as batch cooks keep theirs); a purged tub takes its
    item. A removed recipe that can still be undone keeps its link."""

    __tablename__ = "meal_item"
    __table_args__ = (
        CheckConstraint(MEAL_ITEM_ONE_OF, name="one_of"),
        CheckConstraint(
            "servings IS NULL OR (kind = 'recipe' AND servings >= 1 AND servings <= 99)",
            name="servings_range",
        ),
        ForeignKeyConstraint(
            ["household_id", "meal_id"],
            ["meal.household_id", "meal.id"],
            ondelete="CASCADE",
            name="fk_meal_item_household_id_meal",
        ),
        ForeignKeyConstraint(
            ["household_id", "tub_id"],
            ["tub.household_id", "tub.id"],
            ondelete="CASCADE",
            name="fk_meal_item_household_id_tub",
        ),
        UniqueConstraint("household_id", "id", name="uq_meal_item_household_id_id"),
        Index("ix_meal_item_household_id_meal_id", "household_id", "meal_id", "position"),
        # A tub sits in one meal at a time.
        Index("uq_meal_item_tub_id", "tub_id", unique=True),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    meal_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # recipe, tub, ingredient or note. Filled in from the link when left out.
    kind: Mapped[str] = mapped_column(String(10))
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="SET NULL"), index=True
    )
    tub_id: Mapped[int | None] = mapped_column(Integer)
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("food.id", ondelete="SET NULL"), index=True
    )
    # The recipe's or ingredient's name, kept for when it is deleted for good. Shown only then.
    name: Mapped[str | None] = mapped_column(String(200))
    # How many people the recipe is for. Null: its own "serves".
    servings: Mapped[int | None] = mapped_column(Integer)
    # The ids of the recipe's Optional lines the person will not use (R3, cabledrawer 9 Nov). Null
    # or empty: every line counts, as in a meal made before this.
    optional_skipped: Mapped[list[int] | None] = mapped_column(JSON)
    # Which of the recipe's methods the meal will be cooked with (M2, cabledrawer 9 Nov). Null: the
    # recipe's first method (a meal made before this, or a recipe with one method).
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_method.id", ondelete="SET NULL"), index=True
    )
    # The plan works backwards (M3, F124; cabledrawer 31 Oct and 9 Nov): a recipe with a long wait
    # (a step that waits four hours or more) is asked when the wait will be started. `start_at`
    # is that moment, `started_at` is when the person said the wait was begun ("Start it in Cook
    # mode" past that step, or "Done already"). Both are instants (UTC); the screens show them
    # in the household's own time. Null: not asked, or not started.
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MealEater(Base):
    """Who is eating a meal (0.7 P1, Serves - N + and "who's eating", F57). One row per person
    ticked; none means everyone. By person (`member`) since 0.9 A1, as tubs are."""

    __tablename__ = "meal_eater"
    __table_args__ = (
        UniqueConstraint("meal_id", "member_id", name="uq_meal_eater_meal_id_member_id"),
        ForeignKeyConstraint(
            ["household_id", "meal_id"],
            ["meal.household_id", "meal.id"],
            ondelete="CASCADE",
            name="fk_meal_eater_household_id_meal",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    meal_id: Mapped[int] = mapped_column(Integer, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("member.id", ondelete="CASCADE"), index=True)


class CookedRecord(Base):
    """What was actually cooked, for one meal item or one batch cook (spec section 6, "Plan
    and batch cooks": "Cooked meals keep a record of what was actually made", cabledrawer 17 Oct):
    a snapshot of the recipe as cooked, and the change-log group holding its stock changes.
    Written by "Cooked it"; read-only otherwise. The snapshot is the record's own copy, so
    editing the recipe or deleting it for good changes nothing here."""

    __tablename__ = "cooked_record"
    __table_args__ = (
        CheckConstraint("(meal_item_id IS NULL) != (batch_id IS NULL)", name="meal_item_or_batch"),
        CheckConstraint("portions >= 1 AND portions <= 999", name="portions_range"),
        ForeignKeyConstraint(
            ["household_id", "meal_item_id"],
            ["meal_item.household_id", "meal_item.id"],
            ondelete="CASCADE",
            name="fk_cooked_record_household_id_meal_item",
        ),
        ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["batch_cook.household_id", "batch_cook.id"],
            ondelete="CASCADE",
            name="fk_cooked_record_household_id_batch_cook",
        ),
        # One record per meal item, and per batch cook.
        Index("uq_cooked_record_meal_item_id", "meal_item_id", unique=True),
        Index("uq_cooked_record_batch_id", "batch_id", unique=True),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    meal_item_id: Mapped[int | None] = mapped_column(Integer)
    batch_id: Mapped[int | None] = mapped_column(Integer)
    # The recipe it was cooked from, while it exists; the snapshot keeps its name either way.
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="SET NULL"), index=True
    )
    # How many portions were cooked. The snapshot's amounts are the recipe's own, for its
    # servings (spec section 2, deduction point 2 scales them by portions over servings).
    portions: Mapped[int] = mapped_column(Integer)
    # The recipe as it was when cooked: name, version, servings, lines (words, amount, unit,
    # the ingredient or recipe and its name, note) and steps. `mealwright.cooked.Snapshot`.
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    # The change-log group with its stock changes. Emptied if the tidy-up deletes that change.
    change_id: Mapped[int | None] = mapped_column(
        ForeignKey("change.id", ondelete="SET NULL"), index=True
    )
    cooked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cooked_by_login_id: Mapped[int | None] = mapped_column(
        ForeignKey("login.id", ondelete="SET NULL")
    )
    cooked_by_name: Mapped[str] = mapped_column(String(100), default="")


@event.listens_for(MealItem, "before_insert")
def _meal_item_kind_and_name(_mapper: Any, connection: Any, item: MealItem) -> None:
    """Fill in the kind from the link, and keep the recipe's or ingredient's name."""
    if item.kind is None:
        item.kind = "recipe" if item.recipe_id else "tub" if item.tub_id else "ingredient"
    if item.name is None and item.kind != "tub":
        table, key = (Recipe, item.recipe_id) if item.kind == "recipe" else (Food, item.food_id)
        if key is not None:
            # Only this household's own recipe or ingredient: a bad link copies no one else's name.
            item.name = connection.execute(
                select(table.name).where(table.id == key, table.household_id == item.household_id)
            ).scalar()


@event.listens_for(Login, "before_insert")
def _every_login_has_a_person(_mapper: Any, connection: Any, login: Login) -> None:
    """Every login has its own person (0.9 A1): a login made without one gets a member of the
    same name, eating one portion, so portions and Recent changes always have someone."""
    if login.member_id is None:
        login.member_id = connection.execute(
            insert(Member)
            .values(
                household_id=login.household_id,
                name=login.name,
                portion_quarters=4,
                created_at=utcnow(),
                created_by_name="",
            )
            .returning(Member.id)
        ).scalar_one()
