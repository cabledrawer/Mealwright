"""Your own network: the allow list and which addresses need it (spec section 7)."""

from ipaddress import ip_address
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mealwright import migrate, own_network
from mealwright.db import make_engine, make_sessionmaker
from mealwright.models import Household, Login, OwnNetworkEntry
from mealwright.own_network import (
    ALREADY,
    BAD_ENTRY,
    FULL,
    MAX_ENTRIES,
    NEVER,
    TOO_WIDE,
    always_blocked,
    needs_listing,
)


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    factory = make_sessionmaker(engine)
    with factory() as session:
        session.add_all([Household(id=1, name="Home"), Household(id=2, name="Next door")])
        session.add(
            Login(
                id=1,
                household_id=1,
                username="tess",
                name="Tess",
                password_hash="x",
                role="admin",
            )
        )
        session.commit()
    return factory


# --- Which addresses need the list ------------------------------------------------------

PUBLIC = ["93.184.216.34", "8.8.8.8", "2606:4700::1", "2a00:1450:4009:81f::200e"]
NEEDS_LISTING = [
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.20",
    "100.64.0.1",  # shared (CGNAT)
    "100.127.255.254",
    "224.0.0.1",  # multicast
    "239.255.255.250",
    "240.0.0.1",  # reserved
    "255.255.255.255",
    "198.18.0.1",  # benchmarking
    "192.0.2.1",  # documentation
    "fc00::1",  # unique-local
    "fd12:3456::1",
    "fec0::1",  # site-local (old)
    "ff02::1",  # multicast
    "::ffff:192.168.1.20",  # IPv4-mapped private
    "::ffff:10.0.0.1",
    "::192.168.1.20",  # IPv4-compatible private
    "64:ff9b::c0a8:114",  # NAT64 of 192.168.1.20
    "64:ff9b:1::c0a8:114",  # local NAT64 of 192.168.1.20
    "64:ff9b:1::5db8:d822",  # local NAT64 of a public address: local, so still listed
    "2002:c0a8:114::1",  # 6to4 of 192.168.1.20
    "2001:db8::1",  # documentation
]
ALWAYS = [
    "127.0.0.1",
    "127.1.2.3",
    "0.0.0.0",  # noqa: S104 (an address to refuse, not one to listen on)
    "0.1.2.3",
    "169.254.169.254",  # the usual cloud metadata address
    "169.254.0.1",
    "100.100.100.200",  # another cloud's metadata address
    "::1",
    "::",
    "fe80::1",
    "febf::1",
    "fd00:ec2::254",  # a cloud metadata address over IPv6
    "::ffff:127.0.0.1",  # IPv4-mapped
    "::ffff:169.254.169.254",
    "::127.0.0.1",  # IPv4-compatible
    "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
    "64:ff9b:1::7f00:1",  # local NAT64 of 127.0.0.1
    "64:ff9b:1::a9fe:a9fe",  # local NAT64 of 169.254.169.254
    "2002:7f00:1::",  # 6to4 of 127.0.0.1
]


@pytest.mark.parametrize("address", PUBLIC)
def test_public_addresses_need_nothing(address: str) -> None:
    assert not needs_listing(ip_address(address))
    assert not always_blocked(ip_address(address))


@pytest.mark.parametrize("address", NEEDS_LISTING)
def test_private_and_odd_addresses_need_listing(address: str) -> None:
    assert needs_listing(ip_address(address))
    assert not always_blocked(ip_address(address))


@pytest.mark.parametrize("address", ALWAYS)
def test_this_server_link_local_and_metadata_are_always_blocked(address: str) -> None:
    assert always_blocked(ip_address(address))
    assert needs_listing(ip_address(address))


# --- Adding and tidying ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "kind", "value"),
    [
        ("Wiki.Home.Example", "name", "wiki.home.example"),
        ("  nas.lan.  ", "name", "nas.lan"),
        ("my_wiki", "name", "my_wiki"),
        ("bücher.example", "name", "xn--bcher-kva.example"),
        ("192.168.1.20", "address", "192.168.1.20"),
        ("::ffff:192.168.1.20", "address", "192.168.1.20"),
        ("FD12:3456:0000::0001", "address", "fd12:3456::1"),
        ("192.168.1.5/24", "range", "192.168.1.0/24"),
        ("10.0.0.0/8", "range", "10.0.0.0/8"),
        ("100.64.0.0/11", "range", "100.64.0.0/11"),
        ("FD12:3456:789A::/48", "range", "fd12:3456:789a::/48"),
        ("2001:db8::/32", "range", "2001:db8::/32"),
        ("192.168.1.20/32", "address", "192.168.1.20"),  # one address, however it's written
        ("FD12::1/128", "address", "fd12::1"),
        ("::ffff:192.168.1.20/128", "address", "192.168.1.20"),
        ("192.168.1.20/31", "range", "192.168.1.20/31"),
        ("203.0.113.7", "address", "203.0.113.7"),  # a public address, for an odd port
    ],
)
def test_entries_are_tidied(typed: str, kind: str, value: str) -> None:
    assert own_network.tidy(typed) == (kind, value)


