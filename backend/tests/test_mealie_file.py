"""Reading a Mealie backup file (cabledrawer 13 Nov: file only, never a network fetch).

Every zip here is made up in the test: made-up recipes, made-up people, no real data. The
hostile ones (a zip bomb, `../` names, huge or deep JSON, missing tables, wrong types) must be
refused or skipped, never unpacked to disk or read past a limit.
"""

import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from mealwright import mealie_file
from mealwright.mealie_file import (
    MealieFileProblem,
    MealiePhotos,
    minutes,
    read_file,
    read_now,
)

DAL = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"
SOUP = "2c5f39cb3fb211d2883f0016d3cca428"
FLOUR = "9a0e7c1a-0000-4000-8000-000000000001"
LENTILS = "9a0e7c1a-0000-4000-8000-000000000002"
GRAM = "7b1d6e2f-0000-4000-8000-000000000003"
TAG = "5d6c4b3a-0000-4000-8000-000000000004"


def tables(**changes: object) -> dict[str, object]:
    """A small Mealie database: two recipes, two foods, a unit, a tag, and some things that
    aren't brought in."""
    base: dict[str, object] = {
        "alembic_version": [{"version_num": "1fe4bd37ccc8"}],
        "recipes": [
            {
                "id": DAL,
                "slug": "red-lentil-dal",
                "name": "Red lentil dal",
                "description": "Sam's weeknight dal.",
                "total_time": "1 hour 15 minutes",
                "prep_time": "10 minutes",
                "perform_time": None,
                "recipe_yield": "4 servings",
                "recipe_servings": 4,
                "org_url": "https://kitchen.example/dal",
            },
            {
                "id": SOUP,
                "slug": "lornas-soup",
                "name": "Lorna's soup",
                "description": None,
                "total_time": None,
                "prep_time": "PT10M",
                "perform_time": "20 min",
                "recipe_yield": "6",
                "org_url": None,
            },
        ],
        "recipes_ingredients": [
            {
                "recipe_id": DAL,
                "position": 1,
                "quantity": 200.0,
                "unit_id": GRAM,
                "food_id": LENTILS,
                "note": "rinsed",
                "title": None,
                "original_text": None,
            },
            {
                "recipe_id": DAL,
                "position": 0,
                "quantity": 1.5,
                "unit_id": None,
                "food_id": None,
                "note": "1 tsp turmeric",
                "title": "For the dal",
                "original_text": "1 tsp turmeric",
            },
            {
                "recipe_id": SOUP,
                "position": 0,
                "quantity": 0,
                "unit_id": None,
                "food_id": None,
                "note": "",
                "original_text": "a pinch of salt",
            },
        ],
        "recipe_instructions": [
            {"recipe_id": DAL, "position": 1, "title": "", "text": "Simmer for 20 minutes."},
            {"recipe_id": DAL, "position": 0, "title": "Start", "text": "Rinse the lentils."},
        ],
        "ingredient_foods": [
            {"id": FLOUR, "name": "Plain flour"},
            {"id": LENTILS, "name": "Red lentils"},
        ],
        "ingredient_units": [
            {"id": GRAM, "name": "gram", "abbreviation": "g", "use_abbreviation": True}
        ],
        "recipe_nutrition": [
            {
                "recipe_id": DAL,
                "calories": "320 kcal",
                "protein_content": "18 g",
                "carbohydrate_content": "45",
                "fat_content": None,
                "fiber_content": "9 g",
            },
        ],
        "tags": [{"id": TAG, "name": "Weeknight"}],
        "recipes_to_tags": [{"recipe_id": DAL, "tag_id": TAG}],
        "group_meal_plans": [{}, {}, {}],
        "shopping_lists": [{}],
        "users": [{"username": "noor"}, {"username": "sam"}],
        "cookbooks": [],
    }
    base.update(changes)
    return base


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(out, "JPEG")
    return out.getvalue()


