from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, column, insert, inspect, text
from sqlalchemy import table as sql_table
from sqlalchemy.exc import IntegrityError

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
    tmp_path: Path,
) -> None:
    # Its own empty data folder: the `settings` fixture comes with a new database already in it.
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
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
        assert old[2] == [(f"0{NB}g", f"200{NB}g · 1{NB}pack")]  # not "1 pack → 2 packs"
        assert old[4] == [(f"200{NB}g · 1{NB}pack", f"0{NB}g")]
        assert old[3] == [(f"0{NB}g", f"1{NB}kg · 2{NB}packets")]
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
        assert new[newest] == [(f"200{NB}g · 1{NB}pack", f"400{NB}g · 2{NB}packs")]
        assert {key: value for key, value in new.items() if key != newest} == old

        # Undoing an old change still reverses just its own lines. The made-up 0.2.0 changes
        # are dated 17 Oct and Undo reaches back only a week, so move change 1 to now first.
        with app.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
            session.execute(
                text("UPDATE change SET at = :now WHERE id = 1"),
                {"now": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")},
            )
            session.commit()
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


def _make_0_2_database(path: Path) -> Engine:
    """A 0.2.1 database (a7c3e51d9b02): two households, foods, a lot, a change and its line."""
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, "a7c3e51d9b02")
    with engine.begin() as connection:
        for h in (1, 2):
            for sql in (
                "INSERT INTO household (id, name, created_at) VALUES (:h, 'Home', '2026-10-01')",
                "INSERT INTO login (id, household_id, username, name, password_hash, role,"
                " theme, created_at) VALUES (:h, :h, 'user' || :h, 'User', 'x', 'admin', 'auto',"
                " '2026-10-01')",
                "INSERT INTO place (id, household_id, name, kind, position, created_at)"
                " VALUES (:h, :h, 'Fridge', 'fridge', 0, '2026-10-01')",
                "INSERT INTO food (id, household_id, name, counted_as, staple, created_at)"
                " VALUES (:h, :h, 'Toor dal', 'weight', 0, '2026-10-02')",
                "INSERT INTO stock_lot (id, household_id, food_id, place_id, amount_milli,"
                " added_at) VALUES (:h, :h, :h, :h, 500000, '2026-10-03')",
                "INSERT INTO change (id, household_id, request, kind, login_id, login_name,"
                " food_id, at, summary) VALUES (:h, :h, 'POST /api/v1/stock', 'added', :h,"
                " 'User', :h, '2026-10-03', 'Added 500 g Toor dal')",
                "INSERT INTO change_line (id, household_id, change_id, food_id, lot_id,"
                " amount_before_milli, amount_after_milli, total_before_milli,"
                " total_after_milli) VALUES (:h, :h, :h, :h, :h, 0, 500000, 0, 500000)",
            ):
                connection.execute(text(sql), {"h": h})
    return engine


def test_shopping_lists_migration_keeps_data_and_gives_each_household_a_main_list(
    tmp_path: Path,
) -> None:
    engine = _make_0_2_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    with engine.connect() as connection:
        lists = connection.exec_driver_sql(
            "SELECT household_id, name, main, position, removed_at FROM shopping_list"
            " ORDER BY household_id"
        ).all()
        assert [tuple(row) for row in lists] == [
            (1, "This week", 1, 0, None),
            (2, "This week", 1, 0, None),
        ]
        ids = connection.exec_driver_sql("SELECT id FROM shopping_list").scalars().all()
        assert len(set(ids)) == 2 and all(len(i) == 36 for i in ids)
        # Everything that was there still is, with the new columns at their defaults.
        assert connection.exec_driver_sql("SELECT count(*) FROM stock_lot").scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT summary FROM change WHERE id = 1"
        ).scalar_one() == ("Added 500 g Toor dal")
        food = connection.exec_driver_sql(
            "SELECT name, aisle, version FROM food WHERE id = 1"
        ).one()
        assert tuple(food) == ("Toor dal", None, 0)
        household = connection.exec_driver_sql(
            "SELECT list_seq, list_purged_seq FROM household WHERE id = 2"
        ).one()
        assert tuple(household) == (0, 0)
        assert (
            connection.exec_driver_sql("SELECT tick_id FROM change WHERE id = 1").scalar_one()
            is None
        )
        for table in ("list_item", "list_tick", "sync_action", "list_note", "double_tick"):
            count = connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()  # noqa: S608
            assert count == 0, table
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


def test_shopping_lists_migration_downgrades_and_upgrades_again(tmp_path: Path) -> None:
    engine = _make_0_2_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "a7c3e51d9b02")
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert not tables & {"shopping_list", "list_item", "list_tick", "sync_action"}
        columns = {c["name"] for c in inspect(connection).get_columns("food")}
        assert "aisle" not in columns and "version" not in columns
        assert connection.exec_driver_sql("SELECT count(*) FROM stock_lot").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM change").scalar_one() == 2
    migrate.upgrade(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM shopping_list").scalar_one() == 2


def test_two_main_lists_in_one_household_are_refused(tmp_path: Path) -> None:
    from sqlalchemy.exc import IntegrityError

    engine = _make_0_2_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO shopping_list (id, household_id, name, main, position, created_at,"
            " created_by_name, version) VALUES ('a', 1, 'Second', 1, 1, '2026-10-18', '', 0)"
        )


def test_existing_ingredients_get_a_starting_aisle_only_when_linked_to_the_table(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, "a7c3e51d9b02")
    with engine.begin() as connection:
        for h in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO household (id, name, created_at) VALUES (:h, 'Home', '2026-10-01')"
                ),
                {"h": h},
            )
        foods = (
            (1, 1, "Cumin seeds", "cumin_seeds"),  # linked to the table
            (2, 1, "Toor dal", None),  # not in the table
            (3, 1, "Cumin", None),  # similar name, but no link: no guessing
            (4, 2, "Salt", None),  # the other household, unlinked
        )
        for food_id, h, name, key in foods:
            connection.execute(
                text(
                    "INSERT INTO food (id, household_id, name, counted_as, staple, table_key,"
                    " created_at) VALUES (:id, :h, :name, 'weight', 0, :key, '2026-10-02')"
                ),
                {"id": food_id, "h": h, "name": name, "key": key},
            )
    migrate.upgrade(engine)
    with engine.connect() as connection:
        aisles = dict(connection.exec_driver_sql("SELECT name, aisle FROM food").all())
    assert aisles == {"Cumin seeds": "spices", "Toor dal": None, "Cumin": None, "Salt": None}


# --- Recipes (0.4) -------------------------------------------------------------------------

RECIPE_TABLES = {
    "recipe",
    "recipe_line",
    "recipe_step",
    "tag",
    "recipe_tag",
    "recipe_photo",
}
BEFORE_RECIPES = "f509d7a1c609"  # 0.3.0
RECIPES = "c5e8a1f3b7d2"  # 0.4's first pull request


def _with_recipes(engine: Engine) -> None:
    """A recipe in each household, with a line that uses the other recipe, a step, a tag
    and a photo record, put in at RECIPES and then upgraded to the newest migration."""
    migrate.upgrade(engine, RECIPES)
    with engine.begin() as connection:
        for h in (1, 2):
            for sql in (
                "INSERT INTO recipe (id, household_id, name, serves, version, created_at,"
                " updated_at, updated_by_name, made_ahead) VALUES (:h, :h, 'Sambar', 4, 1,"
                " '2026-10-19', '2026-10-19', 'User', 0)",
                "INSERT INTO recipe_line (id, household_id, recipe_id, position, kind, words,"
                " amount_milli, unit, food_id) VALUES (:h, :h, :h, 0, 'ingredient', 'thuvaram',"
                " 200000, 'g', :h)",
                "INSERT INTO recipe_step (id, household_id, recipe_id, position, kind, text)"
                " VALUES (:h, :h, :h, 0, 'step', 'Boil the dal.')",
                "INSERT INTO tag (id, household_id, name) VALUES (:h, :h, 'Quick')",
                "INSERT INTO recipe_tag (household_id, recipe_id, tag_id) VALUES (:h, :h, :h)",
                "INSERT INTO recipe_photo (id, household_id, recipe_id, file_key, width, height,"
                " bytes, added_at, added_by_name) VALUES (:h, :h, :h, 'abc', 800, 600, 1000,"
                " '2026-10-19', 'User')",
            ):
                connection.execute(text(sql), {"h": h})
    migrate.upgrade(engine)


