"""The page reader: a recipe from a web page's schema.org data (spec section 6, "Recipe
import, decided for 0.5").

The pages in tests/import_pages/ are made up: each copies only the structure a kind of
recipe site uses, with our own text and `.example` addresses. No real page was copied, and
nothing here goes online. Some of them hold hidden characters on purpose (a zero-width
space, a soft hyphen, a byte-order mark, a line separator, a joiner); keep them when
editing.
"""

import html.parser
import json
import re
import time
import tracemalloc
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mealwright import page_reader
from mealwright.page_reader import (
    MAX_LINES,
    MAX_STEPS,
    MAX_TAGS,
    NUTRIENTS,
    PageLine,
    PageRecipe,
    read_page,
)

PAGES = Path(__file__).parent / "import_pages"
URL = "https://site.example/recipes/one/"
NO_NUTRITION: dict[str, Decimal | None] = dict.fromkeys(NUTRIENTS)


def page(name: str, url: str = URL) -> PageRecipe | None:
    raw = (PAGES / name).read_bytes()
    text = raw.decode("latin-1" if name == "old_microdata.html" else "utf-8")
    return read_page(text, url)


def found(name: str, url: str = URL) -> PageRecipe:
    recipe = page(name, url)
    assert recipe is not None
    return recipe


def json_ld(*blocks: object, head: str = "") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in blocks
    )
    return f"<html><head>{head}{scripts}</head><body></body></html>"


def recipe(**fields: Any) -> dict[str, Any]:
    """A small JSON-LD recipe, with `fields` added or replaced."""
    base: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Toor dal",
        "recipeIngredient": ["200 g toor dal"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Boil the dal."}],
    }
    base.update(fields)
    return {k: v for k, v in base.items() if v is not None}


def read(**fields: Any) -> PageRecipe:
    result = read_page(json_ld(recipe(**fields)), URL)
    assert result is not None
    return result


def lines(*texts: str, heading: frozenset[str] = frozenset()) -> tuple[PageLine, ...]:
    return tuple(PageLine(t, heading=t in heading) for t in texts)


# --- The eight kinds of site -----------------------------------------------------------------


def test_big_magazine() -> None:
    assert found("big_magazine.html") == PageRecipe(
        name="Smoky bean and squash stew",
        description=(
            "A thick, warming stew of butter beans and roasted squash with smoked paprika."
            " Ready in under an hour."
        ),
        author="Ada Testwell",
        total_minutes=55,
        serves=4,
        makes=None,
        nutrition={
            "kcal": Decimal(412),
            "protein": Decimal(16),
            "carbs": Decimal(55),
            "fat": Decimal(12),
            "fibre": Decimal(15),
        },
        tags=("Dinner", "Main course", "British"),  # not the keywords
        photo_url="https://images.bigfood.example/recipes/smoky-stew-1200.jpg",
        ingredients=lines(
            "1 butternut squash, peeled and cut into chunks",
            "2 tbsp olive oil",
            "1 onion, chopped",
            "2 garlic cloves, crushed",
            "2 tsp smoked paprika",
            "400g can chopped tomatoes",
            "2 x 400g cans butter beans, drained",
            "300ml vegetable stock",
        ),
        steps=lines(
            "Heat oven to 200C/180C fan/gas 6. Toss the squash with half the oil and roast for"
            " 25 mins.",
            "Meanwhile, soften the onion in the rest of the oil for 10 mins. Stir in the garlic"
            " and paprika for 1 min.",
            "Add the tomatoes, beans and stock, then simmer for 15 mins. Stir in the roasted"
            " squash and season.",
        ),
        lines_cut=False,
        steps_cut=False,
    )


def test_wp_recipe_maker_graph() -> None:
    found_ = found("wp_recipe_maker.html")
    assert found_.name == "Lemon Herb Chicken Traybake"
    assert found_.author == "Rowan Field"  # an @id reference to a Person in the graph
    assert found_.total_minutes == 60
    assert (found_.serves, found_.makes) == (4, None)  # ["4", "4 servings"]
    assert found_.photo_url == "https://quietkitchen.example/wp-content/uploads/traybake.jpg"
    assert found_.tags == ("Main Course", "Mediterranean")
    assert found_.nutrition == {
        "kcal": Decimal(520),
        "protein": Decimal(38),
        "carbs": Decimal(32),
        "fat": Decimal(27),
        "fibre": None,  # not on the page: unknown, never 0
    }
    assert found_.steps == lines(
        "Prepare",
        "Heat the oven to 200°C.",
        "Toss the potatoes, lemons and oil on a large tray.",
        "Roast",
        "Nestle in the chicken, skin side up, and scatter over the thyme and salt.",
        "Roast for 45 minutes until golden.",  # a HowToStep with only a name
        heading=frozenset({"Prepare", "Roast"}),
    )
    assert found_.ingredients[0] == PageLine("8 chicken thighs (skin on, bone in)")
    assert len(found_.ingredients) == 6


def test_tasty_recipes() -> None:
    found_ = found("tasty_recipes.html")
    # Entities decoded, even when the site encoded them twice ("&amp;amp;").
    assert found_.description == "Chewy oat cookies with nutty brown butter & a pinch of sea salt."
    assert found_.author == "Mo & Jules"
    assert found_.ingredients[4] == PageLine("½ tsp bicarbonate of soda")
    assert found_.steps == lines(
        "Melt the butter in a pan and cook until it smells nutty \u2013 about 5 minutes."
        " Let it cool.",
        "Beat in the sugar and egg, then stir in the flour, soda and oats.",  # <p> removed
        "Roll into balls, bake at 180°C for 11 minutes and sprinkle with salt.",
    )
    # ["24", "24 cookies"]: the bare 24 only repeats Makes, so it isn't Serves.
    assert (found_.serves, found_.makes) == (None, (Decimal(24), "cookies"))
    assert found_.photo_url == (
        "https://sunnycrumb.example/wp-content/uploads/oat-cookies-225x225.jpg"
    )
    assert found_.nutrition["carbs"] == Decimal("12.4")
    assert found_.total_minutes == 31


def test_dotdash() -> None:
    found_ = found("dotdash.html")  # @type ["Recipe", "NewsArticle"], inside a list
    assert found_.name == "Slow Cooker Pulled Jackfruit"
    assert found_.author == "Pat Example"  # the first of several
    assert found_.total_minutes == 495  # P0DT8H15M
    assert found_.serves == 6
    assert found_.tags == ("Dinner", "Main Dishes", "American")
    assert found_.photo_url == "https://everydaydish.example/thmb/abc=/1500x0/jackfruit.jpg"
    assert found_.nutrition == {
        "kcal": Decimal(233),
        "protein": Decimal(2),
        "carbs": Decimal(49),
        "fat": Decimal(1),
        "fibre": Decimal(4),
    }
    assert found_.steps[0] == PageLine("Rinse the jackfruit and cut away any hard core.")
    assert len(found_.steps) == 4