def make_zip(
    path: Path,
    database: object | bytes | None = None,
    extra: dict[str, bytes] | None = None,
    method: int = zipfile.ZIP_DEFLATED,
) -> Path:
    with zipfile.ZipFile(path, "w", method) as zipped:
        if database is not None:
            raw = database if isinstance(database, bytes) else json.dumps(database).encode()
            zipped.writestr("database.json", raw)
        for name, data in (extra or {}).items():
            zipped.writestr(name, data)
    return path


@pytest.fixture
def good(tmp_path: Path) -> Path:
    return make_zip(
        tmp_path / "mealie.zip",
        tables(),
        {
            f"data/recipes/{DAL}/images/original.webp": jpeg(),  # named webp, a JPEG inside
            f"data/recipes/{DAL}/images/min-original.webp": jpeg(),
        },
    )


def test_reads_recipes_foods_and_what_is_left_out(good: Path) -> None:
    book = read_now(good)
    assert [r.page.name for r in book.recipes] == ["Red lentil dal", "Lorna's soup"]
    dal, soup = book.recipes
    assert dal.key == DAL.replace("-", "")
    assert dal.source == "https://kitchen.example/dal"
    assert dal.page.description == "Sam's weeknight dal."
    assert dal.page.author is None
    assert dal.page.total_minutes == 75
    assert dal.page.serves == 4
    assert dal.page.tags == ("Weeknight",)
    assert dal.page.nutrition == {
        "kcal": Decimal(320), "protein": Decimal(18), "carbs": Decimal(45),
        "fat": None, "fibre": Decimal(9),
    }  # fmt: skip
    # Ordered by position; a title is a heading line; parts put together with the note.
    assert [(line.text, line.heading) for line in dal.page.ingredients] == [
        ("For the dal", True),
        ("1 tsp turmeric", False),
        ("200 g Red lentils, rinsed", False),
    ]
    assert [(s.text, s.heading) for s in dal.page.steps] == [
        ("Start", True),
        ("Rinse the lentils.", False),
        ("Simmer for 20 minutes.", False),
    ]
    assert dal.foods == (LENTILS.replace("-", ""),)
    assert dal.photo == f"data/recipes/{DAL}/images/original.webp"
    assert dal.photo_bytes > 0
    # The second recipe: prep + cook, a bare number is servings, the first-typed text.
    assert soup.page.total_minutes == 30
    assert soup.page.serves == 6
    assert [line.text for line in soup.page.ingredients] == ["a pinch of salt"]
    assert soup.photo is None and soup.photo_bytes == 0
    # Only the foods some recipe uses.
    assert [f.name for f in book.foods] == ["Red lentils"]
    assert book.left_out == {"meal_plans": 3, "shopping_lists": 1, "users": 2, "cookbooks": 0}


def test_read_file_reads_in_a_budgeted_child(good: Path) -> None:
    book = read_file(good)
    assert len(book.recipes) == 2
    assert book == read_now(good)


def test_photo_is_cleaned_like_an_upload(good: Path) -> None:
    book = read_now(good)
    with MealiePhotos(good) as photos:
        cleaned = photos.cleaned(book.recipes[0].photo)
        assert cleaned is not None
        assert cleaned.large[:3] == b"\xff\xd8\xff"  # a fresh JPEG, made from the pixels
        assert photos.cleaned(None) is None
        # Only photo names are ever read, never another member.
        assert photos.raw("database.json") is None
        assert photos.raw(f"data/recipes/{SOUP}/images/original.webp") is None


def test_a_member_that_is_not_a_photo_is_skipped(tmp_path: Path) -> None:
    member = f"data/recipes/{DAL}/images/original.webp"
    path = make_zip(tmp_path / "m.zip", tables(), {member: b"not a picture"})
    with MealiePhotos(path) as photos:
        assert photos.cleaned(member) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PT1H30M", 90),
        ("45", 45),
        ("1 hour 30 minutes", 90),
        ("1h 30m", 90),
        ("2 Hours", 120),
        ("1 day", 1440),
        ("20 min and 5 mins", 25),
        ("about an hour", None),
        ("30 minutes, then overnight", None),
        ("", None),
        ("9" * 200, None),
        (None, None),
        (12, 12),
    ],
)
def test_minutes(text: object, expected: int | None) -> None:
    assert minutes(text) == expected