@pytest.mark.parametrize(
    ("typed", "problem"),
    [
        ("", BAD_ENTRY),
        ("   ", BAD_ENTRY),
        ("http://wiki.home/", BAD_ENTRY),
        ("wiki.home:8080", BAD_ENTRY),
        ("wiki home", BAD_ENTRY),
        ("-bad.example", BAD_ENTRY),
        ("*.home.example", BAD_ENTRY),
        ("192.168.1", BAD_ENTRY),  # looks like an address
        ("2130706433", BAD_ENTRY),
        ("a" * 64 + ".example", BAD_ENTRY),
        ("fd12::1%eth0", BAD_ENTRY),
        ("::ffff:192.168.1.0/120", BAD_ENTRY),  # write IPv4 ranges as IPv4
        ("64:ff9b::/96", BAD_ENTRY),
        ("64:ff9b::/120", BAD_ENTRY),  # part of NAT64
        ("64:ff9b:1::/48", BAD_ENTRY),  # local NAT64
        ("64:ff9b:1::/96", BAD_ENTRY),
        ("2002:c0a8:114::/48", BAD_ENTRY),  # 6to4 (of 192.168.1.20)
        ("2002::/32", BAD_ENTRY),
        ("2001::/32", BAD_ENTRY),  # Teredo
        ("2001:0:4136:e378::/64", BAD_ENTRY),
        ("2002::/16", TOO_WIDE),
        ("127.0.0.1/32", NEVER),
        ("::1/128", NEVER),
        ("192.168.1.20/33", BAD_ENTRY),
        ("localhost", NEVER),
        ("LOCALHOST.", NEVER),
        ("wiki.localhost", NEVER),
        # The other names systems give this machine, and the cloud metadata name (follow-up from
        # the 0.5 PR 4 review).
        ("localhost.localdomain", NEVER),
        ("LocalHost.LocalDomain.", NEVER),
        ("ip6-localhost", NEVER),
        ("ip6-loopback", NEVER),
        ("localhost6", NEVER),
        ("metadata.google.internal", NEVER),
        ("Metadata.Google.Internal.", NEVER),
        # An address written the old way, which a system's lookup still reads as 127.0.0.1.
        ("0x7f000001", NEVER),
        ("0X7F.0.0.1", NEVER),
        ("0177.0.0.1", NEVER),
        ("0x7f.1", NEVER),
        ("0xa9fea9fe", NEVER),  # 169.254.169.254, the usual metadata address
        ("0x", NEVER),  # a bare 0x reads as 0, so 0.0.0.0
        ("0x.0x.0x.0x", NEVER),
        ("0xc0a80001", BAD_ENTRY),  # 192.168.0.1: write it as 192.168.0.1
        ("09.1.1.1", BAD_ENTRY),
        # The same names written so that the international-name mapping makes them these.
        ("\uff4c\uff4f\uff43\uff41\uff4c\uff48\uff4f\uff53\uff54", NEVER),  # full-width
        ("app.\uff4c\uff4f\uff43\uff41\uff4c\uff48\uff4f\uff53\uff54", NEVER),
        ("localhost\u200b", NEVER),  # a zero-width space after it
        ("local\u00adhost", NEVER),  # a soft hyphen inside it
        ("127.0.0.1", NEVER),
        ("::1", NEVER),
        ("0.0.0.0", NEVER),  # noqa: S104
        ("169.254.169.254", NEVER),
        ("100.100.100.200", NEVER),
        ("fd00:ec2::254", NEVER),
        ("fe80::1", NEVER),
        ("::ffff:127.0.0.1", NEVER),
        ("127.0.0.0/8", NEVER),
        ("169.254.0.0/16", NEVER),
        ("100.64.0.0/10", NEVER),  # holds 100.100.100.200
        ("fd00::/8", NEVER),  # holds fd00:ec2::254
        ("fc00::/7", NEVER),
        ("fe80::/10", NEVER),
        ("fd00:ec2::/32", NEVER),
        ("0.0.0.0/0", NEVER),
        ("::/0", NEVER),
        ("8.0.0.0/7", TOO_WIDE),
        ("128.0.0.0/1", NEVER),  # holds 169.254.0.0/16
        ("11.0.0.0/7", TOO_WIDE),
        ("2000::/3", TOO_WIDE),
        ("2001:db8::/31", TOO_WIDE),
    ],
)
def test_bad_entries_are_refused(typed: str, problem: str) -> None:
    with pytest.raises(ValueError) as refused:
        own_network.tidy(typed)
    assert str(refused.value) == problem