def test_recipes_migration_adds_the_tables_and_keeps_everything_else(tmp_path: Path) -> None:
    engine = _make_0_2_database(tmp_path / "old.db")
    migrate.upgrade(engine, BEFORE_RECIPES)
    assert not RECIPE_TABLES & set(inspect(engine).get_table_names())
    migrate.upgrade(engine)
    assert set(inspect(engine).get_table_names()) >= RECIPE_TABLES
    for table in RECIPE_TABLES:
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        assert "household_id" in columns, table
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM food").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM stock_lot").scalar_one() == 2


def test_recipes_migration_downgrades_and_upgrades_again(tmp_path: Path) -> None:
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    migrate.downgrade(engine, BEFORE_RECIPES)
    assert not RECIPE_TABLES & set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM food").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM change_line").scalar_one() == 2
    migrate.upgrade(engine)
    assert set(inspect(engine).get_table_names()) >= RECIPE_TABLES
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe").scalar_one() == 0


def test_recipe_rows_follow_their_household_and_the_database_keeps_the_rules(
    tmp_path: Path,
) -> None:
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    # A line may point at an ingredient or at a recipe, not both; serves is 1 to 99; a
    # recipe has one photo.
    bad = (
        "INSERT INTO recipe_line (household_id, recipe_id, position, kind, words, food_id,"
        " sub_recipe_id) VALUES (1, 1, 1, 'ingredient', 'x', 1, 1)",
        "INSERT INTO recipe_line (household_id, recipe_id, position, kind, words)"
        " VALUES (1, 1, 1, 'note', 'x')",
        "INSERT INTO recipe (household_id, name, serves, version, created_at, updated_at,"
        " updated_by_name, made_ahead) VALUES (1, 'Big', 100, 1, '2026-10-19', '2026-10-19',"
        " '', 0)",
        "INSERT INTO recipe_photo (household_id, recipe_id, file_key, width, height,"
        " list_width, list_height, bytes, added_at, added_by_name)"
        " VALUES (1, 1, 'second', 1, 1, 1, 1, 1, '2026-10-19', '')",
    )
    for sql in bad:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(sql))
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        # Deleting a recipe takes its lines, steps, tag links and photo with it; deleting an
        # ingredient only unlinks the lines that used it.
        connection.exec_driver_sql("DELETE FROM food WHERE id = 2")
        connection.exec_driver_sql("DELETE FROM recipe WHERE id = 1")
        counts = {
            table: connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()  # noqa: S608
            for table in ("recipe", "recipe_line", "recipe_step", "recipe_tag", "recipe_photo")
        }
    assert counts == {
        "recipe": 1,
        "recipe_line": 1,
        "recipe_step": 1,
        "recipe_tag": 1,
        "recipe_photo": 1,
    }
    with engine.connect() as connection:
        link = connection.exec_driver_sql("SELECT food_id FROM recipe_line").scalar_one()
    # The remaining line is household 2's, whose ingredient we deleted: unlinked, words kept.
    assert link is None


def test_recipe_tables_never_reuse_an_id(tmp_path: Path) -> None:
    """Like the other tables, so Undo can put a row back with its old id."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    with engine.connect() as connection:
        for table in sorted(RECIPE_TABLES - {"recipe_tag"}):
            sql = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = ?", (table,)
            ).scalar_one()
            assert "AUTOINCREMENT" in sql, table


PHOTO_UPLOADS = "97d61f9dd082"  # 0.4's photos pull request


def _photos(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id, household_id, recipe_id, file_key, width, height FROM recipe_photo"
                " ORDER BY id"
            )
        ]


def test_photo_uploads_migration_keeps_a_recipe_database_and_goes_back(tmp_path: Path) -> None:
    """A database already at the recipes migration, with a recipe and its photo record,
    gets the new columns; going back keeps the saved photo and forgets unsaved uploads."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)  # put in at RECIPES, then upgraded to the newest
    before = [(1, 1, 1, "abc", 800, 600), (2, 2, 2, "abc", 800, 600)]
    assert _photos(engine) == before
    with engine.begin() as connection:
        sizes = connection.exec_driver_sql("SELECT list_width, list_height FROM recipe_photo").all()
        assert [tuple(row) for row in sizes] == [(0, 0), (0, 0)]
        # An upload that isn't on a recipe yet: allowed now, more than one per household.
        for key in ("u1", "u2"):
            connection.execute(
                text(
                    "INSERT INTO recipe_photo (household_id, recipe_id, file_key, width, height,"
                    " list_width, list_height, bytes, added_at, added_by_name)"
                    " VALUES (1, NULL, :key, 10, 10, 10, 10, 1, '2026-10-20', '')"
                ),
                {"key": key},
            )
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe").scalar_one() == 2
    columns = {c["name"]: c for c in inspect(engine).get_columns("recipe_photo")}
    assert columns["recipe_id"]["nullable"] is True
    assert columns["list_width"]["default"] is None

    migrate.downgrade(engine, RECIPES)
    assert _photos(engine) == before
    columns = {c["name"]: c for c in inspect(engine).get_columns("recipe_photo")}
    assert "list_width" not in columns
    assert columns["recipe_id"]["nullable"] is False
    migrate.upgrade(engine)
    assert _photos(engine) == before
    assert migrate_head(engine) == newest_migration()
    with engine.connect() as connection:
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'recipe_photo'"
        ).scalar_one()
        indexes = {i["name"] for i in inspect(engine).get_indexes("recipe_photo")}
    assert "AUTOINCREMENT" in sql
    assert "ix_recipe_photo_household_id" in indexes


def newest_migration() -> str:
    return str(ScriptDirectory.from_config(migrate.alembic_config()).get_current_head())


def migrate_head(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        )


OWN_NETWORK = "63a26f6309e7"  # 0.5's fetching pull request: the migration just before the source


def test_recipe_source_migration_keeps_recipes_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.5 PR 3: a recipe gets its web address, import date and author (all empty for the
    recipes already there); going back drops them and keeps the recipes; again forward works."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)  # upgraded to the newest
    wanted = {"source_url", "imported_at", "source_author"}
    assert wanted <= {c["name"] for c in inspect(engine).get_columns("recipe")}
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE recipe SET source_url = 'https://kitchen.example/dal',"
            " source_author = 'A cook', imported_at = '2026-10-23' WHERE id = 1"
        )
    migrate.downgrade(engine, OWN_NETWORK)
    assert not wanted & {c["name"] for c in inspect(engine).get_columns("recipe")}
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe").scalar_one() == 2
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'recipe'"
        ).scalar_one()
    assert "AUTOINCREMENT" in sql
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT source_url, imported_at, source_author FROM recipe"
        ).all()
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'recipe'"
        ).scalar_one()
    assert [tuple(r) for r in rows] == [(None, None, None)] * 2
    assert "AUTOINCREMENT" in sql


RECIPE_SOURCE = "5b2e9d41a7c3"  # 0.5 PR 3's migration: the one just before the drafts


