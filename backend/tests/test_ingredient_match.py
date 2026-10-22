"""Matching a read ingredient line to the household's ingredients."""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mealwright import migrate
from mealwright.db import make_engine, make_sessionmaker
from mealwright.household import add_default_places
from mealwright.ingredient_match import (
    KnownIngredients,
    Match,
    kitchen_of,
    match_line,
)
from mealwright.ingredient_reader import read_line
from mealwright.models import Food, FoodName, FoodSize, Household, Place, utcnow

D = Decimal


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    with make_sessionmaker(engine)() as session:
        session.add_all([Household(id=1, name="Home"), Household(id=2, name="Next door")])
        session.flush()
        add_default_places(session, 1)
        add_default_places(session, 2)
        session.commit()
        yield session


def add_food(
    db: Session,
    name: str,
    *,
    household: int = 1,
    counted_as: str = "weight",
    staple: bool = False,
    others: tuple[str, ...] = (),
    sizes: tuple[tuple[str, str, int], ...] = (),
) -> Food:
    food = Food(household_id=household, name=name, counted_as=counted_as, staple=staple)
    db.add(food)
    db.flush()
    for other in others:
        db.add(FoodName(household_id=household, food_id=food.id, name=other))
    for position, (size, plural, milli) in enumerate(sizes):
        db.add(
            FoodSize(
                household_id=household,
                food_id=food.id,
                name=size,
                plural=plural,
                amount_milli=milli,
                position=position,
            )
        )
    db.commit()
    return food


def match(db: Session, text: str, household: int = 1) -> Match:
    kitchen = kitchen_of(db, household)
    return match_line(kitchen, read_line(text, size_words=kitchen.size_words))


@pytest.fixture
def pantry(db: Session) -> dict[str, Food]:
    return {
        "onions": add_food(db, "Onions", counted_as="count"),
        "dal": add_food(db, "Toor dal", others=("thuvaram paruppu", "arhar dal")),
        "salt": add_food(db, "Salt", staple=True),
        "coriander": add_food(
            db, "Coriander", counted_as="count", sizes=(("bunch", "bunches", 1000),)
        ),
        "tomatoes": add_food(db, "Tomatoes", counted_as="count"),
        "chopped": add_food(db, "Chopped tomatoes", sizes=(("tin", "tins", 400_000),)),
        "rice": add_food(db, "Basmati rice"),
        "chilli": add_food(db, "Green chilli", counted_as="count"),
        "curry": add_food(db, "Curry leaves", counted_as="count"),
        "milk": add_food(db, "Milk", counted_as="volume"),
        "hing": add_food(db, "Hing", others=("asafoetida",)),
    }


# --- Matched ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("2 onions, finely chopped", "onions"),
        ("1 onion", "onions"),
        ("3 ONIONS", "onions"),
        ("finely chopped onions", "onions"),
        ("2 large onions", "onions"),
        ("1 cup toor dal", "dal"),
        ("1 cup Toor Dal", "dal"),
        ("1 cup thuvaram paruppu", "dal"),  # another name
        ("1 cup Thuvaram   Paruppu", "dal"),
        ("1 cup arhar dal", "dal"),
        ("1 cup thuvaram paruppu (toor dal)", "dal"),
        ("1 cup tuvar dal (toor dal)", "dal"),  # the bracket names it
        ("¼ tsp asafoetida", "hing"),
        ("¼ tsp hing / asafoetida", "hing"),
        ("2 green chillies", "chilli"),  # chilli and chillies
        ("2 Green Chilli, slit", "chilli"),
        ("1 sprig curry leaf", "curry"),
        ("10 curry leaves", "curry"),
        ("2 cups milk", "milk"),
        ("1 x 400g tin chopped tomatoes", "chopped"),  # the tin keeps "chopped"
        ("2 cups chopped tomatoes", "chopped"),  # a food called exactly that wins
        ("4 tomatoes, chopped", "tomatoes"),
        ("2 Tomatoes", "tomatoes"),
        ("1 cup basmati rice, rinsed", "rice"),
    ],
)
def test_matched(db: Session, pantry: dict[str, Food], text: str, key: str) -> None:
    result = match(db, text)
    assert result.label == "matched", text
    assert result.food_id == pantry[key].id
    assert result.food_name == pantry[key].name
    assert result.matched_by


