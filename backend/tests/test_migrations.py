from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, column, insert, inspect, text
from sqlalchemy import table as sql_table

from mealwright import migrate
from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.db import Base, make_engine
from mealwright.main import create_app


def test_startup_creates_database(client: TestClient, tmp_path: Path) -> None:
    assert (tmp_path / "data" / "mealwright.db").exists()


def test_migrations_match_models(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], "models changed without a migration: run alembic revision --autogenerate"


def test_downgrade_to_empty(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_every_table_has_household_id() -> None:
    for table in Base.metadata.sorted_tables:
        if table.name == "household":
            continue
        assert "household_id" in table.columns, f"{table.name} has no household_id"


def _counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as connection:
        return tuple(  # type: ignore[return-value]
            connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()  # noqa: S608
            for table in ("household", "login", "session")
        )


def _make_0_1_database(path: Path) -> Engine:
    """A 0.1 database with a household, its admin (dark theme) and a signed-in session."""
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, "d60b64f1e4ff")  # 0.1.0
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin', 'dark', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO session (household_id, login_id, token_hash, remember, created_at,"
            " last_seen_at, expires_at) VALUES (1, 1, 'abc', 0, '2026-10-01', '2026-10-01',"
            " '2026-11-01')"
        )
    return engine


def test_downgrade_keeps_logins_and_sessions(tmp_path: Path) -> None:
    # Rebuilding the household table must not cascade into its logins (foreign keys are
    # switched off while migrating on SQLite).
    engine = _make_0_1_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    assert _counts(engine) == (1, 1, 1)
    migrate.downgrade(engine, "d60b64f1e4ff")
    assert _counts(engine) == (1, 1, 1)
    with engine.connect() as connection:
        theme = connection.exec_driver_sql("SELECT theme FROM login").scalar_one()
    assert theme == "dark"


def test_upgrade_downgrade_upgrade_round_trip(tmp_path: Path) -> None:
    engine = _make_0_1_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "d60b64f1e4ff")
    migrate.upgrade(engine)
    assert _counts(engine) == (1, 1, 1)
    with engine.connect() as connection:
        places = connection.exec_driver_sql("SELECT count(*) FROM place").scalar_one()
        on = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert places == 4
    assert on == 1  # switched back on after migrating


NB = "\u00a0"  # the no-break space the server puts between a number and its unit


def put(db: Connection, into: str, /, **row: object) -> None:
    db.execute(insert(sql_table(into, *[column(key) for key in row])).values(**row))


def _make_0_2_0_database(path: Path) -> Engine:
    """A real-looking 0.2.0 database: two households, foods with sizes and other names,
    several packets, and Recent changes including an undone one. Built with plain inserts on
    the 0.2.0 tables (before the 0.2.1 change); 0.2.1 then starts up on top of it."""
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, "d60b64f1e4ff")  # 0.1.0: the places arrive with the next step
    with engine.begin() as db:
        put(db, "household", id=1, name="Home", created_at="2026-10-01")
        put(db, "household", id=2, name="Next door", created_at="2026-10-01")
        put(
            db,
            "login",
            id=1,
            household_id=1,
            username="tess",
            name="Tess",
            password_hash=hash_password("correct horse battery"),
            role="admin",
            theme="dark",
            created_at="2026-10-01",
        )
    migrate.upgrade(engine, "b4391aaf7695")  # 0.2.0
    with engine.begin() as db:
        fridge = db.execute(
            text("SELECT id FROM place WHERE household_id = 1 AND name = 'Fridge'")
        ).scalar_one()
        cupboard = db.execute(
            text("SELECT id FROM place WHERE household_id = 1 AND name = 'Cupboard'")
        ).scalar_one()
        foods = ((1, 1, "Paneer", "weight"), (2, 1, "Toor dal", "weight"))
        for food_id, household, name, counted_as in (
            *foods,
            (3, 1, "Eggs", "count"),
            (4, 2, "Paneer", "weight"),
        ):
            put(
                db,
                "food",
                id=food_id,
                household_id=household,
                name=name,
                counted_as=counted_as,
                staple=False,
                created_at="2026-10-02",
            )
        for size_id, food_id, name, plural, milli in (
            (1, 1, "pack", "packs", 200_000),
            (2, 2, "packet", "packets", 500_000),
            (3, 3, "dozen", "dozens", 12_000),
        ):
            put(
                db,
                "food_size",
                id=size_id,
                household_id=1,
                food_id=food_id,
                name=name,
                plural=plural,
                amount_milli=milli,
                usual=True,
                added_when_shopping=False,
                position=0,
            )
        put(db, "food_name", id=1, household_id=1, food_id=2, name="thuvaram paruppu")
        for lot_id, food_id, place_id, milli, added in (
            (1, 1, fridge, 200_000, "2026-10-17"),  # Paneer: 200 g typed
            (2, 1, fridge, 0, "2026-10-17"),  # Paneer: a pack, taken back by an Undo
            (3, 2, cupboard, 500_000, "2026-10-17"),
            (4, 2, cupboard, 500_000, "2026-10-18"),  # a second packet of Toor dal
            (5, 3, fridge, 12_000, "2026-10-17"),
        ):
            put(
                db,
                "stock_lot",
                id=lot_id,
                household_id=1,
                food_id=food_id,
                place_id=place_id,
                amount_milli=milli,
                added_at=added,
            )
        for change_id, kind, food_id, summary in (
            (1, "added", 1, "Added 200 g Paneer → Fridge"),
            (2, "added", 1, "Added 1 pack Paneer → Fridge"),
            (3, "added", 2, "Added 2 packets Toor dal → Cupboard"),
            (4, "undo", 1, "Undid: Added 1 pack Paneer → Fridge"),
            (5, "added", 3, "Added 1 dozen Eggs → Fridge"),
        ):
            put(
                db,
                "change",
                id=change_id,
                household_id=1,
                request=f"r{change_id}",
                kind=kind,
                login_id=1,
                login_name="Tess",
                food_id=food_id,
                at=f"2026-10-17 10:0{change_id}:00",
                summary=summary,
            )
        db.execute(text("UPDATE change SET undone_by_change_id = 4 WHERE id = 2"))
        db.execute(text("UPDATE change SET undoes_change_id = 2 WHERE id = 4"))
        for change_id, food_id, lot_id, before, after, place_before, place_after in (
            (1, 1, 1, 0, 200_000, None, fridge),
            (2, 1, 2, 0, 200_000, None, fridge),
            (3, 2, 3, 0, 500_000, None, cupboard),
            (3, 2, 4, 0, 500_000, None, cupboard),
            (4, 1, 2, 200_000, 0, fridge, fridge),
            (5, 3, 5, 0, 12_000, None, fridge),
        ):
            put(
                db,
                "change_line",
                household_id=1,
                change_id=change_id,
                food_id=food_id,
                lot_id=lot_id,
                amount_before_milli=before,
                amount_after_milli=after,
                place_before_id=place_before,
                place_after_id=place_after,
            )
    return engine


