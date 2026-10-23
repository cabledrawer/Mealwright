"""The work budget for reading one page (spec section 6, "A work budget for each page"):
the reader runs in a child process that is stopped past its time or memory limit.

The pages here are made up in the test, with `.example` addresses; nothing goes online.
"""

import json
import logging
import multiprocessing
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mealwright import page_budget
from mealwright.page_budget import CANT_READ, PageUnreadable, read_within_budget
from mealwright.page_fetch import MESSAGES, Problem
from mealwright.page_reader import read_page

URL = "https://kitchen.example/recipes/big-dal/"
FIVE_MB = 5 * 1024 * 1024
MB = 1024 * 1024


def realistic_big_page() -> str:
    """A 5 MB page shaped like a big real recipe blog post: stylesheets and scripts in the
    head, a Yoast-style JSON-LD graph with a 200-ingredient, 100-step recipe, a long menu, a
    long article and thousands of comments."""
    site = "https://kitchen.example/"
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": site + "#site", "name": "A kitchen"},
            {"@type": "WebPage", "@id": URL + "#page", "isPartOf": {"@id": site + "#site"}},
            {"@type": "Person", "@id": site + "#cook", "name": "A cook"},
            {
                "@type": "Recipe",
                "@id": URL + "#recipe",
                "name": "Big dal",
                "author": {"@id": site + "#cook"},
                "image": [site + "dal-1x1.jpg", site + "dal-4x3.jpg"],
                "recipeYield": ["8", "8 servings"],
                "prepTime": "PT20M",
                "cookTime": "PT1H10M",
                "totalTime": "PT1H30M",
                "recipeCategory": "Dinner",
                "recipeCuisine": "Indian",
                "nutrition": {
                    "@type": "NutritionInformation",
                    "calories": "320 kcal",
                    "proteinContent": "18 g",
                    "fatContent": "9 g",
                },
                "recipeIngredient": [
                    f"{n % 9 + 1} cups ingredient number {n}, chopped" for n in range(200)
                ],
                "recipeInstructions": [
                    {
                        "@type": "HowToSection",
                        "name": f"Part {part}",
                        "itemListElement": [
                            {"@type": "HowToStep", "text": f"Step {part}.{n}: stir gently."}
                            for n in range(9)
                        ],
                    }
                    for part in range(10)
                ],
            },
        ],
    }
    head = (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Big dal</title>"
        + "".join(f'<link rel=stylesheet href="/s{n}.css">' for n in range(30))
        + "<style>"
        + ".a{color:red;margin:0 auto;padding:1em}\n" * 2000
        + "</style>"
        + '<script type="application/ld+json">'
        + json.dumps(graph)
        + "</script><script>"
        + "window.dataLayer=window.dataLayer||[];function g(){dataLayer.push(arguments)}\n" * 3000
        + "</script></head><body><nav><ul>"
        + "".join(f'<li><a href="/c/{n}">Category {n}</a></li>' for n in range(300))
        + "</ul></nav><article><h1>Big dal</h1>"
        + "".join(
            f"<p>Paragraph {n} about the dal, with <a href='/x{n}'>a link</a> and"
            " <em>some</em> words.</p>"
            for n in range(3000)
        )
        + "</article>"
    )
    comment = (
        "<li class=comment><div class=meta><img src='/a.png' alt=''><b>A reader</b>"
        "<time datetime='2026-01-01'>1 Jan</time></div><p>Lovely recipe, we made it twice"
        " and added more chilli the second time.</p></li>"
    )
    tail = "</ol></body></html>"
    room = FIVE_MB - len(head) - len(tail) - len("<ol>")
    return head + "<ol>" + comment * (room // len(comment)) + tail


def slow_page() -> str:
    """10 MB of plain valid tags, about 5 seconds' reading (twice the slowest 5 MB page)."""
    return "<p>x</p>" * (2 * FIVE_MB // 8)


def greedy_page() -> str:
    """15 MB of words with one emoji in one ingredient, about 500 MB to read (every string
    then takes 4 bytes a character)."""
    words = "😀" + ("word " * (3 * FIVE_MB // 5))
    return (
        '<script type="application/ld+json">{"@type":"Recipe","name":"Dal",'
        '"recipeIngredient":[' + json.dumps(words, ensure_ascii=False) + "]}</script>"
    )


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """The process IDs of the children the budget starts."""
    pids: list[int] = []
    process = page_budget._spawn.Process
    start = process.start

    def recording(self: multiprocessing.process.BaseProcess) -> None:
        start(self)
        assert self.pid is not None
        pids.append(self.pid)

    monkeypatch.setattr(process, "start", recording)
    yield pids


def gone(pid: int) -> bool:
    """True if no process (not even one that ended and wasn't waited for) has this ID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return not Path(f"/proc/{pid}").exists()
    return False


def test_the_realistic_big_page_reads_normally_within_the_real_budget(
    started: list[int],
) -> None:
    html = realistic_big_page()
    assert FIVE_MB - 1000 < len(html.encode()) <= FIVE_MB
    expected = read_page(html, URL)
    assert expected is not None
    assert (expected.name, len(expected.ingredients), len(expected.steps)) == ("Big dal", 200, 100)
    began = time.monotonic()
    assert read_within_budget(html, URL) == expected
    # Well within the budget, and read in a child that has ended.
    assert time.monotonic() - began < page_budget.MAX_SECONDS / 2
    assert len(started) == 1
    assert gone(started[0])


def test_the_budget_has_a_floor() -> None:
    assert page_budget.MAX_SECONDS >= 5
    assert page_budget.MAX_MEMORY >= 256 * MB


def test_a_page_that_would_run_long_is_stopped_at_its_time_limit(
    started: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    html = slow_page()
    began = time.monotonic()
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget(html, URL, seconds=1.0)
    assert time.monotonic() - began < 3
    assert refused.value.reason == "time"
    assert refused.value.message == CANT_READ
    # The connection's plain label and the reason, never the address.
    assert caplog.messages == ["Couldn't read a page: recipe import, over its time limit"]
    assert "kitchen.example" not in caplog.text
    assert len(started) == 1


def test_a_page_that_would_use_too_much_memory_is_stopped_at_its_memory_limit(
    started: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    html = greedy_page()
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget(html, URL, seconds=60, memory=256 * MB)
    assert refused.value.reason == "memory"
    assert caplog.messages == ["Couldn't read a page: recipe import, over its memory limit"]
    assert "kitchen.example" not in caplog.text
    assert len(started) == 1
    assert gone(started[0])


def test_a_stopped_child_leaves_no_process_behind(started: list[int]) -> None:
    with pytest.raises(PageUnreadable):
        read_within_budget(slow_page(), URL, seconds=0.5)
    assert len(started) == 1
    assert gone(started[0])
    assert started[0] not in {child.pid for child in multiprocessing.active_children()}


def test_a_page_with_no_recipe_reads_as_none_within_the_budget() -> None:
    assert read_within_budget("<p>Just a page</p>", URL) is None


def test_the_import_shows_the_budgets_sentence() -> None:
    assert MESSAGES[Problem.CANT_READ] == CANT_READ == PageUnreadable("time").message
    assert CANT_READ == "Couldn’t read that page. Paste the recipe’s text instead."