def test_accents_and_punctuation_are_ignored(db: Session) -> None:
    jalapeno = add_food(db, "Jalapeño")
    add_food(db, "Confectioners' sugar")
    assert match(db, "2 jalapeno").food_id == jalapeno.id
    assert match(db, "100 g Confectioners sugar").label == "matched"


def test_the_ingredient_name_wins_over_another_ingredients_other_name(db: Session) -> None:
    first = add_food(db, "Mint", others=("pudina",))
    second = add_food(db, "Pudina")
    assert match(db, "1 tsp pudina").food_id == second.id
    assert match(db, "1 tsp mint").food_id == first.id


def test_matched_by_names_the_words_that_matched(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "1 cup thuvaram paruppu")
    assert result.matched_by == "thuvaram paruppu"
    result = match(db, "1 cup tuvar dal (toor dal)")
    assert result.matched_by == "toor dal"


# --- Staple -----------------------------------------------------------------------------------


def test_staple_is_information_only(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "1 tsp salt")
    assert result.label == "staple"
    assert result.food_id == pantry["salt"].id
    assert not result.counts
    assert result.amount_base is None
    assert match(db, "salt to taste").label == "staple"
    assert match(db, "2 tbsp Salt").label == "staple"


# --- To confirm -------------------------------------------------------------------------------


def test_a_close_match_is_to_confirm_with_the_best_guess(
    db: Session, pantry: dict[str, Food]
) -> None:
    result = match(db, "2 red onions")
    assert result.label == "to_confirm"
    assert (result.food_id, result.food_name) == (pantry["onions"].id, "Onions")
    result = match(db, "finely chopped red onions")
    assert (result.label, result.food_name) == ("to_confirm", "Onions")
    result = match(db, "1 cup brown basmati rice")
    assert (result.label, result.food_name) == ("to_confirm", "Basmati rice")
    result = match(db, "1 cup dal toor")  # the same words in another order
    assert (result.label, result.food_name) == ("to_confirm", "Toor dal")


def test_a_food_with_more_words_than_the_line_is_to_confirm_too(
    db: Session, pantry: dict[str, Food]
) -> None:
    result = match(db, "1 cup rice")
    assert (result.label, result.food_name) == ("to_confirm", "Basmati rice")


def test_the_best_guess_is_the_one_sharing_most_words(db: Session) -> None:
    add_food(db, "Onions")
    red = add_food(db, "Red onions")
    add_food(db, "Spring onions")
    result = match(db, "2 small red onions, thinly sliced")
    assert result.label == "matched"  # "red onions" is a food's name: prep words don't matter
    result = match(db, "2 sweet red onions")
    assert (result.label, result.food_id) == ("to_confirm", red.id)


def test_a_tie_goes_to_the_oldest_ingredient(db: Session) -> None:
    older = add_food(db, "Red chilli powder")
    add_food(db, "Green chilli powder")
    assert match(db, "1 tsp chilli powder").food_id == older.id


def test_to_confirm_matches_other_names_too(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "1 cup split thuvaram paruppu")
    assert (result.label, result.food_name) == ("to_confirm", "Toor dal")


def test_to_confirm_never_names_a_staple_as_staple(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "1 tsp sea salt")
    assert result.label == "to_confirm"
    assert result.food_name == "Salt"


# --- Needs you --------------------------------------------------------------------------------


def test_no_match_needs_you(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "1 cup jaggery")
    assert result.label == "needs_you"
    assert result.food_id is None and result.food_name is None and result.matched_by is None
    assert match(db, "2 tsp garam masala").label == "needs_you"


def test_an_unreadable_line_needs_you(db: Session, pantry: dict[str, Food]) -> None:
    for text in ("", "2 cups", "   "):
        result = match(db, text)
        assert result.label == "needs_you"
        assert result.read.readable is False
        assert not result.counts
        assert result.amount_base is None
    assert match(db, "2 cups").new_ingredient.name == "2 cups"


def test_nothing_in_the_kitchen_needs_you(db: Session) -> None:
    result = match(db, "2 onions")
    assert result.label == "needs_you"


# --- Which lines count ------------------------------------------------------------------------