def test_south_indian_blog() -> None:
    found_ = found("south_indian_blog.html")
    # The zero-width space is taken out; Tamil and Hindi stay as they are.
    assert found_.name == "Vendakkai Poriyal (வெண்டைக்காய் பொரியல் / भिंडी की सब्ज़ी)"
    assert found_.author == "Meena Raman"  # a left-to-right mark taken out
    assert found_.description == (
        "A dry okra stir-fry with a mustard seed and urad dal tadka, finished with fresh"
        " coconut. Serve with rice and sambar."  # a soft hyphen taken out
    )
    assert found_.ingredients == lines(
        "For the poriyal",
        "250 g vendakkai (வெண்டைக்காய் / भिंडी, okra), cut into rounds",
        "1 small onion, finely chopped",  # a no-break space becomes a space
        "¼ tsp turmeric powder",
        "Salt to taste",
        "For the tadka",
        "1 tbsp coconut oil",
        "1 tsp mustard seeds (கடுகு / राई)",
        "1 tsp urad dal (உளுத்தம் பருப்பு)",
        "1 sprig curry leaves (கறிவேப்பிலை / करी पत्ता)",
        "To finish",
        "2 tbsp grated coconut (தேங்காய் / नारि\u200dयल)",  # the joiner is kept
        heading=frozenset({"For the poriyal", "For the tadka", "To finish"}),
    )
    assert found_.steps == lines(
        "Tadka",
        "Heat the coconut oil. Add the mustard seeds and let them splutter.",  # BOM out
        "Add the urad dal and curry leaves and fry until the dal turns golden.",
        "Poriyal",
        "Add the onion and fry for 2 minutes, then the okra, turmeric and salt.",
        # A line separator becomes a space.
        "Cook uncovered on a low flame, stirring now and then, for 15 minutes. Do not cover,"
        " or the okra turns sticky.",
        "Stir in the coconut and switch off.",
        heading=frozenset({"Tadka", "Poriyal"}),
    )
    assert found_.serves == 3  # "3 to 4 servings"
    assert found_.total_minutes == 30  # no totalTime: prep + cook
    assert found_.tags == ("Side Dish", "South Indian", "Tamil Nadu")
    assert found_.photo_url == "https://site.example/wp-content/uploads/vendakkai-poriyal.jpg"
    assert found_.nutrition == {
        "kcal": Decimal("119.981"),  # 502 kJ
        "protein": Decimal("2.8"),
        "carbs": Decimal("9.5"),
        "fat": Decimal(7),
        "fibre": Decimal("3.2"),  # "3,2 g"
    }


def test_newspaper() -> None:
    found_ = found("newspaper.html")
    assert found_.name == "Charred leeks with hazelnut dressing"
    description = found_.description
    assert description is not None
    assert len(description) <= 200
    assert description.endswith("parsley and…")  # cut at a word, tags taken out
    assert description.startswith("Leeks are at their best right now, so")
    assert found_.total_minutes is None  # no times on the page
    assert found_.nutrition == NO_NUTRITION
    assert found_.serves == 4  # "Serves 4\u20136"
    assert found_.tags == ("Starter",)
    assert found_.photo_url == "https://i.dailyexample.example/img/media/leeks/master/2000.jpg"
    assert found_.ingredients[2] == PageLine("For the dressing", heading=True)
    assert found_.steps == lines(
        "Trim the leeks and cut each into three.",
        "Cook in a hot dry pan for 10\u201312 minutes, turning, until charred all over.",
        "Mix the dressing ingredients, season, and spoon over the warm leeks.",
    )


def test_old_microdata_page() -> None:
    assert found("old_microdata.html") == PageRecipe(
        name="Granny's Split Pea Soup",
        description="A thick, comforting soup of split peas and smoked ham hock.",
        author="Nell Example",  # the author's name, not taken as the recipe's
        total_minutes=140,  # prep 20 + cook 2 hours
        serves=6,
        makes=None,
        nutrition={
            "kcal": Decimal(380),
            "protein": Decimal(29),
            "carbs": None,
            "fat": Decimal(6),
            "fibre": None,
        },
        tags=("Soup", "British"),
        photo_url="https://oldrecipebox.example/soups/images/split-pea.jpg",  # <base href>
        ingredients=lines(
            "500 g dried green split peas",
            "1 smoked ham hock",
            "2 carrots, diced",
            "1 onion, diced",
            "2 litres water",
        ),
        steps=lines(
            "Rinse the peas.",
            "Put everything into a large pot, bring to the boil and skim.",
            "Simmer for 2 hours, take out the hock, shred the meat and stir it back in.",
        ),
        lines_cut=False,
        steps_cut=False,
    )


def test_a_page_with_no_recipe() -> None:
    assert page("no_recipe.html") is None


def test_several_blocks_one_broken() -> None:
    found_ = found("several_blocks.html")
    assert found_.name == "Sticky miso aubergine"  # not "Not this one" from a plain script
    assert (found_.serves, found_.makes) == (2, (Decimal(8), "slices"))
    assert found_.photo_url == "https://site.example/img/aubergine-16x9.jpg"  # contentUrl
    assert (found_.description, found_.author, found_.total_minutes) == (None, None, None)
    assert found_.nutrition == NO_NUTRITION
    assert found_.tags == ()
    assert len(found_.steps) == 4


@pytest.mark.parametrize("name", sorted(p.name for p in PAGES.glob("*.html")))
def test_every_page_is_made_up(name: str) -> None:
    """Only .example addresses, and no photos or other files next to the pages."""
    text = (PAGES / name).read_bytes().decode("latin-1")
    for address in re.findall(r"(?:https?:)?//([A-Za-z0-9.-]+)", text):
        assert address == "schema.org" or address.endswith(".example"), address
    assert {p.suffix for p in PAGES.iterdir()} == {".html"}


# --- What counts as a recipe -----------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        "",
        "Just some text",
        "<html><body><h1>Toor dal</h1><ul><li>200 g toor dal</li></ul></body></html>",
        json_ld({"@type": "Article", "name": "Toor dal"}),
        json_ld(recipe(recipeIngredient=None, recipeInstructions=None)),  # a name only
        json_ld({"@type": "Recipe", "recipeIngredient": [], "recipeInstructions": "  "}),
        '<script type="application/ld+json">{"@type": "Recipe", </script>',
        '<script type="application/ld+json">' + "[" * 100_000 + "</script>",
        '<script type="application/ld+json">' + "1" * 5_000 + "</script>",
        '<script type="application/ld+json">null</script>',
        "<div>" * 5_000 + "Recipe" + "</div>" * 5_000,
        '<div itemscope itemtype="https://schema.org/Recipe"><b itemprop="name">Dal</b></div>',
    ],
)
def test_no_recipe(html: str) -> None:
    assert read_page(html, URL) is None


@pytest.mark.parametrize(
    "kind",
    [
        "Recipe",
        ["Recipe"],
        ["NewsArticle", "Recipe"],
        "schema:Recipe",
        "http://schema.org/Recipe",
        "https://schema.org/Recipe",
    ],
)
def test_type_forms(kind: object) -> None:
    assert read(**{"@type": kind}).name == "Toor dal"