# --- Hostile and broken files --------------------------------------------------------------------


def problem(path: Path) -> str:
    with pytest.raises(MealieFileProblem) as raised:
        read_now(path)
    return raised.value.reason


def test_not_a_zip(tmp_path: Path) -> None:
    path = tmp_path / "x.zip"
    path.write_bytes(b"PK\x03\x04 not really")
    assert problem(path) == "not_zip"


def test_a_zip_without_database_json(tmp_path: Path) -> None:
    assert problem(make_zip(tmp_path / "x.zip", None, {"notes.txt": b"hi"})) == "not_mealie"


def test_database_json_one_folder_down_is_not_taken(tmp_path: Path) -> None:
    raw = json.dumps(tables()).encode()
    assert problem(make_zip(tmp_path / "x.zip", None, {"x/database.json": raw})) == "not_mealie"


def test_two_database_json_members(tmp_path: Path) -> None:
    path = make_zip(tmp_path / "x.zip", tables())
    with pytest.warns(UserWarning), zipfile.ZipFile(path, "a") as zipped:
        zipped.writestr("database.json", b"{}")
    assert problem(path) == "not_mealie"


def test_missing_recipes_table(tmp_path: Path) -> None:
    database = tables()
    del database["recipes"]
    assert problem(make_zip(tmp_path / "x.zip", database)) == "not_mealie"


@pytest.mark.parametrize("database", [[], "recipes", 3, b"\xff\xfe", b"{not json"])
def test_wrong_shapes(tmp_path: Path, database: object) -> None:
    assert problem(make_zip(tmp_path / "x.zip", database)) == "not_mealie"


def test_other_tables_missing_are_fine(tmp_path: Path) -> None:
    book = read_now(make_zip(tmp_path / "x.zip", {"recipes": [{"id": DAL, "name": "Plain"}]}))
    assert [r.page.name for r in book.recipes] == ["Plain"]
    assert book.recipes[0].page.ingredients == ()
    assert book.left_out == {"meal_plans": 0, "shopping_lists": 0, "users": 0, "cookbooks": 0}


def test_wrong_types_are_skipped(tmp_path: Path) -> None:
    database = tables(
        recipes=[
            "not a row",
            {"id": True, "name": "Bad id"},
            {"id": "../../etc", "name": "Path id"},
            {"id": DAL, "name": ["a list"]},
            {"id": SOUP, "name": "Kept", "total_time": {"h": 1}, "recipe_servings": "lots",
             "description": 5, "org_url": 7},
            {"id": SOUP, "name": "Same id again"},
        ],
        recipes_ingredients=[
            {"recipe_id": SOUP, "position": "first", "quantity": "1e999", "food_id": LENTILS,
             "unit_id": [], "note": None},
            {"recipe_id": SOUP, "quantity": float("nan"), "food_id": LENTILS},
            {"recipe_id": [SOUP], "note": "never seen"},
        ],
        tags={"not": "a list"},
        recipes_to_tags=[{"recipe_id": SOUP, "tag_id": None}],
    )  # fmt: skip
    book = read_now(make_zip(tmp_path / "x.zip", database))
    # A name that isn't text is no name: the recipe still comes (as "Untitled recipe"), never
    # dropped without a word (round 1, review 6).
    assert [(r.key, r.page.name) for r in book.recipes] == [
        (DAL.replace("-", ""), ""),
        (SOUP, "Kept"),
    ]
    kept = book.recipes[1]
    assert kept.page.total_minutes is None and kept.page.serves is None
    assert kept.page.description is None and kept.source is None
    assert [line.text for line in kept.page.ingredients] == ["Red lentils", "Red lentils"]
    assert kept.page.tags == ()