def test_drafts_migration_keeps_recipes_and_photos_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.5 PR 5: a drafts table and `recipe_photo.draft_id` (empty for every photo already
    there). Going back drops both, deletes the photo records the drafts held, and keeps the
    recipes and their photos; forward again works, with the id rule and the index kept."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)  # upgraded to the newest
    assert "import_draft" in inspect(engine).get_table_names()
    assert "draft_id" in {c["name"] for c in inspect(engine).get_columns("recipe_photo")}
    with engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT draft_id FROM recipe_photo").all() == [
            (None,),
            (None,),
        ]
        connection.exec_driver_sql(
            "INSERT INTO import_draft (id, household_id, source_kind, source_text, name, review,"
            " choices, lines_total, lines_checked, started_by_name, created_at, updated_at)"
            " VALUES (1, 1, 'text', 'Sambar', 'Sambar', '{}', '{}', 0, 0, 'User', '2026-10-24',"
            " '2026-10-24')"
        )
        connection.exec_driver_sql(
            "INSERT INTO recipe_photo (household_id, recipe_id, draft_id, file_key, width,"
            " height, list_width, list_height, bytes, added_at, added_by_name) VALUES (1, NULL,"
            " 1, 'kept', 10, 10, 10, 10, 1, '2026-10-24', '')"
        )
        # A draft only has a known kind of source.
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO import_draft (household_id, source_kind, source_text, name, review,"
                " choices, lines_total, lines_checked, started_by_name, created_at, updated_at)"
                " VALUES (1, 'fax', 'x', 'x', '{}', '{}', 0, 0, '', '2026-10-24', '2026-10-24')"
            )

    migrate.downgrade(engine, RECIPE_SOURCE)
    assert "import_draft" not in inspect(engine).get_table_names()
    assert "draft_id" not in {c["name"] for c in inspect(engine).get_columns("recipe_photo")}
    assert [r[0] for r in _photo_keys(engine)] == ["abc", "abc"]  # the draft's photo record is gone
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe").scalar_one() == 2
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    with engine.connect() as connection:
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'recipe_photo'"
        ).scalar_one()
        drafts_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'import_draft'"
        ).scalar_one()
        assert connection.exec_driver_sql("SELECT draft_id FROM recipe_photo").all() == [
            (None,),
            (None,),
        ]
    indexes = {i["name"] for i in inspect(engine).get_indexes("recipe_photo")}
    assert "AUTOINCREMENT" in sql and "AUTOINCREMENT" in drafts_sql
    assert {"ix_recipe_photo_draft_id", "ix_recipe_photo_household_id"} <= indexes


def _photo_keys(engine: Engine) -> list[tuple[str]]:
    with engine.connect() as connection:
        return [tuple(r) for r in connection.exec_driver_sql("SELECT file_key FROM recipe_photo")]


DRAFTS = "d7a4c2e81f56"  # 0.5 PR 5's migration: the one just before the plan tables
PLAN_TABLES = ("meal_slot", "meal", "meal_item", "batch_cook", "tub")
# Tables later migrations add: a test of an older migration leaves them out of its counts.
K1_TABLES = ("recipe_step_line", "cooked_record", "meal_eater")
PLAN_COLUMNS = {"tub_fridge_days", "tub_freezer_months", "plan_ahead_days", "week_starts_on"}


def _table_sql(engine: Engine, table: str) -> str:
    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).scalar_one()
        )


# The stocktake's two tables (0.8): the older migration tests go back past them, so they leave
# them out of their row counts.
STOCKTAKE_TABLES = {"stocktake_place", "stocktake_entry"}
METHOD_TABLES = {"recipe_method"}


def _row_counts(engine: Engine, skip: set[str]) -> dict[str, int]:
    names = [n for n in inspect(engine).get_table_names() if n not in skip]
    with engine.connect() as connection:
        return {
            n: connection.exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one()  # noqa: S608
            for n in sorted(names)
        }


def test_plan_migration_keeps_everything_adds_slots_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.6 PR 2: upgrading a 0.5.1 database keeps its rows, gives every household the default
    slots and the plan settings; going back drops the plan and keeps the rest; forward again
    gives the same slots."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)  # two households with a recipe each, upgraded to the newest
    skip = {
        *STOCKTAKE_TABLES,
        *METHOD_TABLES,
        *PLAN_TABLES,
        "staple_check",
        *K1_TABLES,
        "alembic_version",
    }
    before = _row_counts(engine, skip)
    assert before["recipe"] == 2 and before["food"] == 2 and before["household"] == 2
    migrate.downgrade(engine, DRAFTS)
    assert not set(PLAN_TABLES) & set(inspect(engine).get_table_names())
    assert not PLAN_COLUMNS & {c["name"] for c in inspect(engine).get_columns("household")}
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert set(PLAN_TABLES) <= set(inspect(engine).get_table_names())
    assert _row_counts(engine, skip) == before
    with engine.connect() as connection:
        slots = connection.exec_driver_sql(
            "SELECT household_id, name, position, enabled FROM meal_slot ORDER BY 1, 3"
        ).all()
        settings = connection.exec_driver_sql(
            "SELECT tub_fridge_days, tub_freezer_months, plan_ahead_days, week_starts_on"
            " FROM household"
        ).all()
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'meal'"
        ).scalar_one()
    names = [("Breakfast", 0, 1), ("Lunch", 1, 1), ("Snack", 2, 0), ("Dinner", 3, 1)]
    assert [tuple(s) for s in slots] == [(h, *n) for h in (1, 2) for n in names]
    assert [tuple(s) for s in settings] == [(3, 3, 7, 1)] * 2
    assert "AUTOINCREMENT" in sql
    # And once more round, from the full database.
    migrate.downgrade(engine, DRAFTS)
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert _row_counts(engine, skip) == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM meal_slot").scalar_one() == 8


PLAN_MIGRATION = "e3b7a95c4d18"  # 0.6 PR 2's migration: the one just before staple_check


def test_staple_check_migration_adds_one_table_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.6 PR 5: the "Got it" table is added empty; going back drops only it and keeps every
    other row; going forward again adds it empty; a row goes when its ingredient or household
    does, and one household's row can't be written twice for one ingredient."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "staple_check", *K1_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)
    assert "staple_check" in inspect(engine).get_table_names()
    migrate.downgrade(engine, PLAN_MIGRATION)
    assert "staple_check" not in inspect(engine).get_table_names()
    assert migrate_head(engine) == PLAN_MIGRATION
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    columns = {c["name"] for c in inspect(engine).get_columns("staple_check")}
    assert columns == {"food_id", "household_id", "item_ids", "at"}
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        food_id = connection.exec_driver_sql(
            "SELECT id FROM food WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO staple_check (food_id, household_id, item_ids, at)"
            " VALUES (?, 1, '[1, 2]', '2026-10-27 09:00:00')",
            (food_id,),
        )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO staple_check (food_id, household_id, item_ids, at)"
                " VALUES (?, 1, '[]', '2026-10-27 09:00:00')",
                (food_id,),
            )


STAPLE_MIGRATION = "a4c8e1f7b296"  # 0.6 PR 5's migration: the one just before household pints


def test_household_pints_migration_adds_one_column_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.6 PR 7: every household starts on UK pints; going back drops only the column and
    keeps every other row; going forward again puts every household back on UK pints."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, *K1_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)
    with engine.connect() as connection:
        households = connection.exec_driver_sql("SELECT count(*) FROM household").scalar_one()
        found = connection.exec_driver_sql("SELECT pints FROM household").scalars().all()
    assert found == ["uk"] * households
    migrate.downgrade(engine, STAPLE_MIGRATION)
    assert "pints" not in {c["name"] for c in inspect(engine).get_columns("household")}
    assert migrate_head(engine) == STAPLE_MIGRATION
    assert _row_counts(engine, skip) == before
    with engine.begin() as connection:  # a household made while it was gone has none
        connection.exec_driver_sql(
            "INSERT INTO household (name, created_at) VALUES ('Next', 'now')"
        )
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    column = next(c for c in inspect(engine).get_columns("household") if c["name"] == "pints")
    assert not column["nullable"]
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT pints FROM household").scalars().all()
    assert found == ["uk"] * (households + 1)


PINTS_MIGRATION = "c5f1b8d2a763"  # 0.6 PR 7's migration: the one just before the restock date