def test_a_recipe_deep_in_the_graph_and_the_first_with_ingredients() -> None:
    teaser = {"@type": "Recipe", "name": "Another recipe", "url": "https://site.example/2/"}
    html = json_ld(
        {
            "@graph": [
                {"@type": "WebPage", "mainEntity": teaser},
                {"@type": "ItemList", "itemListElement": [{"item": recipe(name="Rasam")}]},
            ]
        }
    )
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.name == "Rasam"


def test_schema_prefixed_property_names() -> None:
    html = json_ld(
        {
            "@type": "schema:Recipe",
            "schema:name": "Poha",
            "http://schema.org/recipeIngredient": ["1 cup poha"],
        }
    )
    found_ = read_page(html, URL)
    assert found_ is not None
    assert (found_.name, found_.ingredients) == ("Poha", (PageLine("1 cup poha"),))


def test_comments_and_cdata_around_the_json() -> None:
    body = json.dumps(recipe(name="Upma"))
    for wrapped in [f"<!-- {body} -->", f"//<![CDATA[\n{body}\n//]]>", f"<![CDATA[{body}]]>"]:
        html = f'<script type="application/ld+json">{wrapped}</script>'
        found_ = read_page(html, URL)
        assert found_ is not None, wrapped
        assert found_.name == "Upma"


def test_control_characters_inside_json_strings() -> None:
    """Some sites put raw tabs and line breaks inside JSON strings."""
    html = '<script type="application/ld+json">{"@type":"Recipe","name":"Idli\tsambar",'
    html += '"recipeIngredient":["2 cups\nidli rice"]}</script>'
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.name == "Idli sambar"
    assert found_.ingredients == (PageLine("2 cups"), PageLine("idli rice"))


def test_script_type_with_parameters_and_capitals() -> None:
    html = (
        '<script type="Application/LD+JSON; charset=utf-8">'
        + json.dumps(recipe(name="Pongal"))
        + "</script>"
    )
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.name == "Pongal"


# --- Name and description --------------------------------------------------------------------


def test_name_falls_back_to_the_page_title() -> None:
    og = '<meta property="og:title" content="Lemon rice">'
    title = "<title>Lemon rice | My blog</title>"
    found_ = read_page(json_ld(recipe(name=None), head=og + title), URL)
    assert found_ is not None
    assert found_.name == "Lemon rice"
    found_ = read_page(json_ld(recipe(name=None), head=title), URL)
    assert found_ is not None
    assert found_.name == "Lemon rice | My blog"
    found_ = read_page(json_ld(recipe(name=None)), URL)
    assert found_ is not None
    assert found_.name == ""


def test_the_name_is_cut_at_200() -> None:
    name = read(name="word " * 60).name
    assert len(name) <= 200
    assert name.endswith("word…")


def test_description_cut_at_200_at_a_word() -> None:
    words = "Crisp dosa with potato masala and two chutneys, " * 6
    description = read(description=words).description
    assert description is not None
    assert len(description) <= 200
    assert description.endswith("…")
    cut = description.removesuffix("…")
    assert words.startswith(cut)
    assert words[len(cut)] in " ,"  # cut between words, not inside one


def test_description_of_exactly_200_is_kept() -> None:
    text = ("a" * 99 + " ") * 2
    assert read(description=text.strip() + "b").description == text.strip() + "b"
    assert len(text.strip() + "b") == 200
    assert read(description="x" * 201).description == "x" * 199 + "…"  # one long word


def test_empty_description_is_none() -> None:
    assert read(description="  <p> </p> ").description is None
    assert read(description=None).description is None


# --- Author -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("Kavya", "Kavya"),
        ({"@type": "Person", "name": "Kavya"}, "Kavya"),
        ({"@type": "Organization", "name": "Test Kitchen"}, "Test Kitchen"),
        ([{"@type": "Person", "name": ""}, {"@type": "Person", "name": "Kavya"}], "Kavya"),
        (["Kavya", "Arjun"], "Kavya"),
        ({"@type": "Person"}, None),
        (42, None),
        (None, None),
    ],
)
def test_author(author: object, expected: str | None) -> None:
    assert read(author=author).author == expected


# --- Times ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("times", "minutes"),
    [
        ({"totalTime": "PT45M"}, 45),
        ({"totalTime": "PT1H30M", "prepTime": "PT5M", "cookTime": "PT5M"}, 90),
        ({"prepTime": "PT10M", "cookTime": "PT1H"}, 70),
        ({"prepTime": "PT10M"}, 10),
        ({"cookTime": "PT2H"}, 120),
        ({"totalTime": "P1DT2H"}, 1560),
        ({"totalTime": "P0DT0H20M"}, 20),
        ({"totalTime": "PT0.5H"}, 30),
        ({"totalTime": "PT1,5H"}, 90),
        ({"totalTime": "PT90S"}, 2),
        ({"totalTime": "pt20m"}, 20),
        ({"totalTime": "P10D"}, 14_400),
        ({"totalTime": "P10DT1M"}, None),  # over 10 days
        ({"prepTime": "P5D", "cookTime": "P5DT1M"}, None),
        ({"totalTime": "PT0M"}, None),
        ({"totalTime": "PT0M", "prepTime": "PT5M"}, 5),
        ({"totalTime": "45 minutes"}, None),  # not a duration: left out, not guessed
        ({"totalTime": "PT"}, None),
        ({"totalTime": "P1DT"}, None),
        ({"totalTime": ""}, None),
        ({"totalTime": "30"}, 30),
        ({"totalTime": 25}, 25),
        ({"totalTime": True}, None),
        ({"totalTime": ["PT15M"]}, 15),
        ({}, None),
    ],
)
def test_times(times: dict[str, object], minutes: int | None) -> None:
    assert read(**times).total_minutes == minutes


def test_infinite_and_huge_times() -> None:
    html = '<script type="application/ld+json">{"@type":"Recipe","name":"Dal",'
    html += '"recipeIngredient":["dal"],"totalTime":Infinity,"prepTime":NaN,'
    html += '"cookTime":"PT99999999999999999999H"}</script>'
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.total_minutes is None


MILLION_DIGITS = "1" * 1_000_001


@pytest.mark.parametrize(
    "time_",
    [
        "1" * 5_000_000,  # a bare number: 214 s before the 20-character limit
        "PT" + MILLION_DIGITS + "M",  # 8.6 s, and one digit more overflowed
        "P" + MILLION_DIGITS + "W",  # decimal.Overflow out of read_page
        "PT1." + MILLION_DIGITS + "H",
        "1" * 21,
        "PT" + "1" * 21 + "M",
    ],
)
def test_a_very_long_number_in_a_time_is_refused_quickly(time_: str) -> None:
    """Number text over 20 characters is refused before it's converted, like 0.4's amounts
    (MAX_NUMBER_TEXT). Turning a long digit string into a number takes time that grows with
    its square, and a big enough one overflowed."""
    start = time.monotonic()
    found_ = read(totalTime=time_)
    assert time.monotonic() - start < 1
    assert found_.total_minutes is None


