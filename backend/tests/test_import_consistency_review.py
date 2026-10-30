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
from test_recipes import save as edit_recipe

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


def test_a_dozen_and_cloves_count_as_the_number_itself(kitchen: TestClient, web: Web) -> None:
    lines = lines_of(review(kitchen, LAMB))
    eggs = next(line for line in lines if line["words"] == "eggs")
    assert (eggs["amount"], eggs["size"]) == (12, None)
    garlic = [line for line in lines if line["words"] == "garlic"]
    assert len(garlic) == 2
    # Written before or after the name: the same amount.
    assert garlic[0]["amount"] == garlic[1]["amount"] == 2
    assert garlic[0]["note"] == garlic[1]["note"] == "cloves, minced"


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


def test_several_links_are_read_one_at_a_time(links_on: TestClient, web: Web) -> None:
    from test_recipe_import import LINK

    second = "https://bananaleaf.example/other/"
    shown = review(links_on, f"{LINK}\n{second}\n")
    assert web.asked == [LINK]  # only the first was visited
    assert shown["more_links"] == 1
    assert shown["source"]["kind"] == "link" and shown["lines"]
    one = review(links_on, LINK, again=True)
    assert one["more_links"] == 0


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


def test_a_link_import_edited_later_is_marked(links_on: TestClient, web: Web) -> None:
    from test_recipe_import import LINK

    shown = review(links_on, LINK)
    shown["nutrition"] = {"kcal": 200, "protein": None, "carbs": None, "fat": None, "fibre": None}
    saved = ok(save(links_on, to_save(shown)), 201)["recipe"]
    recipe = ok(links_on.get(f"{API}/recipes/{saved['id']}"))
    assert recipe["nutrition_possibly_out_of_date"] is False
    edited = ok(edit_recipe(links_on, recipe, name="Poriyal, my way"))
    assert edited["nutrition_possibly_out_of_date"] is True
    plain = ok(links_on.get(f"{API}/recipes/{recipe['id']}"))
    assert plain["nutrition_possibly_out_of_date"] is True


@pytest.mark.parametrize("text", ["https://a.example/x", "https://a.example/x https://b.example/y"])
def test_links_never_become_a_recipe_named_after_an_address(
    kitchen: TestClient, web: Web, text: str
) -> None:
    # With the link switch off, nothing is read and nothing is made.
    response = kitchen.post(f"{API}/recipes/import", json={"text": text})
    assert response.status_code == 403