def test_restock_date_migration_marks_old_staple_ticks_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.7 K1: purchases made before it are marked as restocks when nothing went into the
    pantry and their ingredient is a staple; going back drops both columns and keeps every
    row; going forward again marks them again."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    migrate.downgrade(engine, PINTS_MIGRATION)
    with engine.begin() as connection:
        main = connection.exec_driver_sql(
            "SELECT id FROM shopping_list WHERE household_id = 1 AND main"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO food (id, household_id, name, counted_as, staple, created_at)"
            " VALUES (3, 1, 'Salt', 'weight', 1, '2026-10-02')"
        )
        for item, food in (("i-salt", 3), ("i-dal", 1)):
            connection.exec_driver_sql(
                "INSERT INTO list_item (id, household_id, list_id, food_id, source, hand_edited,"
                " added_at, added_by_name, version) VALUES (?, 1, ?, ?, 'typed', 0,"
                " '2026-10-20', 'User', 1)",
                (item, main, food),
            )
        for tick, item, bought in (("t-salt", "i-salt", None), ("t-dal", "i-dal", None)):
            connection.exec_driver_sql(
                "INSERT INTO list_tick (household_id, id, item_id, login_name, ticked_at,"
                " bought_milli) VALUES (1, ?, ?, 'User', '2026-10-21 10:00:00', ?)",
                (tick, item, bought),
            )
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, *K1_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)

    def marks() -> dict[str, int]:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT id, restock FROM list_tick").all()
        return {row[0]: row[1] for row in rows}

    migrate.upgrade(engine)
    assert marks() == {"t-salt": 1, "t-dal": 0}
    assert _row_counts(engine, skip) == before
    migrate.downgrade(engine, PINTS_MIGRATION)
    assert "restock" not in {c["name"] for c in inspect(engine).get_columns("list_tick")}
    assert "restocked_at" not in {c["name"] for c in inspect(engine).get_columns("food")}
    assert _row_counts(engine, skip) == before
    assert "AUTOINCREMENT" in _table_sql(engine, "food")  # the copy still never reuses an id
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert marks() == {"t-salt": 1, "t-dal": 0}
    assert _row_counts(engine, skip) == before


RESTOCK_MIGRATION = "b89c3c1918f8"  # 0.7 K1's restock date: the one just before step links


def test_step_links_migration_adds_one_table_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.7 K1: the step ↔ ingredient line table is added empty, recipe steps and lines keep
    every row, rule and "never reuse an id"; a link can't join two households and goes with
    its step; going back drops only the table and keeps every other row."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)  # a recipe with a line and a step in each of two households
    skip = {
        *STOCKTAKE_TABLES,
        *METHOD_TABLES,
        "recipe_step_line",
        "cooked_record",
        "meal_eater",
        "alembic_version",
    }
    before = _row_counts(engine, skip)
    migrate.downgrade(engine, RESTOCK_MIGRATION)
    assert "recipe_step_line" not in inspect(engine).get_table_names()
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    for table in ("recipe_step", "recipe_line"):
        sql = _table_sql(engine, table)
        assert "AUTOINCREMENT" in sql and "CHECK" in sql, table
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        add_row = (
            "INSERT INTO recipe_step_line (household_id, step_id, line_id, kind)"
            " VALUES (?, ?, ?, 'guessed')"
        )
        connection.exec_driver_sql(add_row, (1, 1, 1))
        for household_id, step_id, line_id in ((1, 1, 2), (2, 1, 2), (1, 2, 1)):
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(add_row, (household_id, step_id, line_id))
        connection.exec_driver_sql("DELETE FROM recipe_step WHERE id = 1")
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe_step_line").scalar() == 0
    after = _row_counts(engine, skip)
    migrate.downgrade(engine, RESTOCK_MIGRATION)
    assert _row_counts(engine, skip) == after
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")


STEP_LINKS_MIGRATION = "31a5838bc5a2"  # 0.7 K1's step links: the one just before cooked records


def test_cooked_records_migration_adds_one_table_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.7 K1: the cooked record table is added empty, meal items keep every row, rule and
    "never reuse an id"; a record can't reach into another household, is for a meal item or a
    batch (never both), and keeps its snapshot when the recipe goes; going back drops only the
    table."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    migrate.downgrade(engine, STEP_LINKS_MIGRATION)
    with engine.begin() as connection:
        slot = connection.exec_driver_sql(
            "SELECT id FROM meal_slot WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
            " VALUES (1, 1, '2026-10-30', ?, 'cooked', '2026-10-30')",
            (slot,),
        )
        connection.exec_driver_sql(
            "INSERT INTO meal_item (id, household_id, meal_id, position, kind, recipe_id)"
            " VALUES (1, 1, 1, 0, 'recipe', 1)"
        )
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "cooked_record", "meal_eater", "alembic_version"}
    before = _row_counts(engine, skip)
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    sql = _table_sql(engine, "meal_item")
    assert "AUTOINCREMENT" in sql and "ck_meal_item_one_of" in sql
    snapshot = '{"name": "Sambar", "version": 1, "servings": 4, "lines": [], "steps": []}'
    add_row = (
        "INSERT INTO cooked_record (household_id, meal_item_id, batch_id, recipe_id, portions,"
        " snapshot, cooked_at, cooked_by_name) VALUES (?, ?, ?, 1, 2, ?, '2026-10-30', 'User')"
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for household_id, item_id in ((2, 1), (1, None)):
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(add_row, (household_id, item_id, None, snapshot))
        connection.exec_driver_sql(add_row, (1, 1, None, snapshot))
        connection.exec_driver_sql("UPDATE meal_item SET name = 'Sambar', recipe_id = NULL")
        connection.exec_driver_sql("DELETE FROM recipe_line WHERE recipe_id = 1")
        connection.exec_driver_sql("DELETE FROM recipe_step WHERE recipe_id = 1")
        connection.exec_driver_sql("DELETE FROM recipe_tag WHERE recipe_id = 1")
        connection.exec_driver_sql("DELETE FROM recipe_photo WHERE recipe_id = 1")
        connection.exec_driver_sql("DELETE FROM recipe WHERE id = 1")
        kept = connection.exec_driver_sql("SELECT recipe_id, snapshot FROM cooked_record").one()
    assert kept[0] is None and "Sambar" in kept[1]
    after = _row_counts(engine, skip)
    migrate.downgrade(engine, STEP_LINKS_MIGRATION)
    assert "cooked_record" not in inspect(engine).get_table_names()
    assert _row_counts(engine, skip) == after
    assert "AUTOINCREMENT" in _table_sql(engine, "meal_item")
    migrate.upgrade(engine)
    assert _row_counts(engine, skip) == after


COOKED_RECORDS_MIGRATION = "6612736d5aae"  # 0.7 K1's cooked records: the one just before notes


def test_note_migration_changes_one_rule_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.7 P1: a meal item may be a note (text in `name`, no link); every row, key and "never
    reuse an id" stays; the old rule refuses a note; going back removes the notes (and a meal
    that held nothing else) and keeps everything else."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    migrate.downgrade(engine, COOKED_RECORDS_MIGRATION)
    old_sql = _table_sql(engine, "meal_item")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        slot = connection.exec_driver_sql(
            "SELECT id FROM meal_slot WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        for meal_id, day in ((1, "2026-11-02"), (2, "2026-11-03")):
            connection.exec_driver_sql(
                "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
                " VALUES (?, 1, ?, ?, 'planned', '2026-11-01')",
                (meal_id, day, slot),
            )
        connection.exec_driver_sql(
            "INSERT INTO meal_item (id, household_id, meal_id, position, kind, recipe_id)"
            " VALUES (1, 1, 1, 0, 'recipe', 1)"
        )
        with pytest.raises(IntegrityError):  # the old rule knows no note
            connection.exec_driver_sql(
                "INSERT INTO meal_item (household_id, meal_id, position, kind, name)"
                " VALUES (1, 2, 0, 'note', 'Eating out')"
            )
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "meal_eater", "alembic_version"}
    before = _row_counts(engine, skip)
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    sql = _table_sql(engine, "meal_item")
    assert "AUTOINCREMENT" in sql and "ck_meal_item_one_of" in sql and "'note'" in sql
    assert "'note'" not in old_sql
    add = (
        "INSERT INTO meal_item (household_id, meal_id, position, kind, name, recipe_id, food_id)"
        " VALUES (1, ?, ?, 'note', ?, ?, ?)"
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for bad in ((2, 0, None, None, None), (2, 0, "Out", 1, None), (2, 0, "Out", None, 1)):
            with pytest.raises(IntegrityError):  # a note is text and nothing else
                connection.exec_driver_sql(add, bad)
        connection.exec_driver_sql(add, (2, 0, "Eating out", None, None))  # alone in meal 2
        connection.exec_driver_sql(add, (1, 1, "Then ice cream", None, None))  # beside a recipe
        # A note can't reach into another household's meal.
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO meal_item (household_id, meal_id, position, kind, name)"
                " VALUES (2, 1, 0, 'note', 'Out')"
            )
        # A batch cooked for meal 2, whose recipe was taken out since: only the note is left.
        connection.exec_driver_sql(
            "INSERT INTO batch_cook (household_id, recipe_name, cook_meal_id, cooked_on,"
            " tub_count, pattern, created_at)"
            " VALUES (1, 'Dal', 2, '2026-11-03', 1, 'pick', '2026-11-01')"
        )
    migrate.downgrade(engine, COOKED_RECORDS_MIGRATION)
    assert _row_counts(engine, skip) == {
        **before,
        "meal": before["meal"] - 1,
        "batch_cook": before["batch_cook"] + 1,
    }
    with engine.connect() as connection:
        link = connection.exec_driver_sql("SELECT cook_meal_id FROM batch_cook").scalar_one()
    assert link is None  # the batch stays, no longer pointing at the meal that went
    with engine.connect() as connection:
        kinds = connection.exec_driver_sql("SELECT kind FROM meal_item").all()
        meals = connection.exec_driver_sql("SELECT id FROM meal ORDER BY id").all()
    assert [k[0] for k in kinds] == ["recipe"]  # the notes are gone
    assert [m[0] for m in meals] == [1]  # and the meal that held only a note
    assert "AUTOINCREMENT" in _table_sql(engine, "meal_item")
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()