def test_real_times_are_read_as_before_the_number_limit() -> None:
    assert read(totalTime="PT1H30M").total_minutes == 90
    assert read(totalTime="0" * 18 + "45").total_minutes == 45  # 20 characters: read
    assert read(totalTime="PT" + "0" * 18 + "45M").total_minutes == 45


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("calories", MILLION_DIGITS + " kJ"),  # decimal.Overflow before the limit
        ("proteinContent", MILLION_DIGITS + " mg"),
        ("calories", "1." + MILLION_DIGITS + " kcal"),
        ("calories", "1e" + MILLION_DIGITS),
        ("calories", "1" * 21 + " kcal"),
        ("calories", "0" * 20 + "1 kcal"),  # never read as its first 20 digits
        ("calories", "0." + "0" * 19 + "1 kcal"),  # 22 characters
        ("fatContent", "1,000,000,000,000,000,000,000 g"),
    ],
)
def test_a_very_long_number_in_nutrition_is_refused_quickly(field: str, value: str) -> None:
    start = time.monotonic()
    found_ = read(nutrition=facts(**{field: value}))
    assert time.monotonic() - start < 1
    assert found_.nutrition == NO_NUTRITION


@pytest.mark.parametrize(
    "value", ["1" * 5_000_000 + " servings", "4." + MILLION_DIGITS, "1" * 21 + " cookies"]
)
def test_a_very_long_number_in_a_yield_is_refused_quickly(value: str) -> None:
    start = time.monotonic()
    found_ = read(recipeYield=value)
    assert time.monotonic() - start < 2
    assert (found_.serves, found_.makes) == (None, None)


def test_real_numbers_are_read_as_before_the_number_limit() -> None:
    found_ = read(
        recipeYield="4 servings",
        nutrition=facts(calories="320 kcal", proteinContent="12.5 g", fatContent="1,200 mg"),
    )
    assert found_.serves == 4
    assert found_.nutrition["kcal"] == Decimal(320)
    assert found_.nutrition["protein"] == Decimal("12.5")
    assert found_.nutrition["fat"] == Decimal("1.2")
    assert read(recipeYield="Serves 4 to " + "6" * 30).serves == 4  # the range's end isn't read


# --- Serves and Makes ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "serves", "makes"),
    [
        (4, 4, None),
        ("4", 4, None),
        ("Serves 4", 4, None),
        ("serves: 6", 6, None),
        ("4 servings", 4, None),
        ("4 portions", 4, None),
        ("6 people", 6, None),
        ("For 2", 2, None),
        ("Serves 4\u20136", 4, None),
        ("4-6 servings", 4, None),
        ("about 8 servings", 8, None),
        ("12 cookies", None, (Decimal(12), "cookies")),
        ("Makes 12 dosas", None, (Decimal(12), "dosas")),
        ("Yield: 24 laddoos", None, (Decimal(24), "laddoos")),
        ("1.5 litres", None, (Decimal("1.5"), "litres")),
        ("1 loaf (about 900 g)", None, (Decimal(1), "loaf")),
        (["4", "4 servings"], 4, None),
        (["24", "24 cookies"], None, (Decimal(24), "cookies")),
        (["2", "8 slices"], 2, (Decimal(8), "slices")),
        (["Serves 4", "Makes 1 cake"], 4, (Decimal(1), "cake")),
        ("0", None, None),
        ("100", None, None),  # over 99
        ("150 servings", None, None),
        ("2.5", None, None),  # not a whole number of people
        ("Makes 12", None, None),  # a number of what?
        ("12 " + "x" * 31, None, None),  # unit over 30 characters
        ("12 %", None, None),
        ("A few", None, None),
        ("", None, None),
        (None, None, None),
        (True, None, None),
    ],
)
def test_yield(value: object, serves: int | None, makes: tuple[Decimal, str] | None) -> None:
    found_ = read(recipeYield=value)
    assert (found_.serves, found_.makes) == (serves, makes)


def test_yield_under_its_other_name() -> None:
    found_ = read(**{"yield": "3 servings"})
    assert found_.serves == 3


# --- Nutrition --------------------------------------------------------------------------------


def facts(**values: object) -> dict[str, object]:
    return {"@type": "NutritionInformation", **values}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("250 kcal", Decimal(250)),
        ("250", Decimal(250)),
        (250, Decimal(250)),
        (249.5, Decimal("249.5")),
        ("1,200 kcal", Decimal(1200)),
        ("1046 kJ", Decimal(250)),  # 1046 / 4.184 = 250
        ("Calories: 300", Decimal(300)),
        ("0 kcal", Decimal(0)),  # a real zero stays
        ("", None),
        ("n/a", None),
        ("200000 kcal", None),  # over 100,000
        ("1.5e2", Decimal(150)),  # an exponent is part of the number, not a unit
        ("1.5E2 kcal", Decimal(150)),
        ("2e-1 kcal", Decimal("0.2")),
        ("1e300", None),  # never 1, with "e" taken as a unit
        ("1e300 kcal", None),
        ("1e-300", None),
        ("1e99999999999", None),
        (1.5e2, Decimal(150)),
        (1e300, None),  # str() gives "1e+300"
        (1e-05, Decimal(0)),  # "1e-05"
        (float("inf"), None),
        (float("nan"), None),
        ("3 eggs", Decimal(3)),  # an "e" with no number after it is not an exponent
        (None, None),
        (True, None),
    ],
)
def test_calories(value: object, expected: Decimal | None) -> None:
    assert read(nutrition=facts(calories=value)).nutrition["kcal"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12 g", Decimal(12)),
        ("12g", Decimal(12)),
        ("12.5 g", Decimal("12.5")),
        ("12,5 g", Decimal("12.5")),
        ("0.1234 g", Decimal("0.123")),  # 3 decimal places
        ("1500 mg", Decimal("1.5")),
        ("250 mcg", Decimal("0.00025").quantize(Decimal("0.001"))),
        ("0 g", Decimal(0)),
        ("—", None),
    ],
)
def test_grams(value: object, expected: Decimal | None) -> None:
    assert read(nutrition=facts(proteinContent=value)).nutrition["protein"] == expected


def test_nutrition_keys_and_unknowns() -> None:
    found_ = read(
        nutrition=facts(
            calories="300 kcal",
            proteinContent="10 g",
            carbohydrateContent="40 g",
            fatContent="9 g",
            fiberContent="6 g",
            sugarContent="5 g",
            sodiumContent="300 mg",
        )
    )
    assert found_.nutrition == {
        "kcal": Decimal(300),
        "protein": Decimal(10),
        "carbs": Decimal(40),
        "fat": Decimal(9),
        "fibre": Decimal(6),
    }
    assert read(nutrition=facts(fatContent="9 g")).nutrition == {
        **NO_NUTRITION,
        "fat": Decimal(9),
    }
    assert read().nutrition == NO_NUTRITION
    assert read(nutrition="300 kcal").nutrition == NO_NUTRITION
    assert read(nutrition=[facts(fiberContent="2 g")]).nutrition["fibre"] == Decimal(2)


# --- Tags ------------------------------------------------------------------------------------


def test_tags_are_category_and_cuisine_never_keywords() -> None:
    found_ = read(
        recipeCategory=["Dinner", "Side dish, Snack"],
        recipeCuisine="Indian",
        keywords="quick, vegan, dal",
    )
    assert found_.tags == ("Dinner", "Side dish", "Snack", "Indian")
    assert read(keywords=["quick", "vegan"]).tags == ()


