"""Pints (0.6; spec section 6, "Reading choices, kept"; cabledrawer 24 and 26 Oct).

A pint is 568 ml in the UK and 473 ml in the US, so "2 pints milk" is read with the
household's own choice (Settings; UK unless it says otherwise). When a recipe comes from a
site that looks American, the review offers to read that one recipe's pints as US pints.

How a US site is told (proposed, for cabledrawer): the site's address is on `US_RECIPE_SITES`, or
the page says its own language is US English (`<html lang="en-US">`). Both are in this one
file so they are easy to change. Nothing is looked up and nothing is sent anywhere.

Quarts, gallons and fluid ounces are not read: they stay in the note, as in 0.5.
"""

from typing import Literal
from urllib.parse import urlsplit

type Pints = Literal["uk", "us"]

PINT_ML: dict[str, int] = {"uk": 568, "us": 473}
DEFAULT_PINTS: Pints = "uk"

# Recipe sites whose pints are US pints. A site is listed by its main address; its sub-domains
# count too ("www.allrecipes.com"). Proposed, for cabledrawer: short on purpose.
US_RECIPE_SITES = (
    "allrecipes.com",
    "foodnetwork.com",
    "simplyrecipes.com",
    "seriouseats.com",
    "epicurious.com",
    "thekitchn.com",
    "delish.com",
    "tasty.co",
    "budgetbytes.com",
    "pinchofyum.com",
    "cookieandkate.com",
    "minimalistbaker.com",
    "loveandlemons.com",
    "damndelicious.net",
    "skinnytaste.com",
    "sallysbakingaddiction.com",
    "kingarthurbaking.com",
    "bonappetit.com",
    "eatingwell.com",
    "food.com",
    "tasteofhome.com",
    "thepioneerwoman.com",
)


def household_pints(value: str | None) -> Pints:
    """The household's choice; anything unknown is the UK pint."""
    return "us" if value == "us" else DEFAULT_PINTS


def looks_american(url: str | None, language: str | None) -> bool:
    """A recipe site that writes US pints: its address is on the list, or the page says
    `en-US`. A page that says another language (`en-GB`) on a listed site is still listed:
    the address is the stronger sign."""
    if url:
        try:
            host = (urlsplit(url).hostname or "").lower().rstrip(".")
        except ValueError:
            host = ""
        if any(host == site or host.endswith(f".{site}") for site in US_RECIPE_SITES):
            return True
    return (language or "").lower() == "en-us"
