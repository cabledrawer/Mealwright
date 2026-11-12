import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from mealwright import auth, migrate, setup_code
from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.db import Base, make_engine
from mealwright.household import add_default_places, add_default_slots
from mealwright.main import create_app
from mealwright.models import Household, Login
from mealwright.outbound import install_network_guard

# The whole test suite runs with the network guard on: any connection or DNS lookup
# outside the outbound gate fails the test that made it.
install_network_guard()

# Cheap password hashing, in the tests only (cabledrawer 31 Oct): Argon2 with the smallest
# settings instead of the app's (64 MiB and 3 passes). Nearly every test signs in, so the
# app's hashing was a large part of the run. A test that checks hashing itself is marked
# `real_hashing` and keeps the app's own hasher. The app and the image never see this file.
CHEAP_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
_CHEAP_DUMMY_HASH = CHEAP_HASHER.hash("no such login")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_hashing: hash passwords with the app's own settings")


@pytest.fixture(autouse=True)
def _cheap_hashing(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("real_hashing"):
        return
    monkeypatch.setattr(auth, "_hasher", CHEAP_HASHER)
    monkeypatch.setattr(auth, "_DUMMY_HASH", _CHEAP_DUMMY_HASH)


@pytest.fixture(autouse=True)
def _forget_sign_in_servers_addresses() -> None:
    """What this process remembers of a sign-in server's address is per test."""
    from mealwright import sso

    sso.forget_remembered()


@pytest.fixture(autouse=True)
def _forget_compiled_statements() -> Iterator[None]:
    """Each test builds its own app and so its own database dialect. SQLAlchemy keeps every
    mapper's compiled statements in a cache keyed by dialect, and the cache holds the dialect
    (and its type caches) until it fills. Across the suite that was about 3,000 objects left
    behind per test that touches the database; emptying the caches afterwards drops it to
    about 35. Nothing here changes what a test sees."""
    yield
    for mapper in Base.registry.mappers:
        # `_compiled_cache` is private to SQLAlchemy, and used here in the tests only (cabledrawer
        # 30 Oct: OK). The app never touches it. If a SQLAlchemy update renames it, this line
        # fails loudly in every test; then find the new name or drop this fixture.
        mapper._compiled_cache.clear()


@pytest.fixture(scope="session")
def migrated_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh database brought up to the newest layout once per run (cabledrawer 30 Oct: a faster
    check). Running all the migrations took about 0.2 s, in every test that starts the app;
    copying this file takes a few ms. The app still runs its migrations on start, as it does
    for real, and finds nothing to do. test_migrations.py runs every step itself."""
    path = tmp_path_factory.mktemp("template") / "mealwright.db"
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine)
    engine.dispose()
    # Folded into the one file, so the copy holds everything (no -wal file left beside it).
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


@pytest.fixture
def settings(tmp_path: Path, migrated_database: Path) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copyfile(migrated_database, data_dir / "mealwright.db")
    # The nightly jobs are tested on their own (test_jobs.py).
    return Settings(data_dir=data_dir, run_jobs=False)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # HTTPS, as behind Caddy, so the Secure session cookie is sent back.
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


# The first-run setup code (PR A2) is random and printed in the log; the tests know it.
SETUP_CODE = "KTCH-NSET-UP23"


@pytest.fixture(autouse=True)
def _known_setup_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_code, "new_code", lambda: SETUP_CODE)


ADMIN = {
    "name": "Tess",
    "username": "tess",
    "password": "correct horse battery",
    "setup_code": SETUP_CODE,
}


@pytest.fixture
def kitchen(client: TestClient) -> TestClient:
    """A client signed in as the household's admin, on a fresh install."""
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
    return client


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        add_default_slots(db, 2)
        db.add(
            Login(
                household_id=2,
                username="neighbour",
                name="Neighbour",
                password_hash=hash_password("next door's own password"),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "neighbour", "password": "next door's own password"}
        assert other.post("/api/v1/session", json=body).status_code == 200
        yield other