def test_tags_are_tidied() -> None:
    found_ = read(
        recipeCategory=["Dinner", "dinner", " DINNER ", "", "x" * 41, "y" * 40, {"name": "Lunch"}],
        recipeCuisine=["Indian", "South Indian", "indian", 7],
    )
    assert found_.tags == ("Dinner", "y" * 40, "Lunch", "Indian", "South Indian")


def test_at_most_20_tags() -> None:
    found_ = read(recipeCategory=[f"Tag {n}" for n in range(30)], recipeCuisine="Indian")
    assert len(found_.tags) == MAX_TAGS == 20
    assert found_.tags[-1] == "Tag 19"


# --- Photo -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("https://img.example/a.jpg", "https://img.example/a.jpg"),
        ("/a.jpg", "https://site.example/a.jpg"),
        ("a.jpg", "https://site.example/recipes/one/a.jpg"),
        ("//img.example/a.jpg", "https://img.example/a.jpg"),
        (["https://img.example/a.jpg", "https://img.example/b.jpg"], "https://img.example/a.jpg"),
        ({"@type": "ImageObject", "url": "https://img.example/a.jpg"}, "https://img.example/a.jpg"),
        ({"@type": "ImageObject", "contentUrl": "/c.jpg"}, "https://site.example/c.jpg"),
        ([{"@type": "ImageObject", "url": ["/d.jpg"]}], "https://site.example/d.jpg"),
        (["", "data:image/png;base64,AAAA", "/e.jpg"], "https://site.example/e.jpg"),
        ("javascript:alert(1)", None),
        ("ftp://img.example/a.jpg", None),
        ("", None),
        (7, None),
        (None, None),
    ],
)
def test_photo(image: object, expected: str | None) -> None:
    assert read(image=image).photo_url == expected


def test_photo_falls_back_to_the_page_preview_and_honours_base() -> None:
    head = '<base href="https://cdn.site.example/blog/"><meta property="og:image" content="p.jpg">'
    found_ = read_page(json_ld(recipe(), head=head), URL)
    assert found_ is not None
    assert found_.photo_url == "https://cdn.site.example/blog/p.jpg"
    # A base that isn't http(s) is ignored.
    head = '<base href="javascript:alert(1)//"><meta property="og:image" content="p.jpg">'
    found_ = read_page(json_ld(recipe(), head=head), URL)
    assert found_ is not None
    assert found_.photo_url == "https://site.example/recipes/one/p.jpg"


# --- Ingredients -----------------------------------------------------------------------------


def test_ingredient_lines_are_tidied() -> None:
    found_ = read(
        recipeIngredient=[
            "  1   cup   rice ",
            "<b>2</b> tbsp ghee",
            "1 tsp jeera &amp;amp; hing",
            "",
            "   ",
            "Salt\u200b to taste",
            "1\u00a0lemon",
            {"@type": "HowToSupply", "name": "1 onion"},
            4,
            None,
            True,
            ["nested list"],
        ]
    )
    assert found_.ingredients == lines(
        "1 cup rice",
        "2 tbsp ghee",
        "1 tsp jeera & hing",
        "Salt to taste",
        "1 lemon",
        "1 onion",
        "4",
        "nested list",
    )


def test_ingredient_headings() -> None:
    found_ = read(
        recipeIngredient=[
            "For the batter:",
            "1 cup rice",
            "Tadka :",
            "2 tsp oil:",  # has a number: an ingredient
            ":",
            "Note: soak overnight",  # doesn't end in ":"
            "A very long line that ends with a colon but is far too long to be a heading at all:",
        ]
    )
    assert found_.ingredients == lines(
        "For the batter",
        "1 cup rice",
        "Tadka",
        "2 tsp oil:",
        "Note: soak overnight",
        "A very long line that ends with a colon but is far too long to be a heading at all:",
        heading=frozenset({"For the batter", "Tadka"}),
    )  # a line that is only ":" is left out


def test_an_ingredient_block_with_line_breaks_is_split() -> None:
    found_ = read(recipeIngredient="1 cup rice\n2 cups water<br>salt")
    assert found_.ingredients == lines("1 cup rice", "2 cups water", "salt")


@pytest.mark.parametrize(("count", "cut"), [(199, False), (200, False), (201, True), (500, True)])
def test_at_most_200_ingredient_lines(count: int, cut: bool) -> None:
    found_ = read(recipeIngredient=[f"{n} g rice" for n in range(1, count + 1)])
    assert len(found_.ingredients) == min(count, MAX_LINES)
    assert found_.ingredients[-1].text == f"{min(count, 200)} g rice"
    assert found_.lines_cut is cut


def test_headings_count_towards_the_200() -> None:
    ingredients = []
    for n in range(100):
        ingredients += [f"Part {chr(65 + n % 26)}:", f"{n} g rice"]
    ingredients.append("one more")
    found_ = read(recipeIngredient=ingredients)
    assert len(found_.ingredients) == 200
    assert found_.lines_cut
    assert sum(line.heading for line in found_.ingredients) == 100


def test_long_lines_are_not_cut() -> None:
    long = "rice " * 400
    assert read(recipeIngredient=[long]).ingredients == (PageLine(long.strip()),)


# --- Method ----------------------------------------------------------------------------------


def step(text: str, **more: object) -> dict[str, object]:
    return {"@type": "HowToStep", "text": text, **more}


def test_method_shapes() -> None:
    found_ = read(
        recipeInstructions=[
            step("Soak the rice."),
            {"@type": "HowToStep", "name": "Grind it."},
            {"@type": "HowToStep", "text": "", "name": "Rest it."},
            {
                "@type": "HowToSection",
                "name": "Chutney",
                "itemListElement": [
                    step("Roast the dal."),
                    "Blend with coconut.",
                    {
                        "@type": "HowToSection",
                        "name": "Tempering",
                        "itemListElement": [step("Splutter the mustard.")],
                    },
                ],
            },
            {
                "@type": "HowToStep",
                "itemListElement": [
                    {"@type": "HowToDirection", "text": "Spread the batter."},
                    {"@type": "HowToTip", "text": "Keep the pan hot."},
                ],
            },
            {"@type": "ItemList", "itemListElement": [step("Serve.")]},
            {"@type": "HowToStep"},
            {"@type": "HowToStep", "text": "   "},
            7,
        ]
    )
    assert found_.steps == lines(
        "Soak the rice.",
        "Grind it.",
        "Rest it.",
        "Chutney",
        "Roast the dal.",
        "Blend with coconut.",
        "Tempering",
        "Splutter the mustard.",
        "Spread the batter. Keep the pan hot.",
        "Serve.",
        heading=frozenset({"Chutney", "Tempering"}),
    )


def test_a_section_with_no_name_has_no_heading() -> None:
    found_ = read(recipeInstructions=[{"@type": "HowToSection", "itemListElement": [step("Fry.")]}])
    assert found_.steps == lines("Fry.")


def test_method_as_text() -> None:
    assert read(recipeInstructions="Fry.\nAdd salt.\n\n  Serve.").steps == lines(
        "Fry.", "Add salt.", "Serve."
    )
    html = "<ol><li>Fry.</li><li>Add <b>salt</b>.</li></ol>"
    assert read(recipeInstructions=html).steps == lines("Fry.", "Add salt.")
    assert read(recipeInstructions=["Fry.", "Add salt."]).steps == lines("Fry.", "Add salt.")