NOTE_MIGRATION = "e0c4a7b19d35"  # 0.7 P1's notes: the one just before meal eaters


def test_meal_eaters_migration_adds_one_table_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.7 P1: the who's-eating table is added empty and every other row stays; a row can't
    reach into another household's meal, a person is ticked once per meal, and a row goes with
    its meal or its login; going back drops only the table."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "meal_eater", "alembic_version"}
    before = _row_counts(engine, skip)
    migrate.downgrade(engine, NOTE_MIGRATION)
    assert "meal_eater" not in inspect(engine).get_table_names()
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    names = {c["name"] for c in inspect(engine).get_columns("meal_eater")}
    assert {"household_id", "meal_id", "login_id"} <= names
    assert "AUTOINCREMENT" in _table_sql(engine, "meal_eater")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        slot = connection.exec_driver_sql(
            "SELECT id FROM meal_slot WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
            " VALUES (1, 1, '2026-11-02', ?, 'planned', '2026-11-01')",
            (slot,),
        )
        login = connection.exec_driver_sql(
            "SELECT id FROM login WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        add_row = "INSERT INTO meal_eater (household_id, meal_id, login_id) VALUES (?, 1, ?)"
        connection.exec_driver_sql(add_row, (1, login))
        with pytest.raises(IntegrityError):  # the same person twice
            connection.exec_driver_sql(add_row, (1, login))
        with pytest.raises(IntegrityError):  # household 2 can't tick a meal of household 1
            connection.exec_driver_sql(add_row, (2, login))
        connection.exec_driver_sql("DELETE FROM meal WHERE id = 1")
        assert connection.exec_driver_sql("SELECT count(*) FROM meal_eater").scalar() == 0
    after = _row_counts(engine, skip)
    migrate.downgrade(engine, NOTE_MIGRATION)
    assert "meal_eater" not in inspect(engine).get_table_names()
    assert _row_counts(engine, skip) == after
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()


MEAL_EATERS_MIGRATION = "f27b95d1c8a3"  # 0.7 P1's meal eaters: the one just before cook_per_step


def test_cook_per_step_migration_adds_one_column_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.7 K4: every household starts with the per-step switch off; going back drops only the
    column and keeps every other row; going forward again puts every household back to off."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)
    with engine.connect() as connection:
        households = connection.exec_driver_sql("SELECT count(*) FROM household").scalar_one()
        found = connection.exec_driver_sql("SELECT cook_per_step FROM household").scalars().all()
    assert found == [0] * households
    migrate.downgrade(engine, MEAL_EATERS_MIGRATION)
    assert "cook_per_step" not in {c["name"] for c in inspect(engine).get_columns("household")}
    assert migrate_head(engine) == MEAL_EATERS_MIGRATION
    assert _row_counts(engine, skip) == before
    with engine.begin() as connection:  # a household made while it was gone has none
        connection.exec_driver_sql(
            "INSERT INTO household (name, created_at) VALUES ('Next', 'now')"
        )
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    column = next(
        c for c in inspect(engine).get_columns("household") if c["name"] == "cook_per_step"
    )
    assert not column["nullable"]
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT cook_per_step FROM household").scalars().all()
    assert found == [0] * (households + 1)


COOK_PER_STEP_MIGRATION = "d2e6a4b81c37"  # 0.7 K4's switch: the one just before restock_typed_at


def test_restock_typed_at_migration_adds_one_column_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.7 K5 (cabledrawer 2 Nov, the date typed wins): every ingredient starts with no typed
    moment, so every date shown stays as it was; going back drops only the column and keeps
    every row and "never reuse an id"; going forward again adds it empty."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT restock_typed_at FROM food").scalars().all()
    assert found and set(found) == {None}
    with engine.begin() as connection:  # a typed date on one ingredient
        connection.exec_driver_sql(
            "UPDATE food SET restocked_at = '2026-10-28 11:00:00.000000',"
            " restock_typed_at = '2026-11-01 09:30:00.000000' WHERE id = 1"
        )

    def foods() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, household_id, name, counted_as, staple, place_id, shop_id, aisle,"
                " running_low_milli, merged_into_id, removed_at, created_at, restocked_at"
                " FROM food ORDER BY id"
            )
            return [tuple(row) for row in rows]

    held = foods()
    assert "2026-10-28 11:00:00.000000" in held[0]
    migrate.downgrade(engine, COOK_PER_STEP_MIGRATION)
    assert "restock_typed_at" not in {c["name"] for c in inspect(engine).get_columns("food")}
    assert migrate_head(engine) == COOK_PER_STEP_MIGRATION
    assert _row_counts(engine, skip) == before
    assert foods() == held  # the date and every other value stay
    assert "AUTOINCREMENT" in _table_sql(engine, "food")  # the copy still never reuses an id
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    column = next(c for c in inspect(engine).get_columns("food") if c["name"] == "restock_typed_at")
    assert column["nullable"]
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT restock_typed_at FROM food").scalars().all()
    assert set(found) == {None}
    assert _row_counts(engine, skip) == before
    assert foods() == held
    assert "AUTOINCREMENT" in _table_sql(engine, "food")


RESTOCK_TYPED_AT_MIGRATION = "5fbd6d33c434"  # the one just before date_kind