def test_add_list_and_remove(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        tess = db.get(Login, 1)
        wiki = own_network.add(db, 1, "Wiki.Home.Example", tess)
        own_network.add(db, 1, "192.168.1.0/24")
        db.commit()
        assert (wiki.kind, wiki.value, wiki.added_by_name, wiki.added_by_login_id) == (
            "name",
            "wiki.home.example",
            "Tess",
            1,
        )
        assert wiki.added_at is not None
        assert [(e.kind, e.value) for e in own_network.entries(db, 1)] == [
            ("name", "wiki.home.example"),
            ("range", "192.168.1.0/24"),
        ]
        with pytest.raises(ValueError, match=ALREADY):
            own_network.add(db, 1, "wiki.home.example.")
        with pytest.raises(ValueError, match=ALREADY):
            own_network.add(db, 1, "192.168.1.7/24")
        own_network.add(db, 1, "192.168.2.5")
        with pytest.raises(ValueError, match=ALREADY):
            own_network.add(db, 1, "192.168.2.5/32")
        own_network.remove(db, 1, own_network.entries(db, 1)[-1].id)

        listed = own_network.load(db, 1)
        assert listed.lists_name("WIKI.home.example.")
        assert not listed.lists_name("other.home.example")
        assert listed.lists_address(ip_address("192.168.1.99"))
        assert listed.lists_address(ip_address("::ffff:192.168.1.99"))
        assert not listed.lists_address(ip_address("192.168.2.1"))

        assert own_network.remove(db, 1, wiki.id)
        db.commit()
        assert [e.value for e in own_network.entries(db, 1)] == ["192.168.1.0/24"]
        assert not own_network.remove(db, 1, wiki.id)


def test_a_list_holds_at_most_100_entries(sessions: sessionmaker[Session]) -> None:
    assert MAX_ENTRIES == 100
    with sessions() as db:
        for n in range(MAX_ENTRIES):
            own_network.add(db, 1, f"10.0.{n}.1")
        db.commit()
        with pytest.raises(ValueError) as refused:
            own_network.add(db, 1, "nas.lan")
        assert str(refused.value) == FULL
        with pytest.raises(ValueError, match=ALREADY):  # said first: it's the more useful
            own_network.add(db, 1, "10.0.0.1")
        own_network.add(db, 2, "nas.lan")  # another household's list is its own
        own_network.remove(db, 1, own_network.entries(db, 1)[0].id)
        own_network.add(db, 1, "nas.lan")
        db.commit()
        assert len(own_network.entries(db, 1)) == MAX_ENTRIES


def test_lists_belong_to_their_household(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        theirs = own_network.add(db, 2, "192.168.1.0/24")
        own_network.add(db, 2, "nas.lan")
        own_network.add(db, 1, "nas.lan")  # the same name in two households is fine
        db.commit()
        assert own_network.load(db, 1).networks == ()
        assert not own_network.load(db, 1).lists_address(ip_address("192.168.1.5"))
        assert own_network.load(db, 2).lists_address(ip_address("192.168.1.5"))
        # One household can't take another's entry off.
        assert not own_network.remove(db, 1, theirs.id)
        db.commit()
        assert len(own_network.entries(db, 2)) == 2


def test_an_empty_list_lists_nothing(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        listed = own_network.load(db, 1)
    assert not listed.lists_name("anything.example")
    assert not listed.lists_address(ip_address("10.0.0.1"))


def test_the_database_refuses_a_second_copy_and_an_unknown_kind(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as db:
        own_network.add(db, 1, "nas.lan")
        db.commit()
        db.add(OwnNetworkEntry(household_id=1, kind="name", value="nas.lan"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(OwnNetworkEntry(household_id=1, kind="port", value="8080"))
        with pytest.raises(IntegrityError):
            db.commit()


# --- The migration -------------------------------------------------------------------------

BEFORE = "97d61f9dd082"  # 0.4.0's last migration
OWN_NETWORK = "63a26f6309e7"


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar())


def test_migration_adds_the_table_and_goes_back(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
    assert "own_network_entry" not in inspect(engine).get_table_names()

    migrate.upgrade(engine, OWN_NETWORK)
    columns = {c["name"] for c in inspect(engine).get_columns("own_network_entry")}
    assert columns == {
        "id",
        "household_id",
        "kind",
        "value",
        "added_at",
        "added_by_login_id",
        "added_by_name",
    }
    with engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM own_network_entry").scalar() == 0
        connection.execute(
            text(
                "INSERT INTO own_network_entry (household_id, kind, value, added_at,"
                " added_by_name) VALUES (1, 'name', 'nas.lan', '2026-10-22', 'Tess')"
            )
        )
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'own_network_entry'"
        ).scalar_one()
    assert "AUTOINCREMENT" in sql

    migrate.downgrade(engine, BEFORE)
    assert "own_network_entry" not in inspect(engine).get_table_names()
    assert _version(engine) == BEFORE
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM household").scalar() == 1

    migrate.upgrade(engine)
    assert "own_network_entry" in inspect(engine).get_table_names()


def test_the_fetch_refuses_the_same_names() -> None:
    for name in ("localhost.localdomain", "ip6-localhost", "metadata.google.internal"):
        assert own_network.is_localhost(name)
    assert not own_network.is_localhost("wiki.home.example")
    assert not own_network.is_localhost("mylocalhost.example")