def test_a_step_keeps_its_text_on_one_line() -> None:
    found_ = read(recipeInstructions=[step("Fry the onions\nuntil golden.\r\n\tThen add salt.")])
    assert found_.steps == lines("Fry the onions until golden. Then add salt.")


def test_steps_by_reference() -> None:
    html = json_ld(
        {
            "@graph": [
                recipe(recipeInstructions=[{"@id": "#s1"}, {"@id": "#missing"}]),
                {"@id": "#s1", "@type": "HowToStep", "text": "Boil."},
            ]
        }
    )
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.steps == lines("Boil.")


def test_a_section_that_lists_itself_is_walked_quickly() -> None:
    """A nameless section listing itself 50 times, 8 deep, is 50**8 visits unchecked."""
    loop = {"@id": "#loop", "@type": "HowToSection", "itemListElement": [{"@id": "#loop"}] * 50}
    html = json_ld({"@graph": [recipe(recipeInstructions=[step("Boil."), {"@id": "#loop"}]), loop]})
    start = time.monotonic()
    found_ = read_page(html, URL)
    assert time.monotonic() - start < 1
    assert found_ is not None
    assert found_.steps == lines("Boil.")


def test_sections_that_list_each_other_many_times_are_walked_quickly() -> None:
    """Nine nameless sections, each listing the next 50 times: no loop, but 50**8 visits."""
    chain = [
        {"@id": f"#s{n}", "@type": "HowToSection", "itemListElement": [{"@id": f"#s{n + 1}"}] * 50}
        for n in range(9)
    ]
    html = json_ld({"@graph": [recipe(recipeInstructions=[step("Boil."), {"@id": "#s0"}]), *chain]})
    start = time.monotonic()
    found_ = read_page(html, URL)
    assert time.monotonic() - start < 1
    assert found_ is not None
    assert found_.steps == lines("Boil.")


# One big object referenced many times: its text is tidied once, not once per reference,
# so the work grows with the page's size, not with references times size.
BIG = "<i></i>" * 30_000  # 210 KB of markup that tidies to nothing
BIG_OBJECT = {"@id": "#big", "@type": "HowToStep", "name": BIG, "text": BIG}
BIG_REFS = [{"@id": "#big"}] * 1_000