def test_a_size_word_counts_only_if_the_ingredient_has_that_size(
    db: Session, pantry: dict[str, Food]
) -> None:
    result = match(db, "1 bunch coriander")
    assert result.label == "matched"
    assert result.counts
    assert result.size_id is not None
    size = db.get(FoodSize, result.size_id)
    assert size is not None and size.name == "bunch"
    assert (result.amount_base, result.base_unit) == (D(1), "count")  # coriander is counted
    assert match(db, "2 bunches coriander").size_id == result.size_id
    assert match(db, "2 bunches coriander").amount_base == D(2)


def test_a_size_word_the_ingredient_does_not_have_does_not_count(
    db: Session, pantry: dict[str, Food]
) -> None:
    for text in ("a sprig of coriander", "1 handful coriander", "2 cloves onions", "1 tin onions"):
        result = match(db, text)
        assert result.label == "matched", text
        assert not result.counts, text
        assert result.size_id is None
        assert result.amount_base is None
    assert not match(db, "1 sprig curry leaves").counts
    assert not match(db, "a few curry leaves").counts


def test_a_size_in_grams_turns_into_grams(db: Session, pantry: dict[str, Food]) -> None:
    result = match(db, "2 tins chopped tomatoes")
    assert result.label == "matched"
    assert result.counts
    assert (result.amount_base, result.base_unit) == (D(800), "g")
    assert result.size_id is not None


def test_the_households_own_size_names_are_read_as_sizes(db: Session) -> None:
    add_food(db, "Curd", counted_as="volume", sizes=(("dabba", "dabbas", 500_000),))
    result = match(db, "2 dabbas curd")
    assert result.read.size_word == "dabbas"
    assert result.counts
    assert (result.amount_base, result.base_unit) == (D(1000), "ml")


def test_no_amount_and_pinches_never_count(db: Session, pantry: dict[str, Food]) -> None:
    for text in ("tomatoes to taste", "a pinch of chopped tomatoes", "tomatoes for garnish"):
        assert not match(db, text).counts, text


def test_amounts_in_base_units(db: Session, pantry: dict[str, Food]) -> None:
    cases = {
        "200 g basmati rice": (D(200), "g"),
        "1.5 kg basmati rice": (D(1500), "g"),
        "2 l milk": (D(2000), "ml"),
        "250 ml milk": (D(250), "ml"),
        "2 tsp milk": (D(10), "ml"),
        "2 tbsp milk": (D(30), "ml"),
        "3 onions": (D(3), "count"),
        "½ onion": (D("0.5"), "count"),
    }
    for text, expected in cases.items():
        result = match(db, text)
        assert result.counts, text
        assert (result.amount_base, result.base_unit) == expected, text


def test_the_household_cup(db: Session, pantry: dict[str, Food]) -> None:
    # Never an assumed 250: the household's own cup turns a cup into ml, as in the recipe editor.
    assert match(db, "1 cup milk").amount_base == D(250)  # the default cup
    household = db.get(Household, 1)
    assert household is not None
    household.cup_ml = 240
    db.commit()
    result = match(db, "1 cup milk")
    assert (result.amount_base, result.base_unit) == (D(240), "ml")
    assert match(db, "1½ cups milk").amount_base == D(360)
    # A recipe that gives the metric amount too keeps its own number.
    household.cup_ml = 250
    db.commit()
    assert match(db, "1 cup (240 ml) milk").amount_base == D(240)
    # The cup is read fresh each time: another household has its own.
    other = db.get(Household, 2)
    assert other is not None
    other.cup_ml = 240
    db.commit()
    add_food(db, "Milk", household=2, counted_as="volume")
    assert match(db, "1 cup milk", household=2).amount_base == D(240)
    assert match(db, "1 cup milk", household=1).amount_base == D(250)


def test_lines_that_are_not_matched_say_what_they_would_do(
    db: Session, pantry: dict[str, Food]
) -> None:
    result = match(db, "2 cups jaggery")
    assert result.counts
    assert (result.amount_base, result.base_unit) == (D(500), "ml")
    assert not match(db, "1 bunch jaggery").counts


# --- The first guess for a new ingredient ------------------------------------------------------


def cupboard_id(db: Session, household: int = 1) -> int:
    return db.scalars(
        select(Place.id).where(Place.household_id == household, Place.name == "Cupboard")
    ).one()


