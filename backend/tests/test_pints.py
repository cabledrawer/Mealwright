"""Pints (0.6 PR 7; spec section 6, "Reading choices, kept"): the household's own pint
(Settings), reading "pint" with it, and a US site, which is read with US pints while the
review offers the switch. The web is faked: no test goes online."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import test_recipe_import as base
from fastapi.testclient import TestClient
from sync_kit import ok, person
from test_recipe_import import Web, review, to_save

from mealwright import page_reader, pints
from mealwright.ingredient_reader import read_line
from mealwright.models import Household

API = "/api/v1"
# The same pretend web and the same link switch as the import tests use.
web = base.web
links_on = base.links_on
US_LINK = "https://www.allrecipes.com/recipe/1/rice-pudding/"
UNLISTED = "https://puddings.example/rice/"


PAGES = Path(__file__).parent / "import_pages"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def milk(shown: dict[str, Any]) -> dict[str, Any]:
    return next(line for line in shown["lines"] if "milk" in line["words"])


def set_pints(client: TestClient, value: str) -> Any:
    return ok(client.patch(f"{API}/household", json={"pints": value}))


# --- The reader ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "pint_ml", "amount"),
    [
        ("2 pints milk", 568, Decimal(1136)),
        ("2 pints milk", 473, Decimal(946)),
        ("1 pint milk", 568, Decimal(568)),
        ("1 pt milk", 473, Decimal(473)),
        ("½ pint cream", 568, Decimal(284)),
        ("1-2 pints stock", 473, Decimal(946)),
    ],
)
def test_a_pint_is_read_with_the_size_it_is_given(text: str, pint_ml: int, amount: Decimal) -> None:
    line = read_line(text, pint_ml=pint_ml)
    assert (line.amount, line.unit, line.counts, line.chosen) == (amount, "ml", True, True)
    assert line.pints is not None
    assert line.text == text


def test_without_a_pint_size_a_pint_stays_in_the_note_as_in_0_5() -> None:
    line = read_line("2 pints milk")
    assert (line.amount, line.unit, line.note, line.pints) == (None, None, "2 pints", None)


def test_a_pint_next_to_a_metric_amount_leaves_the_metric_one_the_amount() -> None:
    line = read_line("1 pint (568 ml) milk", pint_ml=473)
    assert (line.amount, line.unit, line.pints) == (Decimal(568), "ml", None)


@pytest.mark.parametrize(
    ("text", "uk_ml", "us_ml"),
    [("2 quarts stock", 2272, 1892), ("1 gallon water", 4546, 3785), ("1 qt milk", 1136, 946)],
)
def test_quarts_and_gallons_are_pints_so_the_household_pint_decides(
    text: str, uk_ml: int, us_ml: int
) -> None:
    """Follow-up 6 (0.7.0): a quart is two pints and a gallon eight; they report their pints,
    so the US switch works on them too."""
    uk, us = read_line(text, pint_ml=568), read_line(text, pint_ml=473)
    assert (uk.amount, uk.unit) == (uk_ml, "ml") and (us.amount, us.unit) == (us_ml, "ml")
    assert uk.pints is not None and uk.pints == us.pints
    assert read_line(text).amount is None  # with no pint size given, as in 0.5


def test_fluid_ounces_follow_the_household_pint_and_have_the_switch() -> None:
    assert read_line("20 fl oz milk", pint_ml=568).amount == 568
    assert read_line("16 fl oz milk", pint_ml=473).amount == 473
    assert read_line("10 fl oz milk", pint_ml=568).amount == 284
    assert read_line("10 fl oz milk", pint_ml=473).amount == 296
    line = read_line("1 fl oz brandy", pint_ml=568)
    assert (line.pints, line.pint_unit) == (1, "fl oz")


# --- Telling a US site -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "language", "american"),
    [
        ("https://www.allrecipes.com/recipe/1/x/", None, True),
        ("https://allrecipes.com/recipe/1/x/", "en-gb", True),
        ("https://cooking.seriouseats.com/x", None, True),
        ("https://notallrecipes.com/x", None, False),
        ("https://allrecipes.com.evil.example/x", None, False),
        ("https://www.bbcgoodfood.com/recipes/x", "en-gb", False),
        ("https://puddings.example/x", "en-US", True),
        ("https://puddings.example/x", "en-us", True),
        ("https://puddings.example/x", "en", False),
        ("https://puddings.example/x", None, False),
        (None, "en-us", True),
        (None, None, False),
        ("not a link", None, False),
    ],
)
def test_how_a_us_site_is_told(url: str | None, language: str | None, american: bool) -> None:
    assert pints.looks_american(url, language) is american


def test_the_page_reader_gives_the_pages_language() -> None:
    found = page_reader.read_page(page("us_pudding.html"), UNLISTED)
    assert found is not None and found.language == "en-us"
    found = page_reader.read_page(page("uk_pudding.html"), UNLISTED)
    assert found is not None and found.language == "en-gb"


def test_a_page_with_no_language_gives_none() -> None:
    html = page("us_pudding.html").replace(' lang="en-US"', "")
    found = page_reader.read_page(html, UNLISTED)
    assert found is not None and found.language is None


# --- The setting -----------------------------------------------------------------------------


def test_the_household_starts_on_uk_pints_and_an_admin_can_change_it(kitchen: TestClient) -> None:
    assert ok(kitchen.get(f"{API}/household"))["pints"] == "uk"
    assert set_pints(kitchen, "us")["pints"] == "us"
    assert ok(kitchen.get(f"{API}/household"))["pints"] == "us"
    assert set_pints(kitchen, "uk")["pints"] == "uk"


def test_a_member_cannot_change_it(kitchen: TestClient) -> None:
    alex = person(kitchen)
    response = alex.patch(f"{API}/household", json={"pints": "us"})
    assert response.status_code == 403
    assert response.json()["code"] == "admins_only"
    assert ok(kitchen.get(f"{API}/household"))["pints"] == "uk"
    assert ok(alex.get(f"{API}/household"))["pints"] == "uk"  # members see it


@pytest.mark.parametrize("body", [{"pints": "imperial"}, {"pints": 568}, {"pints": ""}])
def test_only_uk_or_us_is_taken(kitchen: TestClient, body: dict[str, Any]) -> None:
    assert kitchen.patch(f"{API}/household", json=body).status_code == 422
    assert ok(kitchen.get(f"{API}/household"))["pints"] == "uk"


def test_an_empty_change_changes_nothing(kitchen: TestClient) -> None:
    set_pints(kitchen, "us")
    assert ok(kitchen.patch(f"{API}/household", json={}))["pints"] == "us"


def test_one_household_changing_it_never_changes_anothers(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    set_pints(kitchen, "us")
    assert ok(neighbour.get(f"{API}/household"))["pints"] == "uk"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert [h.pints for h in db.query(Household).order_by(Household.id)] == ["us", "uk"]


def test_signed_out_cannot_change_it(client: TestClient) -> None:
    assert client.patch(f"{API}/household", json={"pints": "us"}).status_code == 401


def test_unknown_values_in_the_database_are_read_as_uk() -> None:
    assert pints.household_pints("us") == "us"
    assert pints.household_pints("uk") == "uk"
    assert pints.household_pints("fr") == "uk"
    assert pints.household_pints(None) == "uk"


# --- On the review ---------------------------------------------------------------------------


def test_pasted_text_is_read_with_the_households_pint(kitchen: TestClient) -> None:
    text = "Rice pudding\n\nIngredients\n2 pints milk\n100 g rice\n\nMethod\nSimmer."
    shown = review(kitchen, text)
    assert shown["pints"] == {"household": "uk", "us_site": False, "reading": "uk"}
    assert milk(shown)["amount"] == 1136
    assert milk(shown)["unit"] == "ml"
    assert milk(shown)["pint_ml"] == {"uk_ml": 1136.0, "us_ml": 946.0}
    set_pints(kitchen, "us")
    shown = review(kitchen, text)
    assert shown["pints"] == {"household": "us", "us_site": False, "reading": "us"}
    assert milk(shown)["amount"] == 946
    assert milk(shown)["pint_ml"] == {"uk_ml": 1136.0, "us_ml": 946.0}


@pytest.mark.parametrize("household", ["uk", "us"])
def test_too_many_pints_for_the_switch_still_gives_a_review(
    kitchen: TestClient, household: str
) -> None:
    """2000 pints is 946,000 ml read as US but 1,136,000 ml as UK, over the most an amount can
    be: the review still shows, without the switch (0.6.0 security pass L1)."""
    set_pints(kitchen, household)
    text = "Big pudding\n\nIngredients\n2000 pints milk\n100 g rice\n\nMethod\nSimmer."
    shown = review(kitchen, text)
    assert milk(shown)["pint_ml"] is None
    assert len(shown["lines"]) == 2


def test_too_many_pints_on_a_us_site_still_gives_a_review(links_on: TestClient, web: Web) -> None:
    big = page("us_pudding.html").replace("2 pints whole milk", "2000 pints whole milk")
    web.pages[UNLISTED] = big
    shown = review(links_on, UNLISTED)
    assert shown["pints"]["us_site"] is True
    assert milk(shown)["pint_ml"] is None


def test_a_line_without_pints_has_no_pint_reading(kitchen: TestClient) -> None:
    shown = review(kitchen, "Rice\n\nIngredients\n200 g rice\n\nMethod\nCook.")
    assert all(line["pint_ml"] is None for line in shown["lines"])


def test_a_listed_us_site_is_read_with_us_pints_while_the_household_is_uk(
    links_on: TestClient,
    web: Web,
) -> None:
    web.pages[US_LINK] = page("uk_pudding.html")  # the address alone is enough
    shown = review(links_on, US_LINK)
    assert shown["pints"] == {"household": "uk", "us_site": True, "reading": "us"}
    assert milk(shown)["amount"] == 946
    assert milk(shown)["pint_ml"] == {"uk_ml": 1136.0, "us_ml": 946.0}


def test_a_page_that_says_en_us_is_a_us_site_whatever_its_address(
    links_on: TestClient,
    web: Web,
) -> None:
    web.pages[UNLISTED] = page("us_pudding.html")
    shown = review(links_on, UNLISTED)
    assert shown["pints"] == {"household": "uk", "us_site": True, "reading": "us"}
    assert milk(shown)["amount"] == 946


def test_a_uk_page_is_read_with_the_households_pint(
    links_on: TestClient,
    web: Web,
) -> None:
    web.pages[UNLISTED] = page("uk_pudding.html")
    shown = review(links_on, UNLISTED)
    assert shown["pints"] == {"household": "uk", "us_site": False, "reading": "uk"}
    assert milk(shown)["amount"] == 1136


def test_a_us_household_reads_a_us_site_with_us_pints_and_is_not_offered_the_switch(
    links_on: TestClient,
    web: Web,
) -> None:
    set_pints(links_on, "us")
    web.pages[UNLISTED] = page("us_pudding.html")
    shown = review(links_on, UNLISTED)
    assert shown["pints"] == {"household": "us", "us_site": True, "reading": "us"}
    assert milk(shown)["amount"] == 946


def test_another_households_pint_is_never_used(
    links_on: TestClient,
    neighbour: TestClient,
    web: Web,
) -> None:
    set_pints(neighbour, "us")
    web.pages[UNLISTED] = page("uk_pudding.html")
    shown = review(links_on, UNLISTED)
    assert shown["pints"]["household"] == "uk"
    assert milk(shown)["amount"] == 1136
    text = "Pudding\n\nIngredients\n2 pints milk\n\nMethod\nSimmer."
    assert milk(review(links_on, text))["amount"] == 1136
    set_pints(links_on, "us")
    assert milk(review(neighbour, text))["amount"] == 946  # theirs is US as well


def test_save_keeps_what_the_review_sent(links_on: TestClient, web: Web) -> None:
    web.pages[US_LINK] = page("uk_pudding.html")
    shown = review(links_on, US_LINK)
    body = to_save(shown)
    saved = ok(links_on.post(f"{API}/recipes/import/save", json=body), 201)
    recipe = ok(links_on.get(f"{API}/recipes/{saved['recipe']['id']}"))
    line = next(item for item in recipe["lines"] if "milk" in item["words"])
    assert (line["amount"], line["unit"]) == (946, "ml")


def test_an_old_draft_without_pints_still_loads(kitchen: TestClient) -> None:
    """A draft kept before 0.6 has no `pints` on its review or its choices: both fall back."""
    from mealwright.api.v1.draft_schemas import DraftChoices
    from mealwright.api.v1.import_schemas import ImportReview

    assert DraftChoices().pints is None
    shown = review(kitchen, "Pudding\n\nIngredients\n2 pints milk\n\nMethod\nSimmer.")
    shown.pop("pints")
    for line in shown["lines"]:
        line.pop("pint_ml")
    old = ImportReview.model_validate(shown)
    assert old.pints.model_dump() == {"household": "uk", "us_site": False, "reading": "uk"}
    assert old.lines[0].pint_ml is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 1e308])
def test_a_draft_cannot_hold_an_impossible_pint(bad: float) -> None:
    """A draft comes back from the phone: a pint reading in it is checked like any amount."""
    from pydantic import ValidationError

    from mealwright.api.v1.import_schemas import PintReading

    with pytest.raises(ValidationError):
        PintReading.model_validate({"uk_ml": bad, "us_ml": 946.0})
    with pytest.raises(ValidationError):
        PintReading.model_validate({"uk_ml": 1136.0, "us_ml": bad})
    assert PintReading.model_validate({"uk_ml": 1136.0, "us_ml": 946.0}).uk_ml == 1136.0