def test_date_kind_migration_adds_one_empty_column_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.8 (cabledrawer 7 Nov, Use by or Best before): every ingredient starts with no chosen date
    type, so each gets its default; going back drops only the column and keeps every row and
    "never reuse an id"; going forward again adds it empty."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT date_kind FROM food").scalars().all()
    assert found and set(found) == {None}
    with engine.begin() as connection:  # a choice made in the editor
        connection.exec_driver_sql("UPDATE food SET date_kind = 'use_by' WHERE id = 1")

    def foods() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, household_id, name, counted_as, staple, place_id, shop_id, aisle,"
                " running_low_milli, merged_into_id, removed_at, created_at, restocked_at"
                " FROM food ORDER BY id"
            )
            return [tuple(row) for row in rows]

    held = foods()
    migrate.downgrade(engine, RESTOCK_TYPED_AT_MIGRATION)
    assert "date_kind" not in {c["name"] for c in inspect(engine).get_columns("food")}
    assert migrate_head(engine) == RESTOCK_TYPED_AT_MIGRATION
    assert _row_counts(engine, skip) == before
    assert foods() == held
    assert "AUTOINCREMENT" in _table_sql(engine, "food")
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    column = next(c for c in inspect(engine).get_columns("food") if c["name"] == "date_kind")
    assert column["nullable"]
    with engine.connect() as connection:
        found = connection.exec_driver_sql("SELECT date_kind FROM food").scalars().all()
    assert set(found) == {None}
    assert _row_counts(engine, skip) == before
    assert foods() == held
    assert "AUTOINCREMENT" in _table_sql(engine, "food")


DATE_KIND_MIGRATION = "a8c3e5f71d24"  # the one just before the stocktake tables


def test_stocktake_migration_adds_two_empty_tables_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.8 (F118, cabledrawer 7 Nov): the stocktake's progress is two new, empty tables; going back
    drops only them and leaves every other row alone; going forward again makes them empty."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {"alembic_version", *STOCKTAKE_TABLES, *METHOD_TABLES}
    before = _row_counts(engine, skip)
    tables = STOCKTAKE_TABLES
    assert tables <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for table in tables:
            assert connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one() == 0  # noqa: S608
    with engine.begin() as connection:  # some progress, lost on the way back
        place_id, food_id = connection.exec_driver_sql(
            "SELECT (SELECT min(id) FROM place), (SELECT min(id) FROM food)"
        ).one()
        connection.exec_driver_sql(
            "INSERT INTO stocktake_place (household_id, place_id, finished_at)"
            " VALUES (1, ?, '2026-11-07')",
            (place_id,),
        )
        connection.exec_driver_sql(
            "INSERT INTO stocktake_entry (household_id, place_id, food_id, answered, at)"
            " VALUES (1, ?, ?, 1, '2026-11-07')",
            (place_id, food_id),
        )
    migrate.downgrade(engine, DATE_KIND_MIGRATION)
    assert not tables & set(inspect(engine).get_table_names())
    assert migrate_head(engine) == DATE_KIND_MIGRATION
    assert _row_counts(engine, skip) == before
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert tables <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for table in tables:
            assert connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one() == 0  # noqa: S608
    assert _row_counts(engine, skip) == before


STOCKTAKE_MIGRATION = "c7e2f4a9b816"  # the one just before places and shops stopped reusing ids


def test_place_and_shop_ids_migration_keeps_rows_and_never_reuses_an_id(tmp_path: Path) -> None:
    """0.8 release (security finding M1): `place` and `shop` are rebuilt with "never reuse an
    id": every row, id, index and link stays, an id removed after the upgrade is not handed out
    again, and going back rebuilds them without it. (A top id removed before the upgrade can be
    handed out once more: the counter starts at the highest id left; left as it is, cabledrawer
    8 Nov.)"""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    migrate.downgrade(engine, STOCKTAKE_MIGRATION)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO shop (household_id, name, position, created_at)"
            " VALUES (1, 'Corner shop', 0, '2026-11-01')"
        )
        shop_id = connection.exec_driver_sql("SELECT max(id) FROM shop").scalar_one()
        connection.exec_driver_sql("UPDATE food SET shop_id = ? WHERE id = 1", (shop_id,))
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    before = _row_counts(engine, skip)

    def rows() -> dict[str, list[tuple[object, ...]]]:
        with engine.connect() as connection:
            return {
                table: [
                    tuple(r)
                    for r in connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY id")  # noqa: S608
                ]
                for table in ("place", "shop")
            }

    held = rows()
    assert "AUTOINCREMENT" not in _table_sql(engine, "place")
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    for table in ("place", "shop"):
        assert "AUTOINCREMENT" in _table_sql(engine, table)
        assert {i["name"] for i in inspect(engine).get_indexes(table)} == {
            f"ix_{table}_household_id"
        }
    assert rows() == held
    assert _row_counts(engine, skip) == before
    with engine.begin() as connection:
        assert (
            connection.exec_driver_sql("SELECT shop_id FROM food WHERE id = 1").scalar_one()
            == shop_id
        )
        connection.exec_driver_sql("DELETE FROM food WHERE shop_id = ?", (shop_id,))
        connection.exec_driver_sql("DELETE FROM shop WHERE id = ?", (shop_id,))
        connection.exec_driver_sql(
            "INSERT INTO shop (household_id, name, position, created_at)"
            " VALUES (1, 'Next shop', 0, '2026-11-02')"
        )
        assert connection.exec_driver_sql("SELECT max(id) FROM shop").scalar_one() > shop_id
    migrate.downgrade(engine, STOCKTAKE_MIGRATION)
    for table in ("place", "shop"):
        assert "AUTOINCREMENT" not in _table_sql(engine, table)


PLACE_SHOP_IDS_MIGRATION = "d4f8b2c1a695"  # the one just before optional ingredients and steps


def test_optional_migration_adds_empty_columns_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.8 wave 4, R3 (cabledrawer 6 and 9 Nov): lines and steps start as not Optional, a planned
    recipe has no pick (every line counts) and no recipe has nutrition dates; going back drops
    only those columns and keeps every row and "never reuse an id"; going forward again adds
    them empty. The new columns are on tables that already have `household_id`."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}

    def columns(table: str) -> set[str]:
        return {c["name"] for c in inspect(engine).get_columns(table)}

    new = {
        "recipe_line": {"optional"},
        "recipe_step": {"optional"},
        "meal_item": {"optional_skipped"},
        "recipe": {"nutrition_set_at", "lines_changed_at"},
    }
    for table, names in new.items():
        assert names <= columns(table)
    with engine.connect() as connection:
        for sql in (
            "SELECT optional FROM recipe_line",
            "SELECT optional FROM recipe_step",
            "SELECT nutrition_set_at FROM recipe",
            "SELECT lines_changed_at FROM recipe",
        ):
            found = set(connection.exec_driver_sql(sql).scalars().all())
            assert found in ({0}, {None}), sql
    with engine.begin() as connection:  # something marked Optional, and a pick
        connection.exec_driver_sql("UPDATE recipe_line SET optional = 1 WHERE id = 1")
        connection.exec_driver_sql("UPDATE recipe_step SET optional = 1 WHERE id = 1")
        connection.exec_driver_sql(
            "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
            " SELECT 1, 1, '2026-11-12', min(id), 'planned', '2026-11-10' FROM meal_slot"
            " WHERE household_id = 1"
        )
        connection.exec_driver_sql(
            "INSERT INTO meal_item (id, household_id, meal_id, position, kind, recipe_id,"
            " optional_skipped) VALUES (1, 1, 1, 0, 'recipe', 1, '[1]')"
        )
    before = _row_counts(engine, skip)

    def kept() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            return [
                tuple(r)
                for r in connection.exec_driver_sql(
                    "SELECT id, household_id, recipe_id, position, kind, words, amount_milli,"
                    " unit, food_id FROM recipe_line ORDER BY id"
                )
            ]

    held = kept()
    migrate.downgrade(engine, PLACE_SHOP_IDS_MIGRATION)
    assert migrate_head(engine) == PLACE_SHOP_IDS_MIGRATION
    for table, names in new.items():
        assert not names & columns(table)
        assert "AUTOINCREMENT" in _table_sql(engine, table)
    assert _row_counts(engine, skip) == before
    assert kept() == held
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    for table, names in new.items():
        assert names <= columns(table)
        assert "AUTOINCREMENT" in _table_sql(engine, table)
    assert _row_counts(engine, skip) == before
    assert kept() == held
    with engine.connect() as connection:
        assert set(connection.exec_driver_sql("SELECT optional FROM recipe_line").scalars()) == {0}
        assert set(connection.exec_driver_sql("SELECT optional FROM recipe_step").scalars()) == {0}
        assert set(
            connection.exec_driver_sql("SELECT optional_skipped FROM meal_item").scalars()
        ) == {None}


