# ruff: noqa: F811  (the fixtures are the household ones from test_problem_report, used by name)
"""Old names kept where they are written (beta fix5): every name a row once held is kept for as
long as log lines live, whatever path changed or deleted the row (Report a problem)."""

from datetime import timedelta

from fastapi.testclient import TestClient

from mealwright.config import Settings
from tests.test_problem_report import (  # noqa: F401  (the fixtures that set up the household)
    API,
    _ok,
    error,
    kitchen,
    log_folder,
    neighbour,
    report,
    write_log,
)
from tests.test_recipes import save as save_recipe


def _gone_from_both(
    kitchen: TestClient, neighbour: TestClient, settings: Settings, olds: list[str]
) -> None:
    write_log(
        log_folder(settings),
        [error(f"Couldn't save {old}", ago=timedelta(seconds=-2)) for old in olds],
    )
    for client in (kitchen, neighbour):
        text = "\n".join(report(client)["errors"]).lower()
        for old in olds:
            for word in old.lower().split():
                assert word not in text.replace("couldn't save", ""), (old, text)


def test_a_renamed_tag_and_a_tag_dropped_with_its_last_use_are_removed(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r4, M1: neither the tag rename nor the drop of an unused tag records a change."""
    _ok(
        kitchen.post(f"{API}/recipes", json={"name": "Plain one", "tags": ["Gwendolyn favourites"]})
    )
    tags = {t["name"]: t["id"] for t in _ok(kitchen.get(f"{API}/recipes/tags"))["tags"]}
    _ok(
        kitchen.patch(
            f"{API}/recipes/tags/{tags['Gwendolyn favourites']}", json={"name": "Keepers"}
        )
    )
    other = _ok(
        kitchen.post(
            f"{API}/recipes",
            json={"name": "Second one", "tags": ["Ptolemy picks"]},
            headers={"Idempotency-Key": "a1"},
        )
    )
    _ok(save_recipe(kitchen, other, tags=[]))
    _gone_from_both(kitchen, neighbour, settings, ["Gwendolyn favourites", "Ptolemy picks"])


def test_a_recipe_renamed_without_a_key_is_removed_by_its_old_name(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r4, M2: made with no Idempotency-Key, so recipe_created was never recorded, and
    recipe_saved keeps only the new name."""
    made = _ok(kitchen.post(f"{API}/recipes", json={"name": "Hortensia rhubarb crumble"}))
    _ok(save_recipe(kitchen, made, name="Crumble"))
    _gone_from_both(kitchen, neighbour, settings, ["Hortensia rhubarb crumble"])


# --- The hook, for every column the Scrubber treats as a name ----------------------------------

import re  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import (  # noqa: E402
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    create_engine,
    delete,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import Session  # noqa: E402

from mealwright import former_names, models  # noqa: E402
from mealwright.db import Base  # noqa: E402


def _filled(cls: type, **given: Any) -> Any:
    """One row of a model with every required column given a plain value (foreign keys are not
    enforced in these tests: only the name columns matter)."""
    values: dict[str, Any] = {}
    for column in inspect(cls).columns:
        if column.key in given or column.nullable or column.default is not None:
            continue
        if column.server_default is not None or column.autoincrement is True:
            continue
        if column.primary_key and isinstance(column.type, Integer):
            continue
        kind = column.type
        if isinstance(kind, Boolean):
            values[column.key] = False
        elif isinstance(kind, Integer):
            values[column.key] = 1
        elif isinstance(kind, DateTime):
            values[column.key] = datetime.now(UTC)
        elif isinstance(kind, Date):
            values[column.key] = datetime.now(UTC).date()
        elif isinstance(kind, String):
            values[column.key] = str(uuid.uuid4())
        else:
            values[column.key] = {}
    return cls(**{**values, **given})


@pytest.fixture
def raw() -> Any:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.execute(text("PRAGMA ignore_check_constraints=ON"))  # only the names matter here
        yield db


def _columns() -> list[tuple[type, str, str]]:
    return [
        (cls, key, kind)
        for cls, fields in sorted(former_names._columns().items(), key=lambda i: i[0].__name__)
        for key, kind in fields
    ]


def _kept(db: Session, name: str) -> list[str]:
    return list(db.scalars(select(models.FormerName.kind).where(models.FormerName.name == name)))


@pytest.mark.parametrize(
    ("cls", "key", "kind"), _columns(), ids=lambda v: getattr(v, "__name__", v)
)
def test_a_name_that_changes_or_goes_through_the_orm_is_kept(
    raw: Session, cls: type, key: str, kind: str
) -> None:
    household = 1
    given: dict[str, Any] = {key: f"Alpha {key} Quimby"}
    if cls is models.Household:
        given["id"] = household
    else:
        given["household_id"] = household
    row = _filled(cls, **given)
    raw.add(row)
    raw.commit()
    assert _kept(raw, f"Alpha {key} Quimby") == []
    setattr(row, key, f"Beta {key} Quimby")
    raw.commit()
    assert _kept(raw, f"Alpha {key} Quimby") == [kind]  # the old value, on a rename
    if cls is models.Household:
        return  # a household goes through Delete everything (tested below)
    raw.delete(row)
    raw.commit()
    assert _kept(raw, f"Beta {key} Quimby") == [kind]  # the current value, on a delete


@pytest.mark.parametrize(
    ("cls", "key", "kind"), _columns(), ids=lambda v: getattr(v, "__name__", v)
)
def test_a_name_that_goes_in_a_bulk_delete_or_update_is_kept(
    raw: Session, cls: type, key: str, kind: str
) -> None:
    given: dict[str, Any] = {key: f"Gamma {key} Quimby"}
    if cls is models.Household:
        pytest.skip("Delete everything keeps nothing")
    given["household_id"] = 1
    raw.add(_filled(cls, **given))
    raw.commit()
    raw.execute(
        update(cls).where(getattr(cls, key) == f"Gamma {key} Quimby").values({key: "Delta"})
    )
    raw.commit()
    assert _kept(raw, f"Gamma {key} Quimby") == [kind]  # an update that sets the name
    raw.execute(delete(cls).where(getattr(cls, key) == "Delta"))
    raw.commit()
    assert _kept(raw, "Delta") == [kind]  # a bulk delete


def test_a_bulk_update_of_something_else_keeps_no_name(raw: Session) -> None:
    raw.add(_filled(models.Shop, household_id=1, name="Mercer & Sons"))
    raw.commit()
    raw.execute(update(models.Shop).values(position=3))
    raw.commit()
    assert _kept(raw, "Mercer & Sons") == []


def test_names_that_go_with_their_parent_by_a_database_cascade_are_kept(raw: Session) -> None:
    """A tub's meal items go with it (ON DELETE CASCADE): the session never sees them."""
    raw.execute(text("PRAGMA foreign_keys=ON"))
    raw.add(_filled(models.Household, id=1, name="Home"))
    raw.commit()
    recipe = _filled(models.Recipe, household_id=1, name="Granny Stew")
    raw.add(recipe)
    raw.commit()
    raw.add(_filled(models.RecipeMethod, household_id=1, recipe_id=recipe.id, name="Slow way"))
    raw.commit()
    raw.execute(delete(models.Recipe).where(models.Recipe.id == recipe.id))
    raw.commit()
    assert _kept(raw, "Granny Stew") == ["recipe"]
    assert _kept(raw, "Slow way") == ["recipe_text"]  # the method went with the recipe


def test_delete_everything_keeps_no_name_and_the_old_lines_stay_out_of_the_report(
    kitchen: TestClient, settings: Settings
) -> None:
    """The household's rows, former names included, go with it (ON DELETE CASCADE), and nothing
    is written on the way. The log lines from before are covered because the report leaves out
    every line from before the new set-up (api/v1/report.py), so none is shown to be scrubbed."""
    from conftest import ADMIN

    _ok(
        kitchen.post(f"{API}/recipes", json={"name": "Plain one", "tags": ["Gwendolyn favourites"]})
    )
    _ok(kitchen.patch(f"{API}/household", json={"name": "Thistlewick Burrow"}))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert "Home" in list(db.scalars(select(models.FormerName.name)))
    write_log(log_folder(settings), [error("Couldn't save Thistlewick Burrow")])
    body = {"words": "delete everything", "password": ADMIN["password"]}
    assert kitchen.post(f"{API}/delete-everything", json=body).status_code == 204
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert list(db.scalars(select(models.FormerName))) == []
    assert kitchen.post(f"{API}/setup", json=ADMIN).status_code == 201
    write_log(log_folder(settings), [error("Couldn't save Gwendolyn", ago=timedelta(seconds=-2))])
    text = "\n".join(report(kitchen)["errors"])
    assert "Thistlewick" not in text, text
    assert "Couldn't save" in text, text


def test_the_log_tidy_deletes_names_older_than_the_log_files_plus_a_day(
    kitchen: TestClient,
) -> None:
    from datetime import timedelta as delta

    now = datetime.now(UTC)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        for age, name in ((13, "Fresh"), (14.5, "Day over"), (15.5, "Old")):
            db.add(
                models.FormerName(
                    household_id=1, kind="person", name=name, at=now - delta(days=age)
                )
            )
        db.commit()
        assert former_names.remove_expired(db, now) == 1
        assert sorted(db.scalars(select(models.FormerName.name))) == ["Day over", "Fresh"]


# Columns whose key says name, title or label and that are NOT a name the Scrubber removes.
_NOT_A_NAME: dict[tuple[str, str], str] = {
    ("FoodSize", "name"): "a size word (tin, bunch, packet): an everyday word, not a name",
    ("FormerName", "name"): "this table: the kept names themselves",
}


def test_every_column_that_looks_like_a_name_is_kept_or_says_why_not() -> None:
    """A guard: a new column called *name*, *title* or *label* is either one the Scrubber removes
    (so the hook keeps its old values) or listed above with the reason it holds no name."""
    covered = {(cls.__name__, key) for cls, key, _ in _columns()}
    looks = {
        (mapper.class_.__name__, column.key)
        for mapper in Base.registry.mappers
        for column in mapper.columns
        if re.search(r"name|title|label", column.key)
    }
    assert looks - covered - set(_NOT_A_NAME) == set(), looks - covered - set(_NOT_A_NAME)
    assert not covered & set(_NOT_A_NAME)
    assert set(_NOT_A_NAME) <= looks
    for reason in _NOT_A_NAME.values():
        assert reason


def test_every_kind_the_hook_writes_has_a_replacement() -> None:
    assert {kind for _, _, kind in _columns()} <= set(former_names.REPLACEMENTS)


def test_the_nightly_purge_keeps_the_names_it_deletes(kitchen: TestClient) -> None:
    """Real paths: an ingredient and a recipe removed, then purged for good by the job (bulk
    deletes, with names that go with them): the hook keeps them, not only the undo data."""
    from tests.test_problem_report import _purge_all

    food = _ok(kitchen.post(f"{API}/foods", json={"name": "Aunty Priyamvada chutney"}))["food"]
    recipe = _ok(kitchen.post(f"{API}/recipes", json={"name": "Barnaby biryani"}))
    _ok(kitchen.delete(f"{API}/foods/{food['id']}"))
    _ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    _purge_all(kitchen)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        kept = {(r.kind, r.name) for r in db.scalars(select(models.FormerName))}
    assert ("ingredient", "Aunty Priyamvada chutney") in kept
    assert ("recipe", "Barnaby biryani") in kept


def test_every_bulk_statement_on_a_name_table_goes_through_the_session() -> None:
    """The sweep: each `delete(Model)` / `update(Model)` in the code on a model that holds a name
    (or whose cascade children do) is executed by a Session, so the hook sees it. None is run
    on a bare connection (that would bypass the hook)."""
    import ast
    from pathlib import Path

    root = Path(former_names.__file__).parent
    found: list[str] = []
    for path in root.rglob("*.py"):
        if "migrations" in path.parts or path.name == "former_names.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("delete", "update")
                and node.args
                and isinstance(node.args[0], ast.Name)
                and hasattr(models, node.args[0].id)
            ):
                table = getattr(models, node.args[0].id).__table__.name
                if former_names._reaches(table):
                    found.append(f"{path.name}:{node.args[0].id}")
    assert found, "the sweep found nothing: it is broken"
    for path in root.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        text_ = path.read_text()
        assert "connection().execute(delete" not in text_ and "conn.execute(delete" not in text_


# --- Round 5: the r4 Lows ------------------------------------------------------------------------


def test_l1_a_long_name_in_undo_data_is_still_a_name() -> None:
    """Review r4, L1: a name of more than 20 words was skipped; any that can be matched is a
    name (problem_report._LONGEST_PHRASE)."""
    from mealwright import problem_report

    name = " ".join(f"word{chr(97 + i)}" for i in range(25))
    found = list(problem_report.undo_names({"recipe_id": 1, "name": name}))
    assert [n for n, _ in found] == [name]
    too_long = " ".join(["word"] * (problem_report._LONGEST_PHRASE + 1))
    assert list(problem_report.undo_names({"name": too_long})) == []  # can't be matched


def test_l2_role_lot_amounts_and_one_word_messages_are_not_names() -> None:
    """Review r4, L2: "admin" and "member" (person roles), a lot's amounts and "Undone." are
    everyday words, not names."""
    from mealwright import problem_report

    data = {
        "person": {"role": ["member", "admin"]},
        "lot_amounts": ["kitchen", "stock"],
        "message": "Undone.",
    }
    assert list(problem_report.undo_names(data)) == []
    long_message = {"message": "Lentil soup is back, on the recipes that had it."}
    assert [n for n, _ in problem_report.undo_names(long_message)] == [long_message["message"]]
    for key in ("role", "lot_amounts"):
        assert problem_report.UNDO_NOT_NAMES[key]


def test_l2_a_role_change_keeps_the_word_admin_in_the_report(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    from mealwright.models import Change

    _ok(kitchen.patch(f"{API}/household", json={"name": "Brightwell"}))  # makes a change to copy
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        first = db.scalars(select(Change)).first()
        assert first is not None
        db.add(
            Change(
                household_id=first.household_id,
                kind="person_changed",
                summary="Changed a role",
                at=first.at,
                login_id=first.login_id,
                login_name=first.login_name,
                undo_data={"person": {"role": ["member", "admin"]}, "message": "Undone."},
            )
        )
        db.commit()
    write_log(
        log_folder(settings),
        [error("Only an admin can change the backup schedule", ago=timedelta(seconds=-2))],
    )
    for client in (kitchen, neighbour):
        assert "Only an admin can change the backup schedule" in report(client)["errors"][-1]


def test_l3_a_name_is_labelled_by_the_kind_of_change_that_kept_it() -> None:
    from mealwright import problem_report

    for kind, label in (
        ("recipe_deleted", "[recipe]"),
        ("recipe_saved", "[recipe]"),
        ("draft_kept", "[recipe]"),
        ("list_made", "[removed]"),
        ("list_renamed", "[removed]"),
    ):
        found = list(
            problem_report.undo_names({"recipe_id": 1, "name": "Barnaby biryani"}, kind=kind)
        )
        assert found == [("Barnaby biryani", label)], kind


def test_l3_the_current_household_name_is_a_whole_phrase_too(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r4, L3: a household now called "Our Kitchen" removes that phrase, and keeps
    "Kitchen timer failed" (it was removed word by word)."""
    _ok(kitchen.patch(f"{API}/household", json={"name": "Our Kitchen"}))
    write_log(
        log_folder(settings),
        [
            error("Kitchen timer failed", ago=timedelta(seconds=-2)),
            error("Couldn't save Our Kitchen", ago=timedelta(seconds=-2)),
        ],
    )
    for client in (kitchen, neighbour):
        text = "\n".join(report(client)["errors"])
        assert "Kitchen timer failed" in text, text
        assert "Couldn't save [household]" in text, text