@pytest.mark.parametrize(
    ("text", "name", "counted_as"),
    [
        ("finely chopped red onions", "Red onions", "weight"),  # no amount
        ("2 finely chopped jaggery blocks", "Jaggery blocks", "count"),
        ("200 g jaggery", "Jaggery", "weight"),
        ("1 kg jaggery", "Jaggery", "weight"),
        ("250 ml coconut milk", "Coconut milk", "volume"),
        ("1 l coconut milk", "Coconut milk", "volume"),
        ("2 tsp garam masala", "Garam masala", "volume"),
        ("2 tbsp garam masala", "Garam masala", "volume"),
        ("1 cup garam masala", "Garam masala", "volume"),
        ("3 plantains", "Plantains", "count"),
        ("1 bunch methi", "Methi", "count"),
        ("a pinch of asafoetida powder", "Asafoetida powder", "weight"),
        ("jaggery, to taste", "Jaggery", "weight"),
        ("1 x 400g tin jackfruit", "Jackfruit", "weight"),
        ("2 tbsp நல்லெண்ணெய்", "நல்லெண்ணெய்", "volume"),
        ("100 g MDH sambar masala", "MDH sambar masala", "weight"),
    ],
)
def test_new_ingredient_first_guess(db: Session, text: str, name: str, counted_as: str) -> None:
    guess = match(db, text).new_ingredient
    assert guess.name == name
    assert guess.counted_as == counted_as
    assert guess.place_id == cupboard_id(db)
    assert guess.staple is False


def test_the_guess_is_on_every_line_that_is_not_matched(
    db: Session, pantry: dict[str, Food]
) -> None:
    assert match(db, "2 red onions").new_ingredient.name == "Red onions"  # to confirm
    assert match(db, "2 cups jaggery").new_ingredient.name == "Jaggery"  # needs you


def test_treat_as_staple_is_the_same_guess_with_staple_on(db: Session) -> None:
    from mealwright.ingredient_match import first_guess

    kitchen = kitchen_of(db, 1)
    read = read_line("2 tsp garam masala")
    plain = first_guess(kitchen, read)
    staple = first_guess(kitchen, read, staple=True)
    assert staple.staple is True
    assert (staple.name, staple.counted_as, staple.place_id) == (
        plain.name,
        plain.counted_as,
        plain.place_id,
    )


def test_no_cupboard_means_no_place(db: Session) -> None:
    db.query(Place).filter(Place.household_id == 1, Place.name == "Cupboard").delete()
    db.commit()
    assert match(db, "200 g jaggery").new_ingredient.place_id is None
    # The other household's Cupboard is never borrowed.
    assert cupboard_id(db, 2)
    # A renamed place isn't called Cupboard: "Spice rack" is not one.
    assert match(db, "200 g jaggery").new_ingredient.place_id is None


def test_the_cupboard_may_be_written_any_way(db: Session) -> None:
    db.query(Place).filter(Place.household_id == 1, Place.name == "Cupboard").update(
        {"name": "cupboard "}
    )
    db.commit()
    assert match(db, "200 g jaggery").new_ingredient.place_id == cupboard_id_any(db)


def cupboard_id_any(db: Session) -> int:
    return (
        db.scalars(
            select(Place.id).where(Place.household_id == 1, Place.kind == "cupboard")
        ).first()
        or 0
    )


def test_a_long_name_is_cut_to_fit(db: Session) -> None:
    guess = match(db, "2 " + "word " * 60).new_ingredient
    assert len(guess.name) <= 100


def test_matching_writes_nothing(db: Session, pantry: dict[str, Food]) -> None:
    foods = db.scalar(select(func.count()).select_from(Food))
    names = db.scalar(select(func.count()).select_from(FoodName))
    kitchen = kitchen_of(db, 1)
    for text in ("2 red onions", "1 cup jaggery", "salt to taste", "1 bunch coriander"):
        match_line(kitchen, read_line(text))
    assert not db.new and not db.dirty and not db.deleted
    assert db.scalar(select(func.count()).select_from(Food)) == foods
    assert db.scalar(select(func.count()).select_from(FoodName)) == names


# --- Reading the household's ingredients --------------------------------------------------------