OPTIONAL_MIGRATION = "b6d1f3a8c254"  # the one just before step waits


def test_step_wait_migration_adds_empty_columns_and_goes_back_and_forward(tmp_path: Path) -> None:
    """0.8 wave 5, M1 (cabledrawer 31 Oct and 9 Nov): every step starts with no wait; going back drops
    only the four wait columns and keeps every row and "never reuse an id"; going forward adds
    them empty again. The columns are on a table that already has `household_id`, and a recipe's
    single time is left as it was (nothing is guessed from old words)."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    names = {"wait_kind", "wait_min_minutes", "wait_max_minutes", "wait_overnight"}

    def columns() -> set[str]:
        return {c["name"] for c in inspect(engine).get_columns("recipe_step")}

    def kept() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            return [
                tuple(r)
                for r in connection.exec_driver_sql(
                    "SELECT s.id, s.household_id, s.recipe_id, s.position, s.kind, s.text,"
                    " s.optional, r.time_minutes FROM recipe_step s JOIN recipe r"
                    " ON r.id = s.recipe_id ORDER BY s.id"
                )
            ]

    assert names <= columns()
    assert "household_id" in columns()
    with engine.connect() as connection:
        assert set(connection.exec_driver_sql("SELECT wait_kind FROM recipe_step").scalars()) == {
            None
        }
        assert set(
            connection.exec_driver_sql("SELECT wait_overnight FROM recipe_step").scalars()
        ) == {0}
    with engine.begin() as connection:  # a step that waits
        connection.exec_driver_sql(
            "UPDATE recipe_step SET wait_kind = 'marinate', wait_min_minutes = 240,"
            " wait_max_minutes = 720, wait_overnight = 1 WHERE id = 1"
        )
    before = _row_counts(engine, skip)
    held = kept()
    migrate.downgrade(engine, OPTIONAL_MIGRATION)
    assert migrate_head(engine) == OPTIONAL_MIGRATION
    assert not names & columns()
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")
    assert _row_counts(engine, skip) == before
    assert kept() == held
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert names <= columns()
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")
    assert _row_counts(engine, skip) == before
    assert kept() == held
    with engine.connect() as connection:
        assert set(connection.exec_driver_sql("SELECT wait_kind FROM recipe_step").scalars()) == {
            None
        }


STEP_WAIT_MIGRATION = "e8a3c5b1d7f9"  # the one just before recipe methods


def test_methods_migration_gives_every_recipe_one_method_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.8 wave 5, M2 (cabledrawer 31 Oct and 9 Nov): every existing recipe becomes a recipe with
    one method holding its time, lines and steps (waits and Optional marks too), with nothing
    lost; going back keeps the first method as the recipe and drops a second one; forward again
    gives every recipe its method. The new table has `household_id`."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    assert "household_id" in {c["name"] for c in inspect(engine).get_columns("recipe_method")}

    def recipe_ids() -> list[int]:
        with engine.connect() as connection:
            return [
                int(i)
                for i in connection.exec_driver_sql("SELECT id FROM recipe ORDER BY id").scalars()
            ]

    def kept() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            lines = connection.exec_driver_sql(
                "SELECT id, household_id, recipe_id, position, kind, words, amount_milli, unit,"
                " food_id, optional FROM recipe_line ORDER BY id"
            )
            steps = connection.exec_driver_sql(
                "SELECT id, household_id, recipe_id, position, kind, text, optional,"
                " wait_kind, wait_min_minutes FROM recipe_step ORDER BY id"
            )
            times = connection.exec_driver_sql("SELECT id, time_minutes FROM recipe ORDER BY id")
            return [tuple(r) for r in [*lines, *steps, *times]]

    with engine.begin() as connection:  # a wait and an Optional mark, so they are shown to survive
        connection.exec_driver_sql(
            "UPDATE recipe_step SET wait_kind = 'marinate', wait_min_minutes = 240 WHERE id = 1"
        )
        connection.exec_driver_sql("UPDATE recipe_line SET optional = 1 WHERE id = 1")
    migrate.downgrade(engine, STEP_WAIT_MIGRATION)
    assert "recipe_method" not in inspect(engine).get_table_names()
    assert "method_id" not in {c["name"] for c in inspect(engine).get_columns("recipe_line")}
    # The tables that point at the ones rebuilt (meal items, lines, steps) hold rows too: a meal
    # with a cooked record, a step linked to a line, a batch cook, and a recipe that
    # uses another as a line (the database's ON DELETE CASCADE must not take them with the rebuild).
    with engine.begin() as connection:
        slot = connection.exec_driver_sql(
            "SELECT id FROM meal_slot WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
            " VALUES (1, 1, '2026-10-30', ?, 'cooked', '2026-10-30')",
            (slot,),
        )
        for sql in (
            "INSERT INTO meal_item (id, household_id, meal_id, position, kind, recipe_id)"
            " VALUES (1, 1, 1, 0, 'recipe', 1)",
            "INSERT INTO cooked_record (household_id, meal_item_id, batch_id, recipe_id, portions,"
            " snapshot, cooked_at, cooked_by_name) VALUES (1, 1, NULL, 1, 2,"
            " '{\"name\": \"Sambar\"}', '2026-10-30', 'User')",
            "INSERT INTO recipe_step_line (household_id, step_id, line_id, kind)"
            " VALUES (1, 1, 1, 'by_hand')",
            "INSERT INTO batch_cook (id, household_id, recipe_id, recipe_name, cook_meal_id,"
            " cooked_on, tub_count, pattern, created_at)"
            " VALUES (1, 1, 1, 'Sambar', 1, '2026-10-30', 2, 'pick', '2026-10-30')",
            "INSERT INTO recipe (id, household_id, name, serves, version, created_at,"
            " updated_at, updated_by_name, made_ahead) VALUES (3, 1, 'Nested', 2, 1,"
            " '2026-10-19', '2026-10-19', 'User', 0)",
            "INSERT INTO recipe_line (id, household_id, recipe_id, position, kind, words,"
            " sub_recipe_id) VALUES (3, 1, 3, 0, 'ingredient', 'sambar', 1)",
        ):
            connection.exec_driver_sql(sql)
    before = _row_counts(engine, skip)
    assert before["cooked_record"] == before["recipe_step_line"] == before["batch_cook"] == 1
    assert before["meal_item"] == 1 and before["recipe"] == 3
    held = kept()
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    assert kept() == held
    with engine.connect() as connection:
        # The rows that point at the rebuilt ones still point at them.
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM cooked_record c JOIN meal_item i ON i.id = c.meal_item_id"
            ).scalar_one()
            == 1
        )
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM recipe_step_line l JOIN recipe_step s ON s.id = l.step_id"
                " JOIN recipe_line r ON r.id = l.line_id"
            ).scalar_one()
            == 1
        )
        assert (
            connection.exec_driver_sql(
                "SELECT sub_recipe_id FROM recipe_line WHERE id = 3"
            ).scalar_one()
            == 1
        )
    with engine.connect() as connection:
        methods = connection.exec_driver_sql(
            "SELECT m.recipe_id, m.household_id, m.position, m.name, m.time_minutes,"
            " r.household_id, r.time_minutes FROM recipe_method m"
            " JOIN recipe r ON r.id = m.recipe_id ORDER BY m.recipe_id"
        ).all()
        assert [m[0] for m in methods] == recipe_ids()
        for _recipe, household, position, name, minutes, r_household, r_minutes in methods:
            assert (position, name) == (0, "")
            assert household == r_household and minutes == r_minutes
        for table in ("recipe_line", "recipe_step"):
            rows = connection.exec_driver_sql(
                f"SELECT t.method_id, m.recipe_id, t.recipe_id FROM {table} t"  # noqa: S608
                " LEFT JOIN recipe_method m ON m.id = t.method_id"
            ).all()
            assert rows
            assert all(method is not None and a == b for method, a, b in rows)
        assert set(connection.exec_driver_sql("SELECT method_id FROM meal_item").scalars()) <= {
            None
        }
    # A second method on one recipe, with a line and a step, goes when going back.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO recipe_method (id, household_id, recipe_id, position, name)"
            " SELECT 900, household_id, id, 1, 'Instant Pot' FROM recipe WHERE id = 1"
        )
        connection.exec_driver_sql(
            "INSERT INTO recipe_line (household_id, recipe_id, position, kind, words, method_id,"
            " optional) SELECT household_id, id, 50, 'ingredient', 'extra', 900, 0 FROM recipe"
            " WHERE id = 1"
        )
        connection.exec_driver_sql(
            "INSERT INTO recipe_step (household_id, recipe_id, position, kind, text, method_id,"
            " optional, wait_overnight) SELECT household_id, id, 50, 'step', 'press', 900, 0, 0"
            " FROM recipe WHERE id = 1"
        )
    migrate.downgrade(engine, STEP_WAIT_MIGRATION)
    assert migrate_head(engine) == STEP_WAIT_MIGRATION
    assert _row_counts(engine, skip) == before
    assert kept() == held
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_line")
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")
    migrate.upgrade(engine)
    assert _row_counts(engine, skip) == before
    assert kept() == held
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM recipe_method").scalar_one() == len(
            recipe_ids()
        )


METHODS_MIGRATION = "f1a6d3c8e502"  # the one just before the start times


def test_start_times_migration_adds_two_empty_columns_keeps_every_row_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.8 wave 5, M3 (cabledrawer 31 Oct and 9 Nov), database change 4 of 4: a planned meal can
    carry the time its wait will be started and the time it was. Both start empty, so a meal
    made before reads as it always did; nothing is lost; going back drops the two columns and
    keeps the meals, their cooked records and their "never reuse an id" numbering."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    migrate.downgrade(engine, METHODS_MIGRATION)
    assert migrate_head(engine) == METHODS_MIGRATION
    assert "start_at" not in {c["name"] for c in inspect(engine).get_columns("meal_item")}
    with engine.begin() as connection:
        slot = connection.exec_driver_sql(
            "SELECT id FROM meal_slot WHERE household_id = 1 LIMIT 1"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO meal (id, household_id, day, slot_id, status, created_at)"
            " VALUES (1, 1, '2026-10-30', ?, 'cooked', '2026-10-30')",
            (slot,),
        )
        connection.exec_driver_sql(
            "INSERT INTO meal_item (id, household_id, meal_id, position, kind, recipe_id, servings)"
            " VALUES (1, 1, 1, 0, 'recipe', 1, 3)"
        )
        connection.exec_driver_sql(
            "INSERT INTO cooked_record (household_id, meal_item_id, batch_id, recipe_id, portions,"
            " snapshot, cooked_at, cooked_by_name) VALUES (1, 1, NULL, 1, 2,"
            " '{\"name\": \"Sambar\"}', '2026-10-30', 'User')"
        )
    before = _row_counts(engine, skip)
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert _row_counts(engine, skip) == before
    columns = {c["name"]: c for c in inspect(engine).get_columns("meal_item")}
    assert columns["start_at"]["nullable"] and columns["started_at"]["nullable"]
    with engine.begin() as connection:
        row = connection.exec_driver_sql(
            "SELECT servings, start_at, started_at FROM meal_item WHERE id = 1"
        ).one()
        assert tuple(row) == (3, None, None)
        connection.exec_driver_sql(
            "UPDATE meal_item SET start_at = '2026-10-29 21:00:00',"
            " started_at = '2026-10-29 21:40:00' WHERE id = 1"
        )
    migrate.downgrade(engine, METHODS_MIGRATION)
    assert migrate_head(engine) == METHODS_MIGRATION
    assert {"start_at", "started_at"}.isdisjoint(
        c["name"] for c in inspect(engine).get_columns("meal_item")
    )
    assert _row_counts(engine, skip) == before
    assert "AUTOINCREMENT" in _table_sql(engine, "meal_item")
    with engine.connect() as connection:  # the cooked record still points at its meal item
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM cooked_record c JOIN meal_item i ON i.id = c.meal_item_id"
            ).scalar_one()
            == 1
        )
    migrate.upgrade(engine)
    assert _row_counts(engine, skip) == before


START_TIMES_MIGRATION = "a7c4e9d2b813"  # the one just before step timings and the kitchen


def test_step_timings_migration_adds_empty_columns_and_a_default_kitchen_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    """0.8 wave 6, B1 (cabledrawer 28 Oct and 11 Nov), Batch cook's database change 1 of 3: every
    step starts with nothing set by hand (so its timing is guessed from its words when read, and
    nothing needs filling in); every household starts with the usual kitchen (4 hob rings, 1
    pressure cooker, an oven) and has not been asked. Going back drops the columns and keeps
    every row and "never reuse an id"; forward again leaves them empty."""
    engine = _make_0_2_database(tmp_path / "old.db")
    _with_recipes(engine)
    skip = {*STOCKTAKE_TABLES, *METHOD_TABLES, "alembic_version"}
    step_names = {"timing_hands", "timing_minutes", "timing_equipment"}
    house_names = {
        "kitchen_hob_rings",
        "kitchen_pressure_cookers",
        "kitchen_oven",
        "kitchen_asked",
    }

    def columns(table: str) -> set[str]:
        return {c["name"] for c in inspect(engine).get_columns(table)}

    def kept() -> list[tuple[object, ...]]:
        with engine.connect() as connection:
            return [
                tuple(r)
                for r in connection.exec_driver_sql(
                    "SELECT id, household_id, recipe_id, position, kind, text, optional"
                    " FROM recipe_step ORDER BY id"
                )
            ]

    assert step_names <= columns("recipe_step") and "household_id" in columns("recipe_step")
    assert house_names <= columns("household")
    with engine.connect() as connection:
        found = connection.exec_driver_sql(
            "SELECT timing_hands, timing_minutes, timing_equipment FROM recipe_step"
        ).all()
        assert found and {tuple(f) for f in found} == {(None, None, None)}
        kitchens = connection.exec_driver_sql(
            "SELECT kitchen_hob_rings, kitchen_pressure_cookers, kitchen_oven, kitchen_asked"
            " FROM household"
        ).all()
    assert kitchens and {tuple(k) for k in kitchens} == {(4, 1, 1, 0)}
    with engine.begin() as connection:  # something set by hand, so it is shown to go
        connection.exec_driver_sql(
            "UPDATE recipe_step SET timing_hands = 'waiting', timing_minutes = 20,"
            " timing_equipment = 'pressure' WHERE id = 1"
        )
        connection.exec_driver_sql("UPDATE household SET kitchen_hob_rings = 2, kitchen_asked = 1")
    before = _row_counts(engine, skip)
    held = kept()
    migrate.downgrade(engine, START_TIMES_MIGRATION)
    assert migrate_head(engine) == START_TIMES_MIGRATION
    assert not step_names & columns("recipe_step")
    assert not house_names & columns("household")
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")
    assert _row_counts(engine, skip) == before
    assert kept() == held
    migrate.upgrade(engine)
    assert migrate_head(engine) == newest_migration()
    assert step_names <= columns("recipe_step") and house_names <= columns("household")
    assert "AUTOINCREMENT" in _table_sql(engine, "recipe_step")
    assert _row_counts(engine, skip) == before
    assert kept() == held
    with engine.connect() as connection:
        assert set(
            connection.exec_driver_sql("SELECT timing_hands FROM recipe_step").scalars()
        ) == {None}
        assert {
            tuple(k)
            for k in connection.exec_driver_sql(
                "SELECT kitchen_hob_rings, kitchen_asked FROM household"
            )
        } == {(4, 0)}
