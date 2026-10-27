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
PLAN_COLUMNS = {"tub_fridge_days", "tub_freezer_months", "plan_ahead_days", "week_starts_on"}


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
    skip = {*PLAN_TABLES, "staple_check", "alembic_version"}
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
    skip = {"staple_check", "alembic_version"}
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