@pytest.fixture
def big_tidied(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts how often the big text is tidied, and fails the test at once the second
    time (without the fix it would be tidied 1,000 times or more, taking minutes)."""
    count = [0]
    real = page_reader._clean

    def counting(value: object) -> str:
        if isinstance(value, str) and len(value) >= len(BIG):
            count[0] += 1
            if count[0] > 1:
                pytest.fail("the big text was tidied more than once")
        return real(value)

    monkeypatch.setattr(page_reader, "_clean", counting)
    return count


def _read_big(*graph: object, **fields: Any) -> PageRecipe:
    start = time.monotonic()
    found_ = read_page(json_ld({"@graph": [recipe(**fields), *graph, BIG_OBJECT]}), URL)
    assert time.monotonic() - start < 2  # about 0.1 s; without the fix, minutes
    assert found_ is not None
    return found_


@pytest.mark.parametrize(
    "key", ["name", "description", "author", "recipeCategory", "recipeIngredient"]
)
def test_one_big_object_referenced_1000_times_is_tidied_once(
    big_tidied: list[int], key: str
) -> None:
    found_ = _read_big(**{key: BIG_REFS})
    assert big_tidied == [1]
    assert found_.name == ("" if key == "name" else "Toor dal")
    assert found_.description is None and found_.author is None and found_.tags == ()
    assert found_.ingredients == (() if key == "recipeIngredient" else lines("200 g toor dal"))


def test_a_method_listing_one_big_step_1000_times_tidies_it_once(big_tidied: list[int]) -> None:
    found_ = _read_big(recipeInstructions=[step("Boil."), *BIG_REFS])
    assert big_tidied == [1]
    assert found_.steps == lines("Boil.")


def test_a_chain_of_sections_reaching_one_big_step_tidies_it_once(
    big_tidied: list[int],
) -> None:
    """Each section lists the next 1,000 times; the last lists the big step 1,000 times."""
    chain = [
        {
            "@id": f"#s{n}",
            "@type": "HowToSection",
            "itemListElement": [{"@id": f"#s{n + 1}"}] * 1000,
        }
        for n in range(5)
    ]
    last = {"@id": "#s5", "@type": "HowToSection", "itemListElement": [*BIG_REFS, step("Boil.")]}
    found_ = _read_big(*chain, last, recipeInstructions=[{"@id": "#s0"}])
    assert big_tidied == [1]
    assert found_.steps == lines("Boil.")


def test_a_section_listing_itself_and_one_big_step_tidies_it_once(
    big_tidied: list[int],
) -> None:
    loop = {
        "@id": "#loop",
        "@type": "HowToSection",
        "itemListElement": [{"@id": "#big"}, {"@id": "#loop"}] * 500,
    }
    found_ = _read_big(loop, recipeInstructions=[step("Boil."), {"@id": "#loop"}])
    assert big_tidied == [1]
    assert found_.steps == lines("Boil.")


def test_one_big_text_used_by_eight_fields_is_tidied_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each different text is tidied once for the whole page, however many fields use it
    (without that, once per field: a 4.5 MB text in eight fields took 16 seconds)."""
    text = "<p>Stir.</p>" * 50_000  # 600 KB, tidied to 50,000 lines
    count = [0]
    real = page_reader._strip_hidden  # the last step of tidying, once for each text tidied

    def counting(tidied: str) -> str:
        if len(tidied) >= 100_000:
            count[0] += 1
            if count[0] > 1:
                pytest.fail("the big text was tidied more than once")
        return real(tidied)

    monkeypatch.setattr(page_reader, "_strip_hidden", counting)
    keys = ["name", "headline", "description", "author", "creator", "recipeCategory"]
    keys += ["recipeCuisine", "recipeInstructions"]
    fields = {key: {"@id": "#big"} for key in keys}
    big = {"@id": "#big", "@type": "HowToStep", "name": text}
    start = time.monotonic()
    found_ = read_page(json_ld({"@graph": [recipe(**fields), big]}), URL)
    assert time.monotonic() - start < 2  # about 0.3 s
    assert count == [1]
    assert found_ is not None
    stirs = " ".join(["Stir."] * 50_000)
    assert found_.name == "Stir. " * 32 + "Stir…"  # cut at 200, at a word
    assert found_.description == found_.author == found_.name
    assert found_.tags == ()  # longer than 40 characters
    assert found_.steps == lines(stirs)


@pytest.mark.parametrize(("count", "cut"), [(100, False), (101, True), (300, True)])
def test_at_most_100_steps(count: int, cut: bool) -> None:
    found_ = read(recipeInstructions=[step(f"Step {n}.") for n in range(1, count + 1)])
    assert len(found_.steps) == min(count, MAX_STEPS)
    assert found_.steps[-1].text == f"Step {min(count, 100)}."
    assert found_.steps_cut is cut


def test_section_headings_count_towards_the_100() -> None:
    sections = [
        {"@type": "HowToSection", "name": f"Part {n}", "itemListElement": [step("Stir.")]}
        for n in range(60)
    ]
    found_ = read(recipeInstructions=sections)
    assert len(found_.steps) == 100
    assert found_.steps_cut
    assert found_.steps[-2:] == (PageLine("Part 49", heading=True), PageLine("Stir."))


def test_a_recipe_with_only_steps_or_only_ingredients() -> None:
    assert read(recipeIngredient=None).ingredients == ()
    assert read(recipeInstructions=None).steps == ()


# --- Hidden characters -----------------------------------------------------------------------


def test_hidden_characters_are_taken_out_not_refused() -> None:
    found_ = read(
        name="Dal\u202e tadka\u0000",
        description="Smoky\u200b and\u00ad rich\x1b.",
        recipeIngredient=["1\u2028cup\u2029dal\x85", "Salt\u2060", "1 tsp\ufeff ghee"],
        recipeInstructions=[step("Fry\u200e the onions.\u200f")],
        recipeCategory=["Din\u200bner"],
        author="Kav\u200bya",
    )
    assert found_.name == "Dal tadka"
    assert found_.description == "Smoky and rich."
    assert found_.ingredients == lines("1 cup dal", "Salt", "1 tsp ghee")
    assert found_.steps == lines("Fry the onions.")
    assert found_.tags == ("Dinner",)
    assert found_.author == "Kavya"


def test_joiners_and_flags_are_kept() -> None:
    scotland = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    found_ = read(
        name=f"Shortbread {scotland}",
        recipeIngredient=["1 cup நெய்\u200c", "👩\u200d🍳 love"],
    )
    assert found_.name == f"Shortbread {scotland}"
    assert found_.ingredients == lines("1 cup நெய்\u200c", "👩\u200d🍳 love")
    # Tag letters on their own spell invisible text: taken out.
    assert read(name="Dal\U000e0041\U000e0042").name == "Dal"


# --- Microdata -------------------------------------------------------------------------------


def test_microdata_shapes() -> None:
    html = """
    <div itemscope itemtype="https://schema.org/Recipe">
      <h1 itemprop="name headline">Masala <i>dosa</i></h1>
      <div itemprop="author" itemscope itemtype="https://schema.org/Person">
        <span itemprop="name">Arjun</span>
      </div>
      <a itemprop="image" href="/dosa.jpg">photo</a>
      <data itemprop="recipeYield" value="4">four people</data>
      <meta itemprop="totalTime" content="PT40M">
      <span itemprop="http://schema.org/recipeCategory">Breakfast</span>
      <span itemprop="keywords">crispy</span>
      <ul>
        <li itemprop="recipeIngredient">2 cups dosa batter</li>
        <li itemprop="recipeIngredient">2 potatoes</li>
      </ul>
      <ol>
        <li itemprop="recipeInstructions" itemscope itemtype="https://schema.org/HowToStep">
          <span itemprop="text">Make the masala.</span></li>
        <li itemprop="recipeInstructions" itemscope itemtype="https://schema.org/HowToStep">
          <span itemprop="text">Spread the batter.</span></li>
      </ol>
      <div itemprop="nutrition" itemscope itemtype="https://schema.org/NutritionInformation">
        <span itemprop="calories">310 kcal</span>
        <span itemprop="fiberContent">5 g</span>
      </div>
      <div itemscope itemtype="https://schema.org/Comment">
        <span itemprop="name">Not the recipe's name</span>
      </div>
    </div>
    """
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.name == "Masala dosa"
    assert found_.author == "Arjun"
    assert found_.photo_url == "https://site.example/dosa.jpg"
    assert found_.serves == 4
    assert found_.total_minutes == 40
    assert found_.tags == ("Breakfast",)
    assert found_.ingredients == lines("2 cups dosa batter", "2 potatoes")
    assert found_.steps == lines("Make the masala.", "Spread the batter.")
    assert found_.nutrition == {**NO_NUTRITION, "kcal": Decimal(310), "fibre": Decimal(5)}


def test_json_ld_wins_over_microdata() -> None:
    micro = (
        '<div itemscope itemtype="http://schema.org/Recipe"><b itemprop="name">Micro</b>'
        '<i itemprop="recipeIngredient">1 cup</i></div>'
    )
    html = json_ld(recipe(name="From JSON-LD")).replace("<body>", "<body>" + micro)
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.name == "From JSON-LD"


# --- The page as a whole -----------------------------------------------------------------------


def test_deeply_nested_and_broken_html_is_read() -> None:
    deep = "<div>" * 2_000 + json_ld(recipe(name="Deep")) + "</div>" * 10
    found_ = read_page(deep, URL)
    assert found_ is not None
    assert found_.name == "Deep"
    # Unclosed and stray tags. (A <title> left open hides the rest of the page from
    # browsers too, so it isn't tried.)
    broken = "<html><head><title>Oops</title><body><p><b><div>" + json_ld(recipe(name="Still"))
    broken += "</span></i></td></html></html>"
    found_ = read_page(broken, URL)
    assert found_ is not None
    assert found_.name == "Still"


def test_deeply_nested_json() -> None:
    nested = "[" * 600 + '"1 cup rice"' + "]" * 600
    html = '<script type="application/ld+json">{"@type":"Recipe","name":"Deep",'
    html += f'"recipeIngredient":[[["2 cups water"]]],"recipeInstructions":{nested}}}</script>'
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.ingredients == lines("2 cups water")
    assert found_.steps == ()  # too deep to be a method


def test_deeply_nested_microdata() -> None:
    html = (
        '<div itemscope itemtype="http://schema.org/Recipe"><b itemprop="name">Deep</b>'
        + '<div itemprop="x" itemscope>' * 300
        + "</div>" * 300
        + '<i itemprop="recipeIngredient">1 cup</i></div>'
    )
    found_ = read_page(html, URL)
    assert found_ is not None
    assert found_.ingredients == lines("1 cup")


# Microdata properties inside properties: an element's text includes the text of every
# property inside it, so 250 nested ones would read the same text 250 times (1 MB took 107
# seconds and 206 MB). The text read for the whole page is limited to the page's length.
WORDS = "toor dal and rice " * 58_000  # about 1 MB
ONE_LINE = " ".join(WORDS.split())
SCOPE = '<div itemscope itemtype="https://schema.org/Recipe">'


def nested_microdata(props: list[str], inner: str, before: str = "") -> str:
    opens = "".join(f'<span itemprop="{props[n % len(props)]}">' for n in range(250))
    return f"{SCOPE}{before}{opens}{inner}{'</span>' * 250}</div>"


class _CountingSet(frozenset[str]):
    """`_SKIP`, counting the elements `_text_of` walks (it asks of each one)."""

    counts: dict[str, int]

    def __contains__(self, tag: object) -> bool:
        self.counts["elements"] += 1
        if self.counts["elements"] > self.counts["limit"]:
            pytest.fail("microdata text walked more elements than the page allows")
        return super().__contains__(tag)


@pytest.fixture
def microdata_read(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Counts the characters of microdata text read, and the elements walked for them, and
    fails the test at once when either passes twice what the page allows (its length, or a
    million for a small page). Without the limit, a nested page passes it at once."""
    counts = {"chars": 0, "elements": 0, "limit": 0}
    real = page_reader._text_of

    def counting(node: Any, *args: Any) -> str:
        text = real(node, *args)
        counts["chars"] += len(text)
        if counts["chars"] > counts["limit"]:
            pytest.fail("microdata read more text than the page allows")
        return text

    monkeypatch.setattr(page_reader, "_text_of", counting)
    skip = _CountingSet(page_reader._SKIP)
    skip.counts = counts
    monkeypatch.setattr(page_reader, "_SKIP", skip)
    return counts


def _read_nested(counts: dict[str, int], html: str, seconds: float = 2) -> PageRecipe:
    counts["limit"] = 2 * max(len(html), 1_000_000)
    start = time.monotonic()
    found_ = read_page(html, URL)
    assert time.monotonic() - start < seconds  # without the limit, minutes
    assert found_ is not None
    return found_


def test_one_property_nested_250_deep_around_1_mb_is_read_once(
    microdata_read: dict[str, int],
) -> None:
    found_ = _read_nested(microdata_read, nested_microdata(["recipeIngredient"], WORDS))
    assert found_.ingredients[0] == PageLine(ONE_LINE)


def test_different_properties_nested_250_deep_around_1_mb_are_read_once(
    microdata_read: dict[str, int],
) -> None:
    props = ["name", "description", "recipeIngredient", "recipeInstructions", "author"]
    before = '<li itemprop="recipeIngredient">2 cups rice</li>'
    found_ = _read_nested(microdata_read, nested_microdata(props, WORDS, before))
    assert found_.name == _cut_words(ONE_LINE, 200)
    assert found_.ingredients[0] == PageLine("2 cups rice")


def test_properties_nested_250_deep_around_100_000_elements_walk_them_a_few_times(
    microdata_read: dict[str, int],
) -> None:
    before = '<li itemprop="recipeIngredient">2 cups rice</li>'
    html = nested_microdata(["recipeIngredient"], "<i></i>" * 100_000, before)
    found_ = _read_nested(microdata_read, html, seconds=5)  # about 0.7 s, counting each one
    assert found_.ingredients == lines("2 cups rice")


def _cut_words(text: str, limit: int) -> str:
    cut = text[: limit - 1]
    return cut[: cut.rfind(" ")] + "…"


def test_the_result_is_frozen() -> None:
    found_ = read()
    with pytest.raises(FrozenInstanceError):
        found_.name = "Changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        found_.ingredients[0].text = "Changed"  # type: ignore[misc]


def test_a_huge_page_still_gives_its_json_ld(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past MAX_NODES the page's tree stops growing (memory), but JSON-LD is still read."""
    monkeypatch.setattr(page_reader, "MAX_NODES", 50)
    padding = "<p>x</p>" * 100
    found_ = read_page(padding + json_ld(recipe(name="Late")), URL)
    assert found_ is not None
    assert found_.name == "Late"
    micro = (
        '<div itemscope itemtype="http://schema.org/Recipe"><b itemprop="name">Micro</b>'
        '<i itemprop="recipeIngredient">1 cup</i></div>'
    )
    assert read_page(micro, URL) is not None
    assert read_page(padding + micro, URL) is None


FIVE_MB = 5 * 1024 * 1024


def test_a_5_mb_name_of_half_tags_is_read_in_linear_time() -> None:
    """2.6 million "<a" with no ">": the old tag pattern started a scan to the end of the text
    at every "<", taking over an hour; read in about a second now."""
    name = "<a" * (FIVE_MB // 2)
    start = time.monotonic()
    found_ = read(name=name)
    assert time.monotonic() - start < 5
    assert found_.name.startswith("<a<a")


def test_one_endless_start_tag_takes_little_memory_or_time() -> None:
    """5 MB of `<a x='` is one start tag of 900,000 attributes. The standard parser used
    506 MB finding where it ends; it now looks no further than MAX_START_TAG."""
    html = "<a x='" * (FIVE_MB // 6)
    tracemalloc.start()
    try:
        start = time.monotonic()
        assert read_page(html, URL) is None
        took = time.monotonic() - start
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert took < 2
    assert peak < 50_000_000
    # The same with an end: many tiny attributes, then ">" past the limit.
    assert read_page(html + ">" + json_ld(recipe(name="After")), URL) is not None


@pytest.mark.parametrize("unit", ["{},", "[],", '{"@id":"#n","a":1},'])
def test_5_mb_of_tiny_json_objects_stays_near_the_pages_size_in_memory(unit: str) -> None:
    """Each parsed object or list costs about 50 times its text: 5 MB of `[{},{},…]` took
    247 MB. A block with more than MAX_JSON_CONTAINERS is skipped before it's parsed, and
    the page's other blocks are still read."""
    tiny = "[" + unit * (FIVE_MB // len(unit)) + "{}]"
    html = f'<script type="application/ld+json">{tiny}</script>' + json_ld(recipe(name="Dal"))
    tracemalloc.start()
    try:
        found_ = read_page(html, URL)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert found_ is not None
    assert found_.name == "Dal"
    assert peak < 2 * len(html)


def test_json_ld_objects_are_counted_across_the_whole_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """The limit is for all the page's blocks together, so many blocks just under it can't add
    up to the same memory; a block that would take the page past it is skipped."""
    monkeypatch.setattr(page_reader, "MAX_JSON_CONTAINERS", 10)
    filler = {"@type": "Thing", "parts": [{}, {}, {}]}  # 5 objects and lists
    assert read_page(json_ld(filler, filler, recipe(name="Late")), URL) is None
    found_ = read_page(json_ld(filler, recipe(name="Fits")), URL)  # 5, then 4
    assert found_ is not None
    assert found_.name == "Fits"


def test_a_start_tag_longer_than_the_limit_is_skipped_and_the_page_still_read() -> None:
    picture = '<img alt="a > b" src="data:image/png;base64,' + "A" * 100_000 + '">'
    micro = (
        '<div itemscope itemtype="http://schema.org/Recipe"><b itemprop="name">Micro</b>'
        '<i itemprop="recipeIngredient">1 cup</i></div>'
    )
    found_ = read_page("<html><body>" + picture + micro + "</body></html>", URL)
    assert found_ is not None
    assert found_.name == "Micro"
    # A long tag that is itself part of the recipe is lost, not misread.
    long_name = '<b itemprop="name" title="' + "x" * 70_000 + '">Long</b>'
    micro_long = micro.replace('<b itemprop="name">Micro</b>', long_name)
    found_ = read_page(micro_long, URL)
    assert found_ is not None
    assert found_.name != "Long"


def test_the_tag_end_pattern_is_the_standard_parsers() -> None:
    """A copy of html.parser's own pattern; this says so if Python's ever changes."""
    standard = getattr(html.parser, "locatetagend")  # noqa: B009 (not in the type stubs)
    assert page_reader._TAG_END.pattern == standard.pattern
    assert page_reader._TAG_END.flags == standard.flags