def test_a_nameless_recipe_is_kept_and_an_ingredients_name_is_cut_to_100(
    tmp_path: Path,
) -> None:
    database = tables(
        recipes=[{"id": DAL, "name": "   "}],
        recipes_ingredients=[{"recipe_id": DAL, "position": 0, "food_id": FLOUR, "quantity": 2}],
        ingredient_foods=[{"id": FLOUR, "name": "Sam's " + "very " * 40 + "fine flour"}],
    )
    book = read_now(make_zip(tmp_path / "x.zip", database))
    assert [recipe.page.name for recipe in book.recipes] == [""]
    (food,) = book.foods
    assert len(food.name) <= 100 and food.name.endswith("…")
    # The line names the ingredient as cut, so it matches the one the import adds.
    assert book.recipes[0].page.ingredients[0].text == f"2 {food.name}"


def test_too_many_recipes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mealie_file, "MAX_RECIPES", 1)
    assert problem(make_zip(tmp_path / "x.zip", tables())) == "too_many"


def named_over_and_over(
    recipes: int, lines: int, name: str, unit: str | None = None
) -> dict[str, object]:
    """A small file that names one ingredient (and unit) on every line of every recipe."""
    keys = [f"{i:032x}" for i in range(recipes)]
    return tables(
        recipes=[{"id": key, "name": f"Lorna's pot {i}"} for i, key in enumerate(keys)],
        recipes_ingredients=[
            {
                "recipe_id": key,
                "position": j,
                "food_id": FLOUR,
                "quantity": 1,
                "unit_id": unit and GRAM,
            }
            for key in keys
            for j in range(lines)
        ],
        recipe_instructions=[],
        recipe_nutrition=[],
        recipes_to_tags=[],
        ingredient_foods=[{"id": FLOUR, "name": name}],
        ingredient_units=[{"id": GRAM, "name": unit}] if unit else [],
    )


def test_what_the_reader_hands_back_has_a_limit_on_its_text(tmp_path: Path) -> None:
    # Round 1, S-M5: 190,000 lines of a 100-character name (the most an ingredient's name
    # keeps) and a 30-character unit are 25 million characters for the server to keep, from a
    # file of a few hundred KB.
    assert mealie_file.MAX_BOOK_TEXT == 24_000_000
    database = named_over_and_over(1_900, 100, "Noor's " + "q" * 193, "Lorna's " + "u" * 40)
    path = make_zip(tmp_path / "x.zip", database)
    assert path.stat().st_size < 1_000_000
    assert problem(path) == "too_big"


def test_what_the_reader_hands_back_has_a_limit_on_its_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert mealie_file.MAX_BOOK_LINES == 250_000
    monkeypatch.setattr(mealie_file, "MAX_BOOK_LINES", 30)
    assert (
        len(read_now(make_zip(tmp_path / "x.zip", named_over_and_over(3, 10, "Salt"))).recipes) == 3
    )
    assert problem(make_zip(tmp_path / "y.zip", named_over_and_over(4, 10, "Salt"))) == "too_big"


def test_too_deep_json(tmp_path: Path) -> None:
    deep: object = 1
    for _ in range(mealie_file.MAX_JSON_DEPTH):
        deep = [deep]
    database = tables(recipes=[{"id": DAL, "name": "Deep", "extras": deep}])
    assert problem(make_zip(tmp_path / "x.zip", database)) == "not_mealie"


def test_very_deep_json_does_not_crash(tmp_path: Path) -> None:
    raw = b'{"recipes": ' + b"[" * 200_000 + b"]" * 200_000 + b"}"
    assert problem(make_zip(tmp_path / "x.zip", raw)) == "not_mealie"


def test_huge_json_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mealie_file, "MAX_DATABASE_BYTES", 1000)
    database = tables(recipes=[{"id": DAL, "name": "x" * 2000}])
    assert problem(make_zip(tmp_path / "x.zip", database)) == "too_big"


def test_zip_bomb_is_never_unpacked_past_the_limit(tmp_path: Path) -> None:
    """5 MB of spaces packs into a few KB. Whatever the zip says about its size, a read stops
    at its limit, so a bomb is cut off rather than unpacked."""
    path = make_zip(tmp_path / "bomb.zip", b"{" + b" " * 5_000_000 + b"}")
    assert path.stat().st_size < 50_000
    with zipfile.ZipFile(path) as zipped:
        member = zipped.getinfo("database.json")
        assert mealie_file.read_member(zipped, member, 1000) is None
        assert mealie_file.read_member(zipped, member, 6_000_000) is not None


