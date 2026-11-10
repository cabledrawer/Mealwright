# ruff: noqa: F811, RUF001  (the fixtures come from test_recipe_import.py and are used by name)
"""Importer consistency at the review (0.7.0): headings, page junk, optional serving lines,
two lines from one, "Kept in" defaults, one link at a time, the pints banner, name capitals on
save, and the nutrition flag. The reader's own rules are in test_import_consistency.py."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok
from test_recipe_import import (  # noqa: F401
    API,
    Web,
    links_on,
    review,
    save,
    to_save,
    web,
)

LAMB = """Lamb curry
Ingredients
For the Lamb
500 g lamb
Cook Mode
½x1×2×
a swish of olive oil + a sprinkle of salt
1 cup milk
a dozen eggs
2 cloves garlic, minced
garlic, 2 cloves, minced
For serving
1 cup basmati rice
Method
FULL RECIPE
1. Brown the lamb.
2. Add the rest.
"""


def lines_of(shown: dict[str, Any]) -> list[dict[str, Any]]:
    return list(shown["lines"])


def test_headings_junk_and_two_lines(kitchen: TestClient, web: Web) -> None:
    shown = review(kitchen, LAMB)
    lines = lines_of(shown)
    kinds = [(line["kind"], line["words"]) for line in lines]
    assert ("heading", "For the Lamb") in kinds and ("heading", "For serving") in kinds
    assert not any("Cook Mode" in line["written"] or "½x1" in line["written"] for line in lines)
    names = [line["words"] for line in lines if line["kind"] == "ingredient"]
    assert names[:4] == ["lamb", "olive oil", "salt", "milk"]  # "+" gave two lines
    assert shown["steps"][0] == {"kind": "heading", "text": "FULL RECIPE"}


def test_serving_lines_are_optional(kitchen: TestClient, web: Web) -> None:
    lines = lines_of(review(kitchen, LAMB))
    rice = next(line for line in lines if line["words"] == "basmati rice")
    assert (rice["note"] or "").startswith("optional")
    lamb = next(line for line in lines if line["words"] == "lamb")
    assert "optional" not in (lamb["note"] or "")


def test_a_dozen_counts_as_the_number_itself(kitchen: TestClient, web: Web) -> None:
    lines = lines_of(review(kitchen, LAMB))
    eggs = next(line for line in lines if line["words"] == "eggs")
    assert (eggs["amount"], eggs["size"]) == (12, None)


def test_f89_cloves_are_cloves_never_garlic(kitchen: TestClient, web: Web) -> None:
    """F89 (cabledrawer 31 Oct): "2 cloves garlic" reads as 2 cloves, shown as "2 cloves" in the
    note like "1 bunch coriander", never counted and never taken as 2 whole garlic. The learned
    size comes with K3."""
    lines = lines_of(review(kitchen, LAMB))
    garlic = [line for line in lines if line["words"] == "garlic"]
    assert len(garlic) == 2
    # Written before or after the name: the same reading.
    for line in garlic:
        assert (line["amount"], line["unit"], line["size"]) == (None, None, None)
        assert line["note"] == "2 cloves, minced"
        assert line["counts"] is False
    forms = (
        "Garlic\nIngredients\n2 cloves garlic\n2 garlic cloves\ngarlic, 2 cloves\n8 whole cloves\n"
    )
    forms += "1 bunch coriander\nMethod\n1. Cook.\n"
    read = {line["written"]: line for line in lines_of(review(kitchen, forms))}
    for written in ("2 cloves garlic", "2 garlic cloves", "garlic, 2 cloves"):
        assert (read[written]["words"], read[written]["amount"]) == ("garlic", None), written
        assert read[written]["note"] == "2 cloves", written
        assert read[written]["counts"] is False, written
    # The same as a size the ingredient lacks anywhere else, and the spice is untouched (F87).
    assert (read["1 bunch coriander"]["amount"], read["1 bunch coriander"]["note"]) == (
        None,
        "1 bunch",
    )
    assert (read["8 whole cloves"]["words"], read["8 whole cloves"]["amount"]) == ("cloves", 8)
    assert read["8 whole cloves"]["note"] == "whole"  # F103


def test_f89_garlic_with_a_clove_size_counts_that_size(kitchen: TestClient, web: Web) -> None:
    """When the ingredient does have a "clove" size, the line is 2 of that size, as before."""
    made = kitchen.post(f"{API}/foods", json={"name": "Garlic", "counted_as": "weight"})
    assert made.status_code == 201, made.text
    food_id = made.json()["food"]["id"]
    sized = kitchen.post(f"{API}/foods/{food_id}/sizes", json={"name": "clove", "amount": 4})
    assert sized.status_code == 201, sized.text
    text = "Garlic\nIngredients\n2 cloves garlic\n2 garlic cloves\nMethod\n1. Cook.\n"
    for line in lines_of(review(kitchen, text)):
        if line["kind"] != "ingredient":
            continue
        assert line["label"] == "matched", line["written"]
        assert (line["amount"], line["size"]["name"]) == (2, "clove"), line["written"]
        assert line["counts"] is True, line["written"]


def test_f88_a_weight_with_its_container_keeps_its_amount(kitchen: TestClient, web: Web) -> None:
    """F88 (cabledrawer 31 Oct): "three 14-ounce cans" and "half a 340g jar" get an amount, like
    "one 14-ounce can". Before, the review moved it to the note ("as written") and left none."""
    text = "\n".join(
        [
            "Pantry",
            "Ingredients",
            "one 14-ounce can coconut milk",
            "three 14-ounce cans coconut milk",
            "three 14 oz cans coconut milk",
            "two (14-ounce) cans coconut milk",
            "half a 340g jar jam",
            "1/2 a 400g tin tomatoes",
            "two 400g tins tomatoes",
            "four 400ml cartons passata",
            "half a jar plum jam",
            "Method",
            "1. Cook.",
        ]
    )
    lines = {line["written"]: line for line in lines_of(review(kitchen, text))}
    want = {
        "one 14-ounce can coconut milk": (397, "g"),
        "three 14-ounce cans coconut milk": (1191, "g"),
        "three 14 oz cans coconut milk": (1191, "g"),
        "two (14-ounce) cans coconut milk": (794, "g"),
        "half a 340g jar jam": (170, "g"),
        "1/2 a 400g tin tomatoes": (200, "g"),
        "two 400g tins tomatoes": (800, "g"),
        "four 400ml cartons passata": (1600, "ml"),
    }
    for written, (amount, unit) in want.items():
        assert (lines[written]["amount"], lines[written]["unit"]) == (amount, unit), written
        assert lines[written]["note"].startswith("as written:"), written
    # No weight written: the container can't be turned into an amount, so it stays in the note.
    jar = lines["half a jar plum jam"]
    assert (jar["amount"], jar["note"]) == (None, "\u00bd jar")


def test_new_ingredient_milk_is_kept_in_the_fridge_and_flour_in_the_cupboard(
    kitchen: TestClient, web: Web
) -> None:
    lines = lines_of(review(kitchen, LAMB))
    milk = next(line for line in lines if line["words"] == "milk")
    assert milk["new_ingredient"]["place"]["name"] == "Fridge"
    lamb = next(line for line in lines if line["words"] == "lamb")
    assert lamb["new_ingredient"]["place"]["name"] == "Fridge"
    rice = next(line for line in lines if line["words"] == "basmati rice")
    assert rice["new_ingredient"]["place"]["name"] == "Cupboard"


def test_a_box_sent_to_the_api_with_several_links_reads_the_first(
    links_on: TestClient, web: Web
) -> None:
    """The screen sends the links one by one (see the next test); a box with several links sent
    straight to the API still reads only the first and says how many are left."""
    from test_recipe_import import LINK

    second = "https://bananaleaf.example/other/"
    shown = review(links_on, f"{LINK}\n{second}\n")
    assert web.asked == [LINK]  # only the first was visited
    assert shown["more_links"] == 1
    assert shown["source"]["kind"] == "link" and shown["lines"]
    one = review(links_on, LINK, again=True)
    assert one["more_links"] == 0


def test_f110_several_links_one_after_another_each_into_a_draft_and_a_failure_in_the_middle(
    links_on: TestClient, web: Web
) -> None:
    """F110: the screen sends each pasted link as its own request, one after another. A link the
    site refuses in the middle gives its own refusal and no draft; the links either side of it are
    read and kept as two drafts, through the same switch and the same fetch as one link."""
    from test_recipe_import import LINK, page_text

    from mealwright.page_fetch import FetchRefused, Problem

    middle = "https://refuses.example/dal/"
    last = "https://bananaleaf.example/other/"
    web.pages[middle] = FetchRefused(Problem.SITE_REFUSED)
    web.pages[last] = page_text()
    kept: list[int] = []
    for link in (LINK, middle, last):
        answer = links_on.post(f"{API}/recipes/import", json={"text": link})
        if link == middle:
            assert answer.status_code == 422 and answer.json()["code"] == "site_refused"
            continue
        shown = ok(answer)
        assert shown["more_links"] == 0 and shown["lines"]
        draft = links_on.post(
            f"{API}/recipes/drafts", json={"text": link, "review": shown, "choices": {}}
        )
        kept.append(ok(draft, 201)["id"])
    assert web.asked == [LINK, middle, last]  # in order, each visited once
    assert len(set(kept)) == 2
    assert ok(links_on.get(f"{API}/recipes/drafts"))["count"] == 2


def test_f171_pasted_serves_and_takes_fill_serves_and_minutes(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(
        kitchen, "Dal\nServes 4\nTakes 30 minutes\nIngredients\n1 cup toor dal\n2 onions"
    )
    assert (shown["serves"], shown["time_minutes"]) == (4, 30)
    assert [line["written"] for line in shown["lines"]] == ["1 cup toor dal", "2 onions"]
    plain = review(kitchen, "Dal\nIngredients\n1 cup toor dal\n2 onions")
    assert (plain["serves"], plain["time_minutes"]) == (None, None)


def test_f15_f85_the_banner_is_only_for_a_recipe_with_pints(links_on: TestClient, web: Web) -> None:
    """F15 and F85: an Indian recipe in cups, with no pints, on a site that looks American
    shows no banner; the same site with pints does."""

    def page(ingredient: str) -> str:
        return (
            '<html lang="en-US"><script type="application/ld+json">'
            f'{{"@type":"Recipe","name":"X","recipeIngredient":["{ingredient}","1 onion"],'
            '"recipeInstructions":["Cook."]}</script></html>'
        )

    url = "https://www.allrecipes.com/recipe/1/x/"
    web.pages[url] = page("1 cup milk")
    assert review(links_on, url)["pints"]["us_site"] is False
    web.pages[url] = page("2 pints milk")
    shown = review(links_on, url, again=True)
    assert shown["pints"]["us_site"] is True and shown["pints"]["reading"] == "us"


def test_the_recipe_name_and_tags_are_tidied(links_on: TestClient, web: Web) -> None:
    url = "https://bananaleaf.example/x/"
    web.pages[url] = (
        '<html><script type="application/ld+json">{"@type":"Recipe",'
        '"name":"How to Make Butter Chicken (Authentic Indian Recipe)",'
        '"recipeCategory":["dinner","MAINS"],"recipeCuisine":"Main course",'
        '"recipeIngredient":["1 onion"],'
        '"recipeInstructions":["Cook."]}</script></html>'
    )
    shown = review(links_on, url)
    assert shown["name"] == "Butter Chicken"
    assert shown["tags"] == ["Dinner", "Main"]


def test_f91_every_source_of_a_name_is_tidied_the_same(links_on: TestClient, web: Web) -> None:
    """F91: JSON-LD, microdata, the page title and pasted text all go through one tidy."""
    url = "https://bananaleaf.example/lemon/"
    web.pages[url] = (
        '<html><script type="application/ld+json">{"@type":"Recipe",'
        '"name":"Lemon Rice Recipe (Chitranna)","recipeIngredient":["1 onion"],'
        '"recipeInstructions":["Cook."]}</script></html>'
    )
    assert review(links_on, url)["name"] == "Lemon Rice (Chitranna)"
    web.pages[url] = (
        '<html><body itemscope itemtype="https://schema.org/Recipe">'
        '<h1 itemprop="name">Sambar Recipe, How to Make Sambar</h1>'
        '<span itemprop="recipeIngredient">1 onion</span>'
        '<div itemprop="recipeInstructions">Cook.</div></body></html>'
    )
    assert review(links_on, url, again=True)["name"] == "Sambar"
    pasted = "Sambar Recipe, How to Make Sambar\nIngredients\n1 onion\nMethod\n1. Cook.\n"
    assert review(links_on, pasted)["name"] == "Sambar"


def test_cuts_into_slices_fills_serves(links_on: TestClient, web: Web) -> None:
    url = "https://bananaleaf.example/cake/"
    web.pages[url] = (
        '<html><script type="application/ld+json">{"@type":"Recipe","name":"Cake",'
        '"recipeYield":"Cuts into 10 slices","recipeIngredient":["1 onion"],'
        '"recipeInstructions":["Cook."]}</script></html>'
    )
    assert review(links_on, url)["serves"] == 10


def test_names_get_tidy_capitals_on_save(kitchen: TestClient, web: Web) -> None:
    shown = review(kitchen, "Dish\nIngredients\n2 tbsp kashmiri chilli powder\nMethod\n1. Mix.")
    choice = {
        0: {
            "kind": "new",
            "name": "KASHMIRI CHILLI POWDER",
            "counted_as": "weight",
            "place_id": None,
        }
    }
    saved = ok(save(kitchen, to_save(shown, choice)), 201)
    foods = ok(kitchen.get(f"{API}/foods"))["foods"]
    assert "Kashmiri chilli powder" in [f["name"] for f in foods]
    whole = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert whole["lines"][0]["food"]["name"] == "Kashmiri chilli powder"


@pytest.mark.parametrize("text", ["https://a.example/x", "https://a.example/x https://b.example/y"])
def test_links_never_become_a_recipe_named_after_an_address(
    kitchen: TestClient, web: Web, text: str
) -> None:
    # With the link switch off, nothing is read and nothing is made.
    response = kitchen.post(f"{API}/recipes/import", json={"text": text})
    assert response.status_code == 403


def test_a_huge_amount_in_pasted_text_still_gives_a_review(kitchen: TestClient, web: Web) -> None:
    text = (
        "Beans\nIngredients\n999999999999 999999999999oz can beans\n"
        "999999999999 x 999999999999 lb tins beans\n999999999999 999999999999 gallon cans beans\n"
        "2 pints milk\nMethod\n1. Mix."
    )
    shown = review(kitchen, text)
    assert len(shown["lines"]) == 4


def test_the_quart_switch_follows_the_pints_choice(kitchen: TestClient, web: Web) -> None:
    text = "Soup\nIngredients\n1 quart stock\n1 gallon water\n10 fl oz cream\nMethod\n1. Boil."
    uk = {line["words"]: line for line in review(kitchen, text)["lines"]}
    assert uk["stock"]["amount"] == 1136
    assert uk["stock"]["pint_ml"] == {"uk_ml": 1136.0, "us_ml": 946.0}
    assert uk["water"]["pint_ml"] == {"uk_ml": 4546.0, "us_ml": 3785.0}
    assert uk["cream"]["pint_ml"] == {"uk_ml": 284.0, "us_ml": 296.0}
    ok(kitchen.patch(f"{API}/household", json={"pints": "us"}))
    us = {line["words"]: line for line in review(kitchen, text)["lines"]}
    assert (us["stock"]["amount"], us["water"]["amount"], us["cream"]["amount"]) == (946, 3785, 296)


def test_kept_in_exceptions(kitchen: TestClient, web: Web) -> None:
    """cabledrawer 31 Oct: chicken bouillon and corned beef are Cupboard, fish fingers Freezer."""
    text = (
        "Tea\nIngredients\n1 chicken bouillon cube\n1 tin corned beef\n8 fish fingers\n"
        "500 g chicken breast\nMethod\n1. Cook."
    )
    places = {
        line["words"]: line["new_ingredient"]["place"]["name"]
        for line in review(kitchen, text)["lines"]
    }
    assert places["chicken bouillon cube"] == "Cupboard"
    assert places["corned beef"] == "Cupboard"
    assert places["fish fingers"] == "Freezer"
    assert places["chicken breast"] == "Fridge"


def test_a_one_megabyte_hostile_ingredient_line_does_not_freeze_the_import(
    links_on: TestClient, web: Web
) -> None:
    import json
    import time

    url = "https://bananaleaf.example/hostile/"
    hostile = "(note 1" * 150_000  # about 1 MB
    web.pages[url] = (
        '<html><script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "Recipe",
                "name": "Hostile",
                "recipeIngredient": [hostile, "1 onion"],
                "recipeInstructions": ["Cook."],
            }
        )
        + "</script></html>"
    )
    started = time.perf_counter()
    shown = review(links_on, url)
    # 5 s: the page is read in a child process, and starting one can take seconds on a busy
    # machine. A line that froze the reader would run into the reader's 12 s limit.
    assert time.perf_counter() - started < 5
    assert len(shown["lines"]) >= 1


def test_f109_water_and_broth_is_two_lines_and_no_name_is_learned_from_an_and(
    kitchen: TestClient, web: Web
) -> None:
    """F109 (cabledrawer 31 Oct): two lines, no amount, the note "4½ cups together"; a line with
    "and" in its name offers "Same as" without learning the name."""
    text = (
        "Soup\nIngredients\n4 1/2 cups water and broth (see instructions)\n"
        "1 cup half and half\n1 cup cream\nMethod\n1. Cook.\n"
    )
    lines = lines_of(review(kitchen, text))
    assert [line["words"] for line in lines] == ["water", "broth", "half and half", "cream"]
    for line in lines[:2]:
        assert (line["amount"], line["unit"], line["counts"]) == (None, None, False)
        assert line["note"] == "4½\u00a0cups together, see instructions"
        assert line["written"] == "4 1/2 cups water and broth (see instructions)"
        assert line["learn_name"] == line["words"]
    assert lines[2]["learn_name"] is None  # the name joins two: never another name
    assert lines[3]["learn_name"] == "cream"


def test_f109_save_never_learns_a_name_that_joins_two(kitchen: TestClient, web: Web) -> None:
    """Even a draft kept before this change, or a hand-made request, cannot teach one."""
    shown = review(kitchen, "Soup\nIngredients\n1 cup cream\nMethod\n1. Cook.\n")
    made = kitchen.post(f"{API}/foods", json={"name": "Water", "counted_as": "volume"})
    assert made.status_code == 201, made.text
    food_id = made.json()["food"]["id"]
    link = {"kind": "ingredient", "food_id": food_id, "learn": "water and broth"}
    saved = ok(save(kitchen, to_save(shown, {0: link})), 201)
    assert saved["learned"] == 0
    other = {**link, "learn": "tap water"}
    again = ok(save(kitchen, to_save(shown, {0: other})), 201)
    assert again["learned"] == 1