def test_kitchen_of_reads_ingredients_names_sizes_and_places(
    db: Session, pantry: dict[str, Food]
) -> None:
    kitchen = kitchen_of(db, 1)
    assert isinstance(kitchen, KnownIngredients)
    assert kitchen.household_id == 1
    assert kitchen.cup_ml == 250
    by_name = {food.name: food for food in kitchen.foods}
    assert set(by_name["Toor dal"].other_names) == {"thuvaram paruppu", "arhar dal"}
    assert [size.name for size in by_name["Coriander"].sizes] == ["bunch"]
    assert by_name["Salt"].staple is True
    assert by_name["Milk"].counted_as == "volume"
    assert [place.name for place in kitchen.places] == [
        "Fridge",
        "Freezer",
        "Cupboard",
        "Spice rack",
    ]
    assert "bunch" in kitchen.size_words and "bunches" in kitchen.size_words


def test_removed_and_merged_away_ingredients_are_not_matched(db: Session) -> None:
    gone = add_food(db, "Radish")
    merged = add_food(db, "Scallions", others=("spring onion",))
    keeper = add_food(db, "Green onions")
    gone.removed_at = utcnow()
    merged.merged_into_id = keeper.id
    db.commit()
    assert match(db, "2 radishes").label == "needs_you"
    assert match(db, "2 scallions").label == "needs_you"
    assert match(db, "2 spring onions").label == "needs_you"
    assert [food.name for food in kitchen_of(db, 1).foods] == ["Green onions"]


def test_two_households_never_see_each_other(db: Session) -> None:
    mine = add_food(
        db,
        "Toor dal",
        household=1,
        others=("thuvaram paruppu",),
        sizes=(("packet", "packets", 500_000),),
    )
    theirs = add_food(
        db,
        "Moong dal",
        household=2,
        others=("pasi paruppu",),
        sizes=(("sack", "sacks", 5_000_000),),
    )
    kitchen_one, kitchen_two = kitchen_of(db, 1), kitchen_of(db, 2)
    assert [food.id for food in kitchen_one.foods] == [mine.id]
    assert [food.id for food in kitchen_two.foods] == [theirs.id]
    assert kitchen_one.size_words == ("packet", "packets")
    assert kitchen_two.size_words == ("sack", "sacks")
    assert match(db, "1 cup thuvaram paruppu", household=2).label == "needs_you"
    assert match(db, "1 cup pasi paruppu", household=1).label == "needs_you"
    assert match(db, "1 cup pasi paruppu", household=2).food_id == theirs.id
    assert match(db, "1 cup thuvaram paruppu", household=1).food_id == mine.id
    assert match(db, "1 sack moong dal", household=1).label == "needs_you"
    # Places too.
    assert {place.id for place in kitchen_one.places}.isdisjoint(
        {place.id for place in kitchen_two.places}
    )
    assert kitchen_one.cupboard_id == cupboard_id(db, 1)
    assert kitchen_two.cupboard_id == cupboard_id(db, 2)


def test_other_names_of_other_households_do_not_leak_in_by_food_id(db: Session) -> None:
    # A name row filed under household 2 but pointing at household 1's food is never read.
    mine = add_food(db, "Toor dal", household=1)
    db.add(FoodName(household_id=2, food_id=mine.id, name="stray name"))
    db.commit()
    assert kitchen_of(db, 1).foods[0].other_names == ()


def test_an_unknown_household_has_nothing(db: Session) -> None:
    kitchen = kitchen_of(db, 99)
    assert kitchen.foods == () and kitchen.places == ()
    assert kitchen.cup_ml == 250
    assert match_line(kitchen, read_line("2 onions")).label == "needs_you"


# --- Properties --------------------------------------------------------------------------------


# Nothing here writes, so the database can be shared by all the generated lines.
@settings(
    max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(st.text(max_size=120))
def test_matching_never_raises(db: Session, pantry: dict[str, Food], text: str) -> None:
    kitchen = kitchen_of(db, 1)
    result = match_line(kitchen, read_line(text))
    assert result.label in ("matched", "to_confirm", "needs_you", "staple")
    assert (result.food_id is None) == (result.label == "needs_you")
    if result.label == "staple":
        assert not result.counts
    if result.amount_base is not None:
        assert result.counts
        assert result.amount_base >= 0
    assert result.new_ingredient.name is not None