def test_zip_bomb_by_its_own_size_is_refused(tmp_path: Path) -> None:
    path = make_zip(tmp_path / "bomb.zip", tables(), {"filler.bin": b"\0" * 2_000_000})
    original = mealie_file.MAX_TOTAL_BYTES
    try:
        mealie_file.MAX_TOTAL_BYTES = 1_000_000
        assert problem(path) == "too_big"
    finally:
        mealie_file.MAX_TOTAL_BYTES = original


def test_too_many_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mealie_file, "MAX_MEMBERS", 3)
    extra = {f"data/x{i}.txt": b"" for i in range(5)}
    assert problem(make_zip(tmp_path / "x.zip", tables(), extra)) == "too_big"


def test_encrypted_or_odd_members_are_not_read(tmp_path: Path) -> None:
    path = make_zip(tmp_path / "x.zip", tables(), method=zipfile.ZIP_LZMA)
    assert problem(path) == "not_mealie"


def test_dot_dot_names_are_never_used_as_paths(tmp_path: Path) -> None:
    """Names with "../" or a leading "/" are not photos, and nothing is written anywhere."""
    folder = tmp_path / "inside"
    folder.mkdir()
    sneaky = {
        f"../data/recipes/{DAL}/images/original.webp": jpeg(),
        f"data/recipes/{DAL}/../../../escaped.webp": jpeg(),
        f"/data/recipes/{DAL}/images/original.webp": jpeg(),
        f"data/recipes/../{DAL}/images/original.webp": jpeg(),
    }
    path = make_zip(folder / "x.zip", tables(), sneaky)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    book = read_file(path)
    assert all(recipe.photo is None for recipe in book.recipes)
    with MealiePhotos(path) as photos:
        for name in sneaky:
            assert photos.raw(name) is None
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_a_photo_over_the_limit_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mealie_file, "MAX_PHOTO_BYTES", 100)
    member = f"data/recipes/{DAL}/images/original.webp"
    path = make_zip(tmp_path / "x.zip", tables(), {member: jpeg()})
    assert read_now(path).recipes[0].photo is None
    with MealiePhotos(path) as photos:
        assert photos.raw(member) is None


def test_child_reports_problems(tmp_path: Path) -> None:
    with pytest.raises(MealieFileProblem) as raised:
        read_file(make_zip(tmp_path / "x.zip", None, {"a.txt": b""}))
    assert raised.value.reason == "not_mealie"
    assert raised.value.message == mealie_file.MESSAGES["not_mealie"]


def test_child_over_its_memory_is_stopped(tmp_path: Path) -> None:
    """8 million empty rows: a 24 MB file (under the size limit) that needs far more memory
    once read. The child stops at its memory limit."""
    raw = b'{"recipes": [], "group_meal_plans": [' + b"{}," * 7_999_999 + b"{}]}"
    path = make_zip(tmp_path / "x.zip", raw)
    with pytest.raises(MealieFileProblem) as raised:
        read_file(path, memory=256 * 1024 * 1024)
    assert raised.value.reason == "too_big"


def test_child_over_its_time_is_stopped(tmp_path: Path) -> None:
    raw = b'{"recipes": [], "group_meal_plans": [' + b"{}," * 7_999_999 + b"{}]}"
    path = make_zip(tmp_path / "x.zip", raw)
    with pytest.raises(MealieFileProblem) as raised:
        read_file(path, wall_seconds=0.2)
    assert raised.value.reason == "unreadable"


def test_file_over_the_upload_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mealie_file, "MAX_FILE_BYTES", 10)
    with pytest.raises(MealieFileProblem) as raised:
        read_file(make_zip(tmp_path / "x.zip", tables()))
    assert raised.value.reason == "too_big"
