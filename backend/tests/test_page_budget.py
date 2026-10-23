"""The work budget for reading one page (spec section 6, "A work budget for each page"):
the reader runs in a child process that is stopped past its time or memory limit.

The pages here are made up in the test, with `.example` addresses; nothing goes online.
"""

import json
import logging
import multiprocessing
import os
import resource
import signal
import socket
import threading
import time
from collections.abc import Iterator
from multiprocessing.connection import Connection
from pathlib import Path

import pytest

from mealwright import page_budget, page_reader
from mealwright.outbound import OutboundBlocked
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
    """10 MB of plain valid tags: twice the slowest 5 MB page found, so twice its time."""
    return "<p>x</p>" * (2 * FIVE_MB // 8)


def greedy_page() -> str:
    """15 MB of words with one emoji in one ingredient: three times the greediest 5 MB page
    found (177 MB), since the emoji makes every character take 4 bytes."""
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
    # Well within the clock's limit, and read in a child that has ended.
    assert time.monotonic() - began < page_budget.MAX_WALL_SECONDS / 2
    assert len(started) == 1
    assert gone(started[0])


def test_the_budget_has_a_floor_and_the_clock_is_the_wider_limit() -> None:
    # The realistic big page needs 1.1 to 1.25 s of processor time on a fast PC (measured 23
    # Oct), so perhaps 5 to 6 s on a Raspberry Pi 4 class board (an estimate, not measured;
    # docs/dev/recipe-import.md): the limit stays more than twice that.
    assert page_budget.MAX_CPU_SECONDS >= 10
    assert page_budget.MAX_WALL_SECONDS > page_budget.MAX_CPU_SECONDS
    # And inside the import's 30 seconds (spec section 6).
    assert page_budget.MAX_WALL_SECONDS <= 20
    assert page_budget.MAX_MEMORY >= 256 * MB


def test_a_page_that_uses_too_much_processor_time_is_stopped_at_its_processor_limit(
    started: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    # The clock's limit is far away, so only the processor limit can stop it. 10 MB of plain
    # tags needs about 7 s of processor time on a fast PC; the limit is 1.
    html = slow_page()
    began = time.monotonic()
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget(html, URL, cpu_seconds=1.0, wall_seconds=60)
    assert time.monotonic() - began < 5
    assert refused.value.reason == "time"
    assert refused.value.message == CANT_READ
    # The connection's plain label and the reason, never the address.
    assert caplog.messages == ["Couldn't read a page: recipe import, over its time limit"]
    assert "kitchen.example" not in caplog.text
    assert len(started) == 1
    assert gone(started[0])


def test_the_clock_stops_a_child_that_the_processor_limit_would_not(
    started: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    # The processor limit is far away (60 s; the page needs about 7), so only the clock and
    # the kill can stop it. Without `child.kill()` the parent would wait for the child to
    # finish by itself, about 7 s, so the bound is far under that.
    html = slow_page()
    began = time.monotonic()
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget(html, URL, cpu_seconds=60, wall_seconds=0.5)
    assert time.monotonic() - began < 1.8
    assert refused.value.reason == "time"
    assert caplog.messages == ["Couldn't read a page: recipe import, over its time limit"]
    assert len(started) == 1
    assert gone(started[0])


def test_a_page_that_would_use_too_much_memory_is_stopped_at_its_memory_limit(
    started: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    html = greedy_page()
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget(html, URL, cpu_seconds=60, wall_seconds=60, memory=256 * MB)
    assert refused.value.reason == "memory"
    assert caplog.messages == ["Couldn't read a page: recipe import, over its memory limit"]
    assert "kitchen.example" not in caplog.text
    assert len(started) == 1
    assert gone(started[0])


# --- Children that behave badly in other ways (#54, round 5, item 26) ------------------------
# Each is a stand-in for `_read_in_child`, defined here so the spawned child can find it again
# (it gets this test file's folder on its path from the parent).


def _crashing_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    page_budget._prepare_child(cpu, memory)
    os.kill(os.getpid(), signal.SIGSEGV)


def _silent_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    page_budget._prepare_child(cpu, memory)
    os._exit(3)


def _unsendable_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    # A result that can't be pickled: the real child code must say "failed", not crash.
    page_reader.read_page = lambda html, url: threading.Lock()  # type: ignore[assignment,return-value]
    page_budget._read_in_child(send, html, url, cpu, memory)


class _Unreadable(Exception):
    """An exception that pickles but can't be unpickled: its message is not its only argument."""

    def __init__(self, message: str, more: str) -> None:
        super().__init__(message)


def _unpicklable_error_child(
    send: Connection, html: str, url: str, cpu: float, memory: int
) -> None:
    page_budget._prepare_child(cpu, memory)
    send.send(("raised", _Unreadable("sent", "back")))
    send.close()


def _lingering_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    page_budget._prepare_child(cpu, memory)
    send.send(("read", None))
    send.close()
    time.sleep(30)  # answered, but doesn't end


def _limits_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    page_budget._prepare_child(cpu, memory)
    send.send(
        (
            "raised",
            ValueError(
                f"core={resource.getrlimit(resource.RLIMIT_CORE)}"
                f" cpu={resource.getrlimit(resource.RLIMIT_CPU)}"
            ),
        )
    )


def _connecting_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    page_budget._prepare_child(cpu, memory)
    try:
        socket.create_connection(("127.0.0.1", int(url)), timeout=2)
    except Exception as error:
        send.send(("raised", error))
    else:
        send.send(("read", None))


@pytest.fixture
def child_as(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def use(target: object) -> None:
        monkeypatch.setattr(page_budget, "_read_in_child", target)

    return use


@pytest.mark.parametrize("target", [_crashing_child, _silent_child])
def test_a_child_that_dies_without_answering_is_a_crash_not_memory(
    child_as, target: object, caplog: pytest.LogCaptureFixture, started: list[int]
) -> None:
    child_as(target)
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget("<p>x</p>", URL)
    assert refused.value.reason == "crash"
    assert refused.value.message == CANT_READ
    assert caplog.messages == ["Couldn't read a page: recipe import, the reader stopped"]
    assert gone(started[0])


def test_a_result_that_cannot_be_sent_is_unreadable_not_a_runtime_error(
    child_as, caplog: pytest.LogCaptureFixture
) -> None:
    child_as(_unsendable_child)
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget("<p>x</p>", URL)
    assert refused.value.reason == "crash"
    assert caplog.messages == ["Couldn't read a page: recipe import, the reader stopped"]


def test_an_error_from_the_child_that_cannot_be_unpickled_is_unreadable_not_that_error(
    child_as, caplog: pytest.LogCaptureFixture, started: list[int]
) -> None:  # type: ignore[no-untyped-def]
    child_as(_unpicklable_error_child)
    with caplog.at_level(logging.WARNING), pytest.raises(PageUnreadable) as refused:
        read_within_budget("<p>x</p>", URL)
    assert refused.value.reason == "crash"
    assert refused.value.message == CANT_READ
    assert caplog.messages == ["Couldn't read a page: recipe import, the reader stopped"]
    assert gone(started[0])


def test_a_child_that_answers_but_does_not_end_is_killed_after_a_moment(
    child_as, monkeypatch: pytest.MonkeyPatch, started: list[int]
) -> None:
    child_as(_lingering_child)
    monkeypatch.setattr(page_budget, "_EXIT_SECONDS", 0.5)
    began = time.monotonic()
    assert read_within_budget("<p>x</p>", URL) is None
    # Without the wait's limit, the parent would sit there for the child's 30 seconds.
    assert time.monotonic() - began < 3
    assert gone(started[0])


def test_the_child_cannot_write_a_core_file(child_as) -> None:
    child_as(_limits_child)
    with pytest.raises(ValueError, match=r"core=\(0, 0\)"):
        read_within_budget("<p>x</p>", URL)


def test_a_connection_from_the_child_is_refused_by_the_network_guard(child_as) -> None:
    # The child starts fresh, so it has only the guard it switches on itself. A listening
    # socket here would see a connection if the guard let one through.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        listener.settimeout(0.1)
        child_as(_connecting_child)
        with pytest.raises(OutboundBlocked):
            read_within_budget("<p>x</p>", str(port))
        with pytest.raises(TimeoutError):  # nothing ever arrived
            listener.accept()


def test_a_stopped_child_leaves_no_process_behind(started: list[int]) -> None:
    with pytest.raises(PageUnreadable):
        read_within_budget(slow_page(), URL, cpu_seconds=60, wall_seconds=0.5)
    assert len(started) == 1
    assert gone(started[0])
    assert started[0] not in {child.pid for child in multiprocessing.active_children()}


def test_a_page_with_no_recipe_reads_as_none_within_the_budget() -> None:
    assert read_within_budget("<p>Just a page</p>", URL) is None


def test_the_import_shows_the_budgets_sentence() -> None:
    assert MESSAGES[Problem.CANT_READ] == CANT_READ == PageUnreadable("time").message
    assert CANT_READ == "Couldn’t read that page. Paste the recipe’s text instead."


# --- Two pages at a time (cabledrawer 23 Oct, question 22) ---------------------------------------


def _holding_child(send: Connection, html: str, url: str, cpu: float, memory: int) -> None:
    """Holds its place for `url` seconds, then answers."""
    page_budget._prepare_child(cpu, memory)
    time.sleep(float(url))
    send.send(("read", None))
    send.close()


def _in_threads(count: int, hold: float, **options: float) -> list[object]:
    """Read `count` pages at once, each holding its place for `hold` seconds; what each
    gives back (None, or the error raised), with when it ended."""
    results: list[object] = [None] * count
    ended: list[float] = [0.0] * count

    def one(index: int) -> None:
        try:
            read_within_budget("<p>x</p>", str(hold), **options)
        except PageUnreadable as error:
            results[index] = error
        ended[index] = time.monotonic()

    threads = [threading.Thread(target=one, args=(i,)) for i in range(count)]
    began = time.monotonic()
    for thread in threads:
        thread.start()
        time.sleep(0.05)  # in order: the third is the last to ask
    for thread in threads:
        thread.join()
    results.append([end - began for end in ended])
    return results


def test_two_pages_are_read_at_once(child_as) -> None:  # type: ignore[no-untyped-def]
    assert page_budget.MAX_AT_ONCE == 2
    child_as(_holding_child)
    *results, ends = _in_threads(2, 2.0)
    assert results == [None, None]
    # Both ran together: about 2.x seconds in all, not 4.
    assert max(ends) < 3.8


def test_a_third_page_waits_its_turn_and_then_runs(child_as) -> None:  # type: ignore[no-untyped-def]
    child_as(_holding_child)
    *results, ends = _in_threads(3, 1.5)
    assert results == [None, None, None]
    # The third could only start when one of the first two was done.
    assert max(ends) > 3.0


def test_a_third_page_whose_wait_would_pass_its_limit_is_told_mealwright_is_busy(
    child_as, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    child_as(_holding_child)
    with caplog.at_level(logging.WARNING):
        *results, ends = _in_threads(3, 3.0, wait_seconds=0.5)
    assert results[:2] == [None, None]
    busy = results[2]
    assert isinstance(busy, page_budget.PageBusy)
    assert (
        busy.message
        == page_budget.BUSY
        == "Mealwright is busy reading another page. Try again in a moment."
    )
    assert MESSAGES[Problem.BUSY] == page_budget.BUSY
    assert "busy with other pages" in caplog.text
    assert ends[2] < 1.5  # it gave up at its wait, it didn't wait for the others


def test_a_failed_or_over_budget_read_gives_its_place_back(child_as) -> None:  # type: ignore[no-untyped-def]
    # Four reads that fail one after another, then two that need both places at once: if a
    # failed read kept its place, the last two would be refused.
    child_as(_crashing_child)
    for _ in range(3):
        with pytest.raises(PageUnreadable):
            read_within_budget("<p>x</p>", URL)
    with pytest.raises(PageUnreadable):
        read_within_budget(slow_page(), URL, cpu_seconds=60, wall_seconds=0.3)
    child_as(_holding_child)
    *results, _ = _in_threads(2, 0.5, wait_seconds=0.2)
    assert results == [None, None]


# --- The import's 30 seconds (cabledrawer 22 Oct, question 12) -----------------------------------


def test_the_reads_clock_is_cut_to_what_the_import_has_left(
    monkeypatch: pytest.MonkeyPatch, started: list[int]
) -> None:
    monkeypatch.setattr(page_budget, "MIN_READ_SECONDS", 0.2)
    began = time.monotonic()
    with pytest.raises(PageUnreadable) as over:
        # Plenty of processor time and the usual 15 s clock; only the import's time is short.
        read_within_budget(slow_page(), URL, cpu_seconds=60, within_seconds=1.0)
    assert over.value.reason == "time"
    assert time.monotonic() - began < 2.5  # not the 15 s clock
    assert gone(started[0])


def test_a_read_that_waited_for_a_place_and_has_too_little_time_left_is_told_busy(
    child_as, monkeypatch: pytest.MonkeyPatch, started: list[int], caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    child_as(_holding_child)
    monkeypatch.setattr(page_budget, "MIN_READ_SECONDS", 0.6)
    holders = [
        threading.Thread(target=read_within_budget, args=("<p>x</p>", "1.0")) for _ in range(2)
    ]
    for holder in holders:
        holder.start()
    time.sleep(0.2)  # both places are taken
    began = time.monotonic()
    with caplog.at_level(logging.WARNING), pytest.raises(page_budget.PageBusy):
        # A place frees at about 1 s, which leaves under the 0.6 s a read needs.
        read_within_budget("<p>x</p>", "0", within_seconds=1.3)
    assert time.monotonic() - began < 1.6
    assert "busy with other pages" in caplog.text
    for holder in holders:
        holder.join()
    # And it gave nothing back twice: both places are still there for two reads at once.
    *results, _ = _in_threads(2, 0.3, wait_seconds=0.5)
    assert results == [None, None]
    assert len(started) == 2 + 2  # the busy read never started a child


def test_a_child_that_answered_is_not_given_more_time_than_the_import_has(
    child_as, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    child_as(_lingering_child)
    monkeypatch.setattr(page_budget, "_EXIT_SECONDS", 20.0)
    monkeypatch.setattr(page_budget, "MIN_READ_SECONDS", 0.2)
    began = time.monotonic()
    assert read_within_budget("<p>x</p>", URL, within_seconds=1.5) is None
    assert time.monotonic() - began < 3  # not the 20 s of waiting for it to end