def _wording(app: TestClient) -> dict[int, list[tuple[str, str]]]:
    changes = app.get("/api/v1/changes", params={"area": "pantry"}).json()["changes"]
    return {
        c["id"]: [(t["before"]["display"], t["after"]["display"]) for t in c["totals"]]
        for c in changes
    }


def test_upgrading_a_0_2_0_database_keeps_everything_and_old_changes_read_as_before(
    settings: Settings,
) -> None:
    settings.data_dir.mkdir(parents=True)
    engine = _make_0_2_0_database(settings.data_dir / "mealwright.db")
    with engine.connect() as db:
        lines_before = db.execute(
            text(
                "SELECT id, change_id, lot_id, amount_before_milli, amount_after_milli"
                " FROM change_line ORDER BY id"
            )
        ).fetchall()
    engine.dispose()

    with TestClient(create_app(settings), base_url="https://testserver") as app:
        # The new columns are there and empty on every old line; nothing else moved.
        with app.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
            rows = session.execute(
                text(
                    "SELECT id, change_id, lot_id, amount_before_milli, amount_after_milli,"
                    " total_before_milli, total_after_milli FROM change_line ORDER BY id"
                )
            ).fetchall()
            assert [tuple(r[:5]) for r in rows] == [tuple(r) for r in lines_before]
            assert all(r[5] is None and r[6] is None for r in rows)
            counts = {
                name: session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()  # noqa: S608
                for name in ("household", "food", "food_size", "food_name", "stock_lot", "change")
            }
            assert counts == {
                "household": 2,
                "food": 4,
                "food_size": 3,
                "food_name": 1,
                "stock_lot": 5,
                "change": 5,
            }

        signed_in = app.post(
            "/api/v1/session", json={"username": "tess", "password": "correct horse battery"}
        )
        assert signed_in.status_code == 200, signed_in.text

        # Old changes keep their old wording: only the packets they touched.
        old = _wording(app)
        assert old[2] == [(f"0{NB}g", f"1{NB}pack · 200{NB}g")]  # not "1 pack → 2 packs"
        assert old[4] == [(f"1{NB}pack · 200{NB}g", f"0{NB}g")]
        assert old[3] == [(f"0{NB}g", f"2{NB}packets · 1{NB}kg")]
        assert app.get("/api/v1/foods/1").json()["stock"]["amount"] == 200.0
        assert app.get("/api/v1/foods", params={"q": "thuvaram"}).json()["foods"][0]["name"] == (
            "Toor dal"
        )

        fridge = next(p["id"] for p in app.get("/api/v1/places").json() if p["name"] == "Fridge")
        # A change made after the upgrade shows the whole amount; the old ones stay as they were.
        added = app.post(
            "/api/v1/stock",
            json={"food_id": 1, "amount": {"amount": 1, "unit": "pack"}, "place_id": fridge},
        )
        assert added.status_code == 201, added.text
        new = _wording(app)
        newest = max(new)
        assert new[newest] == [(f"1{NB}pack · 200{NB}g", f"2{NB}packs · 400{NB}g")]
        assert {key: value for key, value in new.items() if key != newest} == old

        # Undoing an old change still reverses just its own lines.
        undone = app.post("/api/v1/changes/1/undo")
        assert undone.status_code == 200, undone.text
        assert app.get("/api/v1/foods/1").json()["stock"]["amount"] == 200.0  # the new pack stays


def test_0_2_1_migration_goes_back_and_forward(tmp_path: Path) -> None:
    engine = _make_0_2_0_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "b4391aaf7695")
    with engine.connect() as db:
        columns = [c["name"] for c in inspect(db).get_columns("change_line")]
        assert "total_before_milli" not in columns
        assert db.execute(text("SELECT count(*) FROM change_line")).scalar_one() == 6
    migrate.upgrade(engine)
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM change_line")).scalar_one() == 6
