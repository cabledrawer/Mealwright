"""Importing a recipe: the one box, the review, and Save (spec section 6, "Recipe import,
decided for 0.5"). The web is faked: no test goes online. The page fetch and the photo
download are replaced by pages and pictures made here; the rest (the switches, the reader, the
matching, the database, Save and Undo) is the real thing."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import photo_kit as kit
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import ok, person
from test_recipes import food

from mealwright import page_budget, page_fetch, page_reader, photos
from mealwright.models import (
    Change,
    Food,
    FoodName,
    Place,
    Recipe,
    RecipePhoto,
)
from mealwright.outbound import Connection, set_switch
from mealwright.page_fetch import FetchedPage, FetchRefused, Problem

API = "/api/v1"
PAGES = Path(__file__).parent / "import_pages"
LINK = "https://bananaleaf.example/vendakkai-poriyal/"


def page_text(name: str = "south_indian_blog.html") -> str:
    return (PAGES / name).read_text(encoding="utf-8")


class Web:
    """A pretend web: which pages and photos it has, and what was asked of it."""

    def __init__(self) -> None:
        self.pages: dict[str, str | FetchRefused | Exception] = {}
        self.photo: bytes | FetchRefused | Exception | None = None
        self.asked: list[str] = []
        self.photos_asked: list[str] = []

    def fetch_page(self, gate: Any, household_id: int, url: str, **_: Any) -> FetchedPage:
        self.asked.append(url)
        gate.check_switch(household_id, Connection.RECIPE_IMPORT)
        found = self.pages.get(url)
        if isinstance(found, FetchRefused | Exception):
            raise found
        if found is None:
            raise FetchRefused(Problem.CANT_REACH)
        return FetchedPage(url=url, html=found)

    def download_photo(self, gate: Any, household_id: int, url: str, **_: Any) -> photos.Cleaned:
        self.photos_asked.append(url)
        if self.photo is None:
            raise FetchRefused(Problem.CANT_REACH)
        if isinstance(self.photo, FetchRefused | Exception):
            raise self.photo
        return photos.clean(self.photo)


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> Web:
    pretend = Web()
    pretend.pages[LINK] = page_text()
    monkeypatch.setattr(page_fetch, "fetch_page", pretend.fetch_page)
    monkeypatch.setattr(page_fetch, "download_photo", pretend.download_photo)

    # Reading goes through the budget; here it is read in this process (the budget has its own
    # tests in test_page_budget.py) so these tests stay fast.
    def read(html: str, url: str, **_: Any) -> Any:
        return page_reader.read_page(html, url)

    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", read)
    return pretend


def switch(client: TestClient, connection: Connection, on: bool = True) -> None:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        set_switch(db, 1, connection, on)
        db.commit()


@pytest.fixture
def links_on(kitchen: TestClient) -> TestClient:
    switch(kitchen, Connection.RECIPE_IMPORT)
    return kitchen


def start(client: TestClient, text: str, **fields: Any) -> Any:
    return client.post(f"{API}/recipes/import", json={"text": text, **fields})


def review(client: TestClient, text: str, **fields: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(start(client, text, **fields))
    return found


def counts(client: TestClient) -> tuple[int, int, int]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return (
            db.scalar(select(func.count()).select_from(Recipe)) or 0,
            db.scalar(select(func.count()).select_from(Food)) or 0,
            db.scalar(select(func.count()).select_from(FoodName)) or 0,
        )


def cupboard(client: TestClient) -> int:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return db.scalars(select(Place.id).where(Place.name == "Cupboard")).first() or 0


def to_save(
    shown: dict[str, Any], links: dict[int, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """What the screen sends back: the review's recipe and each line, with the choices made."""
    links = links or {}
    lines = []
    for index, line in enumerate(shown["lines"]):
        body: dict[str, Any] = {
            "kind": line["kind"],
            "words": line["words"],
            "amount": line["amount"],
            "unit": line["unit"],
            "size_id": line["size"]["id"] if line["size"] else None,
            "note": line["note"],
        }
        if index in links:
            body["link"] = links[index]
        elif line["label"] in ("matched", "staple"):
            body["link"] = {"kind": "ingredient", "food_id": line["food"]["id"]}
        lines.append(body)
    return {
        "name": shown["name"],
        "description": shown["description"],
        "time_minutes": shown["time_minutes"],
        "serves": shown["serves"],
        "makes": shown["makes"],
        "tags": shown["tags"],
        "nutrition": shown["nutrition"],
        "lines": lines,
        "steps": shown["steps"],
        "source_url": shown["source"]["url"],
        "source_author": shown["author"],
        "photo_id": shown["photo"]["photo"]["id"] if shown["photo"]["photo"] else None,
    }


def save(client: TestClient, body: dict[str, Any], **headers: str) -> Any:
    return client.post(f"{API}/recipes/import/save", json=body, headers=headers)


PASTED = """Sambar
Ingredients
1 cup thuvaram paruppu
2-3 green chillies, slit
1 red onion, sliced
1/4 tsp asafoetida
a sprig of curry leaves
salt to taste
Method
1. Boil the dal.
2. Add the rest.
Tips
Use fresh curry leaves.
Serve hot.
"""


@pytest.fixture
def pantry(kitchen: TestClient) -> dict[str, dict[str, Any]]:
    dal = food(kitchen, "Toor dal", counted_as="weight")
    other = {"name": "thuvaram paruppu"}
    ok(kitchen.post(f"{API}/foods/{dal['id']}/other-names", json=other), 201)
    return {
        "Toor dal": dal,
        "Onions": food(kitchen, "Onions", counted_as="count"),
        "Green chillies": food(kitchen, "Green chillies", counted_as="count"),
        "Salt": food(kitchen, "Salt", staple=True),
    }


# --- The one box ------------------------------------------------------------------------------


def test_pasted_text_works_with_the_link_switch_off_and_saves_nothing(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    before = counts(kitchen)
    shown = review(kitchen, PASTED)
    assert web.asked == []  # nothing went online
    assert shown["source"] == {"kind": "text", "url": None, "site": None}
    assert shown["name"] == "Sambar"
    assert shown["lines"][0]["written"] == "1 cup thuvaram paruppu"
    assert shown["photo"]["state"] == "none"
    assert [step["text"] for step in shown["steps"]] == ["Boil the dal.", "Add the rest."]
    assert shown["left_out"] == [{"heading": "Tips", "lines": 2}]
    assert counts(kitchen) == before  # nothing is saved until Save


def test_each_line_has_a_label_and_the_counts_add_up(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    by_written = {line["written"]: line for line in shown["lines"]}
    dal = by_written["1 cup thuvaram paruppu"]
    assert dal["label"] == "matched"
    assert dal["food"]["name"] == "Toor dal"
    assert dal["matched_by"] == "thuvaram paruppu"
    chillies = by_written["2-3 green chillies, slit"]
    assert chillies["label"] == "matched" and chillies["amount"] == 3
    assert chillies["note"] == "as written: 2-3 green chillies, slit"  # picked from two numbers
    onion = by_written["1 red onion, sliced"]
    assert onion["label"] == "to_confirm"
    assert onion["food"]["name"] == "Onions"  # the best guess
    assert onion["learn_name"] == "red onion"
    assert onion["new_ingredient"]["name"] == "Red onion"
    assert onion["new_ingredient"]["counted_as"] == "count"
    assert onion["new_ingredient"]["place"]["name"] == "Cupboard"
    asafoetida = by_written["1/4 tsp asafoetida"]
    assert asafoetida["label"] == "needs_you"
    assert asafoetida["new_ingredient"]["counted_as"] == "volume"
    sprig = by_written["a sprig of curry leaves"]
    assert sprig["label"] == "needs_you"
    assert (
        sprig["amount"] is None and sprig["note"] == "1 sprig"
    )  # a count that means something else
    salt = by_written["salt to taste"]
    assert salt["label"] == "staple" and salt["counts"] is False
    assert shown["counts"] == {"matched": 2, "to_confirm": 1, "needs_you": 2, "staple": 1}


def test_nothing_given_and_no_recipe_in_text(kitchen: TestClient, web: Web) -> None:
    response = start(kitchen, "   ")
    assert response.status_code == 422 and response.json()["code"] == "nothing_given"
    response = start(kitchen, "Hello there, this is not a recipe at all.")
    assert response.status_code == 422 and response.json()["code"] == "no_recipe"
    assert "Paste its title, ingredients and method" in response.json()["detail"]


def test_text_over_100000_characters_gets_its_sentence(kitchen: TestClient, web: Web) -> None:
    response = start(kitchen, "word " * 30_000)
    assert response.status_code == 422 and response.json()["code"] == "text_too_long"
    assert response.json()["detail"].startswith("That text is longer than 100,000 characters.")


# --- A link ----------------------------------------------------------------------------------


def test_a_link_with_the_switch_off_is_refused_and_nothing_is_fetched(
    kitchen: TestClient, web: Web
) -> None:
    response = start(kitchen, LINK)
    assert response.status_code == 403
    assert response.json()["code"] == "import_switched_off"
    assert response.json()["detail"] == "Importing from links is switched off"
    assert response.json()["admin"] is True
    assert counts(kitchen) == (0, 0, 0)


def test_a_member_is_told_an_admin_can_switch_it_on(kitchen: TestClient, web: Web) -> None:
    wren = person(kitchen)
    response = start(wren, LINK)
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Importing from links is switched off. An admin can switch it on."
    )
    assert response.json()["admin"] is False
    assert web.asked == []


def test_a_link_gives_the_review_with_the_pages_recipe(
    links_on: TestClient, web: Web, pantry: dict[str, dict[str, Any]]
) -> None:
    shown = review(links_on, LINK)
    assert web.asked == [LINK]
    assert shown["source"] == {"kind": "link", "url": LINK, "site": "bananaleaf.example"}
    assert shown["name"].startswith("Vendakkai Poriyal")
    assert shown["author"] == "Meena Raman"
    assert shown["time_minutes"] == 30
    assert shown["serves"] == 3
    assert shown["tags"] == ["Side", "South Indian", "Tamil Nadu"]  # "Side dish" is "Side"
    headings = [line["words"] for line in shown["lines"] if line["kind"] == "heading"]
    assert headings == ["For the poriyal", "For the tadka", "To finish"]
    assert shown["steps"][0] == {
        "kind": "heading",
        "text": "Tadka",
        "optional": False,
        "wait": None,
        "wait_confirmed": False,
    }
    # Matched to what the household has; the rest need a choice.
    labels = {line["written"][:12]: line["label"] for line in shown["lines"] if line["label"]}
    assert labels["1 small onio"] == "matched"  # "small" is a prep word: Onions
    assert counts(links_on) == (0, 4, 1)  # nothing saved: only the pantry's own


def test_the_photo_is_not_downloaded_while_its_switch_is_off(
    links_on: TestClient, web: Web
) -> None:
    web.photo = kit.jpeg()
    shown = review(links_on, LINK)
    assert shown["photo"] == {"state": "off", "photo": None, "message": "Photo not downloaded"}
    assert web.photos_asked == []


def test_the_main_photo_waits_until_save_and_goes_on_the_recipe(
    links_on: TestClient, web: Web
) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.jpeg(1200, 900)
    shown = review(links_on, LINK)
    assert shown["photo"]["state"] == "downloaded"
    assert web.photos_asked == [
        "https://bananaleaf.example/wp-content/uploads/vendakkai-poriyal.jpg"
    ]
    photo = shown["photo"]["photo"]
    assert links_on.get(photo["url"]).status_code == 200  # the review can show it
    with links_on.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        waiting = db.scalars(select(RecipePhoto)).all()
        assert [(p.recipe_id, p.id) for p in waiting] == [(None, photo["id"])]
    saved = ok(save(links_on, to_save(shown)), 201)
    recipe = ok(links_on.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert recipe["photo"]["id"] == photo["id"]


def test_f92_ten_reads_then_discarding_them_frees_the_eleventh(
    links_on: TestClient, web: Web
) -> None:
    """F92: the Check screen's Discard deletes its waiting photo (DELETE /recipes/photos/<id>), so
    ten reads that were never saved don't block the next one."""
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.jpeg(1200, 900)
    shown = [review(links_on, LINK, again=True) for _ in range(10)]
    assert all(each["photo"]["state"] == "downloaded" for each in shown)
    blocked = review(links_on, LINK, again=True)
    assert blocked["photo"]["state"] == "failed"
    assert blocked["photo"]["message"] == photos.TOO_MANY_WAITING
    for each in shown:
        assert (
            links_on.delete(f"{API}/recipes/photos/{each['photo']['photo']['id']}").status_code
            == 204
        )
    again = review(links_on, LINK, again=True)
    assert again["photo"]["state"] == "downloaded"
    with links_on.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert len(db.scalars(select(RecipePhoto)).all()) == 1


def test_a_photo_that_cannot_be_had_never_stops_the_import(links_on: TestClient, web: Web) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = FetchRefused(Problem.PHOTO_TOO_BIG)
    shown = review(links_on, LINK)
    assert shown["photo"]["state"] == "failed"
    assert shown["photo"]["message"] == "That photo is bigger than 15 MB."
    web.photo = None  # the site doesn't answer
    assert review(links_on, LINK)["photo"]["state"] == "failed"


@pytest.mark.parametrize(
    ("problem", "code", "sentence"),
    [
        (Problem.NOT_A_PAGE, "not_a_page", "This link isn’t a web page."),
        (Problem.PAGE_TOO_BIG, "page_too_big", "That page is bigger than 5 MB."),
        (Problem.OWN_NETWORK, "own_network", "That link is on your own network."),
        (Problem.TIMEOUT, "timeout", "That site took too long to answer. Try again later."),
        (Problem.CANT_REACH, "cant_reach", "Couldn’t reach that site."),
        (Problem.BAD_LINK, "bad_link", "That doesn’t look like a web link."),
    ],
)
def test_a_refused_fetch_reaches_the_screen_as_its_sentence(
    links_on: TestClient, web: Web, problem: Problem, code: str, sentence: str
) -> None:
    web.pages[LINK] = FetchRefused(problem)
    response = start(links_on, LINK)
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert response.json()["detail"].startswith(sentence)
    assert counts(links_on) == (0, 0, 0)


@pytest.mark.parametrize("problem", [Problem.ALWAYS_BLOCKED, Problem.OWN_NETWORK, Problem.ODD_PORT])
def test_a_member_gets_one_code_for_every_network_refusal(
    links_on: TestClient, web: Web, problem: Problem
) -> None:
    web.pages[LINK] = FetchRefused(problem)
    answer = start(person(links_on), LINK)
    assert answer.status_code == 422
    assert answer.json()["code"] == "cant_open_link"
    assert answer.json()["detail"].startswith("Mealwright can’t open that link.")
    assert start(links_on, LINK).json()["code"] == problem.value  # an admin keeps the reason


@pytest.mark.parametrize("problem", [Problem.ALWAYS_BLOCKED, Problem.OWN_NETWORK, Problem.ODD_PORT])
def test_a_members_photo_says_one_thing_for_every_network_refusal(
    links_on: TestClient, web: Web, problem: Problem
) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = FetchRefused(problem)
    member = review(person(links_on), LINK)["photo"]
    assert member["state"] == "failed"
    assert member["message"].startswith("Mealwright can’t open that link.")
    admin = review(links_on, LINK, again=True)["photo"]
    assert (
        admin["message"] != member["message"] and admin["message"] == FetchRefused(problem).message
    )


def test_an_error_the_fetch_did_not_expect_is_a_sentence_and_the_log_has_no_address(
    links_on: TestClient, web: Web, caplog: pytest.LogCaptureFixture
) -> None:
    web.pages[LINK] = ValueError("netloc 'secret-host.example' is not valid")
    with caplog.at_level(logging.DEBUG):
        response = start(links_on, LINK)
    assert response.status_code == 422
    assert response.json()["code"] == "cant_reach"
    assert response.json()["detail"].startswith("Couldn’t reach that site.")
    assert "secret-host" not in caplog.text and "bananaleaf" not in caplog.text
    assert "recipe import, ValueError" in caplog.text
    assert counts(links_on) == (0, 0, 0)


def test_an_error_the_photo_download_did_not_expect_only_drops_the_photo(
    links_on: TestClient, web: Web, caplog: pytest.LogCaptureFixture
) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = ValueError("netloc 'secret-host.example' is not valid")
    with caplog.at_level(logging.DEBUG):
        shown = review(links_on, LINK)
    assert shown["name"].startswith("Vendakkai Poriyal")  # the import went on
    assert shown["photo"]["state"] == "failed"
    assert shown["photo"]["message"].startswith("Couldn’t reach that site.")
    assert "secret-host" not in caplog.text and "bananaleaf" not in caplog.text
    assert "recipe photos, ValueError" in caplog.text


def test_a_photo_whose_commit_fails_and_whose_files_cannot_be_deleted_still_shows_the_first_error(
    links_on: TestClient,
    web: Web,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """0.5 PR 7 review L2: the clean-up after a failed commit can't hide the error that started
    it, and its own failure logs only the kind of error, never a path."""
    from sqlalchemy.orm import Session

    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.png()
    written: list[bool] = []
    real_write, real_commit = photos.write, Session.commit

    def write(*args: Any, **kwargs: Any) -> int:
        written.append(True)
        return real_write(*args, **kwargs)

    def commit(self: Session) -> None:
        if written:
            raise RuntimeError("the disk is full")
        real_commit(self)

    def unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(f"cannot delete {self}")

    monkeypatch.setattr(photos, "write", write)
    monkeypatch.setattr(Session, "commit", commit)
    monkeypatch.setattr(Path, "unlink", unlink)
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError, match="the disk is full"):
        review(links_on, LINK)
    assert "PermissionError" in caplog.text
    assert "cannot delete" not in caplog.text and ".jpg" not in caplog.text


@pytest.mark.parametrize("bad", ["http://[abc", "http://secret\u2100host.example/"])
def test_a_bad_redirect_on_the_page_or_the_photo_never_leaks_an_error_or_an_address(
    links_on: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    bad: str,
) -> None:
    """The real fetch (the answers from the web are made here): a redirect to an address
    Python can't take apart. The page: a sentence. The photo: only the photo is dropped."""
    from mealwright.outbound import OutboundResponse

    switch(links_on, Connection.RECIPE_PHOTOS)
    answers = {
        "page": OutboundResponse(200, {"Content-Type": "text/html"}, page_text().encode(), LINK),
        "redirect": OutboundResponse(302, {"Location": bad}, b"", LINK),
    }

    def hop(gate: Any, household: int, url: str, kinds: Any, *_: Any) -> OutboundResponse:
        return (
            answers["page"]
            if kinds.connection is Connection.RECIPE_IMPORT and "poriyal" in url
            else answers["redirect"]
        )

    monkeypatch.setattr(page_fetch, "_one_hop", hop)
    with caplog.at_level(logging.DEBUG):
        shown = review(links_on, LINK)
        assert shown["photo"]["state"] == "failed"
        redirect_only = OutboundResponse(302, {"Location": bad}, b"", LINK)
        answers["page"] = redirect_only
        response = start(links_on, LINK)
    assert (response.status_code, response.json()["code"]) == (422, "bad_link")
    assert "secret" not in caplog.text and "[abc" not in caplog.text
    assert "bananaleaf" not in caplog.text


def test_a_bad_link_never_reaches_the_web(links_on: TestClient, web: Web) -> None:
    for text in ("ftp://example.test/x", "http://", "https://user:pw@kitchen.example/"):
        response = start(links_on, text)
        assert response.status_code == 422 and response.json()["code"] == "bad_link", text
    assert web.asked == []


def test_a_page_with_no_recipe_says_so_and_offers_pasted_text(
    links_on: TestClient, web: Web
) -> None:
    web.pages[LINK] = page_text("no_recipe.html")
    response = start(links_on, LINK)
    assert response.status_code == 422
    assert response.json()["code"] == "no_recipe"
    assert response.json()["detail"].endswith("Paste the recipe’s text instead.")


def test_a_page_over_its_budget_or_that_breaks_the_reader_is_the_same_plain_sentence(
    links_on: TestClient,
    web: Web,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentence = "Couldn’t read that page. Paste the recipe’s text instead."
    for error in (page_budget.PageUnreadable("time"), page_budget.PageUnreadable("memory")):

        def over(html: str, url: str, error: Exception = error, **_: Any) -> Any:
            raise error

        monkeypatch.setattr("mealwright.recipe_import.read_within_budget", over)
        response = start(links_on, LINK)
        assert response.status_code == 422
        assert (response.json()["code"], response.json()["detail"]) == ("cant_read", sentence)

    # Anything else the reader raises (a bug, a number that won't convert) is the same sentence:
    # never a stack trace, and the log has the kind of error only, never the address.
    def breaks(html: str, url: str, **_: Any) -> Any:
        raise ArithmeticError(f"could not read {url}")

    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", breaks)
    with caplog.at_level(logging.WARNING):
        response = start(links_on, LINK)
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["detail"]) == ("cant_read", sentence)
    assert "bananaleaf" not in caplog.text
    assert "recipe import, ArithmeticError" in caplog.text


def test_a_busy_reader_says_so(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    def busy(html: str, url: str, **_: Any) -> Any:
        raise page_budget.PageBusy

    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", busy)
    response = start(links_on, LINK)
    assert response.json()["code"] == "busy"
    assert response.json()["detail"] == (
        "Mealwright is busy reading another page. Try again in a moment."
    )


def test_the_wait_for_a_place_counts_within_the_imports_30_seconds(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[float] = []

    def read(html: str, url: str, *, within_seconds: float, **_: Any) -> Any:
        seen.append(within_seconds)
        return page_reader.read_page(html, url)

    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", read)
    review(links_on, LINK)
    assert 0 < seen[0] <= 30


def test_the_fetch_is_given_what_is_left_of_the_30_seconds(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[float | None] = []
    real = web.fetch_page

    def fetch(gate: Any, household_id: int, url: str, *, seconds: float | None = None) -> Any:
        given.append(seconds)
        return real(gate, household_id, url)

    monkeypatch.setattr(page_fetch, "fetch_page", fetch)
    review(links_on, LINK)
    assert given[0] is not None and 29 < given[0] <= 30


class Clock:
    """Stands in for the import's clock: time only passes when a test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr("mealwright.recipe_import._now", clock)
    return clock


def test_a_fetch_that_uses_the_time_the_read_needs_ends_the_import_with_the_timeout_sentence(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    real = web.fetch_page
    read: list[object] = []

    def slow(gate: Any, household_id: int, url: str, **options: Any) -> Any:
        clock.now += 29  # the site took 29 of the 30 seconds
        return real(gate, household_id, url)

    def reader(html: str, url: str, **options: Any) -> Any:
        read.append(options)
        return page_reader.read_page(html, url)

    monkeypatch.setattr(page_fetch, "fetch_page", slow)
    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", reader)
    response = start(links_on, LINK)
    assert (response.status_code, response.json()["code"]) == (422, "timeout")
    assert response.json()["detail"].startswith("That site took too long to answer.")
    assert read == []  # nothing was read
    assert counts(links_on) == (0, 0, 0)


def test_the_read_is_given_only_what_the_fetch_left_and_the_photo_only_what_the_read_left(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.png()
    real = web.fetch_page
    given: dict[str, float | None] = {}

    def fetch(gate: Any, household_id: int, url: str, *, seconds: float | None = None) -> Any:
        given["fetch"] = seconds
        clock.now += 12
        return real(gate, household_id, url)

    def reader(html: str, url: str, *, within_seconds: float, **_: Any) -> Any:
        given["read"] = within_seconds
        clock.now += within_seconds + 1  # it uses all it has, and a little more
        return page_reader.read_page(html, url)

    monkeypatch.setattr(page_fetch, "fetch_page", fetch)
    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", reader)
    shown = review(links_on, LINK)
    assert given["fetch"] == 30
    assert given["read"] == 18  # 30 - the fetch's 12
    # No time left for the photo: it is not asked for, and the review says why.
    assert web.photos_asked == []
    assert shown["photo"]["state"] == "failed"
    assert shown["photo"]["message"] == "That site took too long to answer. Try again later."


def test_whatever_the_fetch_and_the_read_use_the_import_never_asks_for_more_than_30_seconds(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """A slow site then a slow reading place: every time the import hands out is within what
    is left, so the total can't pass the 30 seconds."""
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = FetchRefused(Problem.CANT_REACH)
    real_fetch, real_photo = web.fetch_page, web.download_photo
    asked: list[tuple[str, float]] = []

    def fetch(gate: Any, household_id: int, url: str, *, seconds: float | None = None) -> Any:
        asked.append(("fetch", seconds or 0))
        clock.now += 14
        return real_fetch(gate, household_id, url)

    def photo(gate: Any, household_id: int, url: str, *, seconds: float | None = None) -> Any:
        asked.append(("photo", seconds or 0))
        return real_photo(gate, household_id, url)

    def reader(html: str, url: str, *, within_seconds: float, **_: Any) -> Any:
        asked.append(("read", within_seconds))
        clock.now += 10  # waiting and reading
        return page_reader.read_page(html, url)

    monkeypatch.setattr(page_fetch, "fetch_page", fetch)
    monkeypatch.setattr(page_fetch, "download_photo", photo)
    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", reader)
    review(links_on, LINK)
    spent = 0.0
    for what, seconds in asked:
        assert seconds <= 30 - spent + 1e-6, what
        spent += {"fetch": 14, "read": 10, "photo": 0}[what]
    assert [what for what, _ in asked] == ["fetch", "read", "photo"]
    assert asked[-1][1] == 6  # 30 - 14 - 10


def test_no_database_connection_is_held_open_while_the_page_is_fetched_read_or_the_photo_downloaded(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.png()
    pool = links_on.app.state.sessionmaker.kw["bind"].pool  # type: ignore[attr-defined]
    open_during: dict[str, int] = {}
    fetch, photo = web.fetch_page, web.download_photo

    def fetching(gate: Any, household_id: int, url: str, **options: Any) -> Any:
        open_during["fetch"] = pool.checkedout()
        return fetch(gate, household_id, url)

    def reading(html: str, url: str, **_: Any) -> Any:
        open_during["read"] = pool.checkedout()
        return page_reader.read_page(html, url)

    def downloading(gate: Any, household_id: int, url: str, **options: Any) -> Any:
        open_during["photo"] = pool.checkedout()
        return photo(gate, household_id, url)

    monkeypatch.setattr(page_fetch, "fetch_page", fetching)
    monkeypatch.setattr(page_fetch, "download_photo", downloading)
    monkeypatch.setattr("mealwright.recipe_import.read_within_budget", reading)
    review(links_on, LINK)
    assert open_during == {"fetch": 0, "read": 0, "photo": 0}


def test_the_real_budget_reads_the_page_in_a_child(links_on: TestClient) -> None:
    """One import through the real budget (a child process), with the fetch faked."""
    web = Web()
    web.pages[LINK] = page_text()
    mp = pytest.MonkeyPatch()
    mp.setattr(page_fetch, "fetch_page", web.fetch_page)
    try:
        shown = review(links_on, LINK)
    finally:
        mp.undo()
    assert shown["name"].startswith("Vendakkai Poriyal")


# --- The same link twice ----------------------------------------------------------------------


def test_the_same_link_twice_offers_open_it_or_import_again_as_a_copy(
    links_on: TestClient, web: Web
) -> None:
    saved = ok(save(links_on, to_save(review(links_on, LINK))), 201)
    again = start(links_on, LINK)
    assert again.status_code == 409
    body = again.json()
    assert body["code"] == "already_imported"
    assert body["detail"] == "You already have this recipe"
    assert body["recipe"] == saved["recipe"]
    assert body["site"] == "bananaleaf.example"
    assert body["imported_at"]
    # Nothing was fetched a second time for the question.
    assert web.asked == [LINK]
    # "Import again as a copy" goes on to the review.
    assert review(links_on, LINK, again=True)["name"].startswith("Vendakkai")
    # And Save makes a second recipe.
    save(links_on, to_save(review(links_on, LINK, again=True)))
    assert counts(links_on)[0] == 2


def test_a_deleted_recipe_or_another_household_does_not_count_as_a_duplicate(
    links_on: TestClient, web: Web
) -> None:
    saved = ok(save(links_on, to_save(review(links_on, LINK))), 201)
    assert links_on.delete(f"{API}/recipes/{saved['recipe']['id']}").status_code == 200
    assert start(links_on, LINK).status_code == 200


def test_a_link_that_redirects_to_a_recipe_you_have_is_the_same_recipe(
    links_on: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok(save(links_on, to_save(review(links_on, LINK))), 201)
    short = "https://short.example/abc"
    real = web.fetch_page

    def redirected(gate: Any, household_id: int, url: str, **options: Any) -> FetchedPage:
        if url.startswith("https://short.example"):
            return FetchedPage(url=LINK, html=page_text())
        return real(gate, household_id, url, **options)

    monkeypatch.setattr(page_fetch, "fetch_page", redirected)
    assert start(links_on, short).status_code == 409


# --- Save -------------------------------------------------------------------------------------


def test_save_makes_everything_in_one_go_with_one_undo(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    lines = {line["written"]: index for index, line in enumerate(shown["lines"])}
    home = cupboard(kitchen)
    choices = {
        # "Same as Onions" for the red onion: learns "red onion"
        lines["1 red onion, sliced"]: {
            "kind": "ingredient",
            "food_id": pantry["Onions"]["id"],
            "learn": "red onion",
        },
        # A new ingredient, with its name and counting changed on the screen
        lines["1/4 tsp asafoetida"]: {
            "kind": "new",
            "name": "Hing",
            "counted_as": "weight",
            "place_id": home,
        },
        # Treat as staple
        lines["a sprig of curry leaves"]: {
            "kind": "staple",
            "name": "Curry leaves",
            "counted_as": "weight",
        },
    }
    before = counts(kitchen)
    saved = ok(save(kitchen, to_save(shown, choices), **{"Idempotency-Key": "import-1"}), 201)
    assert saved["recipe"]["name"] == "Sambar"
    assert [i["name"] for i in saved["new_ingredients"]] == ["Hing", "Curry leaves"]
    assert saved["learned"] == 1
    assert saved["change"]["kind"] == "recipe_imported" and saved["change"]["can_undo"]
    assert saved["change"]["summary"] == "Imported Sambar, with 2 new ingredients and 1 other name"

    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    by_words = {line["words"]: line for line in recipe["lines"]}
    assert by_words["thuvaram paruppu"]["food"]["name"] == "Toor dal"
    assert (by_words["thuvaram paruppu"]["amount"], by_words["thuvaram paruppu"]["unit"]) == (
        1,
        "cup",
    )
    assert by_words["red onion"]["food"]["name"] == "Onions"
    assert by_words["asafoetida"]["food"]["name"] == "Hing"
    assert by_words["curry leaves"]["food"]["name"] == "Curry leaves"
    assert by_words["salt"]["food"]["name"] == "Salt"
    assert [s["text"] for s in recipe["steps"]] == ["Boil the dal.", "Add the rest."]
    assert recipe["source"] is None  # pasted text has no address

    foods = {f["name"]: f for f in ok(kitchen.get(f"{API}/foods"))["foods"]}
    assert foods["Curry leaves"]["staple"] is True and foods["Hing"]["staple"] is False
    assert foods["Hing"]["counted_as"] == "weight"
    onions = ok(kitchen.get(f"{API}/foods/{pantry['Onions']['id']}"))
    assert "red onion" in [n["name"] for n in onions["other_names"]]
    assert counts(kitchen) == (before[0] + 1, before[1] + 2, before[2] + 1)  # 1 learned

    # One entry in Ingredients' Recent changes.
    listed = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients", "limit": 50}))
    imports = [c for c in listed["changes"] if c["kind"] == "recipe_imported"]
    assert len(imports) == 1
    assert not [c for c in listed["changes"] if c["summary"].startswith("Added Hing")]

    # Its Undo takes the whole save back.
    undone = ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert kitchen.get(f"{API}/recipes/{saved['recipe']['id']}").status_code == 404
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 0
    names = {f["name"] for f in ok(kitchen.get(f"{API}/foods"))["foods"]}
    assert "Hing" not in names and "Curry leaves" not in names
    onions = ok(kitchen.get(f"{API}/foods/{pantry['Onions']['id']}"))
    assert "red onion" not in [n["name"] for n in onions["other_names"]]


def test_a_second_undo_of_the_same_save_is_refused(kitchen: TestClient, web: Web) -> None:
    saved = ok(save(kitchen, to_save(review(kitchen, PASTED))), 201)
    ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    assert kitchen.post(f"{API}/changes/{saved['change']['id']}/undo").status_code == 409


def test_lines_with_no_choice_are_saved_as_words_only(kitchen: TestClient, web: Web) -> None:
    shown = review(kitchen, PASTED)
    saved = ok(save(kitchen, to_save(shown)), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert {line["link"] for line in recipe["lines"]} == {"none"}
    assert saved["new_ingredients"] == [] and saved["learned"] == 0
    assert counts(kitchen)[1:] == (0, 0)


def test_a_link_import_keeps_its_address_date_and_author(links_on: TestClient, web: Web) -> None:
    saved = ok(save(links_on, to_save(review(links_on, LINK))), 201)
    recipe = ok(links_on.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert recipe["source"]["url"] == LINK
    assert recipe["source"]["site"] == "bananaleaf.example"
    assert recipe["source"]["author"] == "Meena Raman"
    assert recipe["source"]["imported_at"].startswith("20")
    assert recipe["source_note"] is None


def test_makes_is_in_plain_units_in_the_review_and_saves_as_the_same_number(
    links_on: TestClient, web: Web
) -> None:
    """A page that says "24 cookies": the review says 24 (not 24000), and so does the saved
    recipe, which the screen's Save sends back as it was shown."""
    web.pages[LINK] = page_text("tasty_recipes.html")
    shown = review(links_on, LINK)
    assert shown["makes"] == {"amount": 24, "unit": "cookies"}
    saved = ok(save(links_on, to_save(shown)), 201)
    recipe = ok(links_on.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert (recipe["makes"]["amount"], recipe["makes"]["unit"]) == (24, "cookies")
    # A fraction and a metric unit are kept the same way.
    litres = ok(save(links_on, {**to_save(shown), "makes": {"amount": 1.5, "unit": "litres"}}), 201)
    recipe = ok(links_on.get(f"{API}/recipes/{litres['recipe']['id']}"))
    assert (recipe["makes"]["amount"], recipe["makes"]["unit"]) == (1.5, "l")


def test_the_address_kept_is_a_web_address_only(links_on: TestClient, web: Web) -> None:
    body = to_save(review(links_on, PASTED))
    for bad in ("javascript:alert(1)", "ftp://x.example/y", "file:///etc/passwd"):
        response = save(links_on, {**body, "source_url": bad})
        assert response.status_code == 422 and response.json()["code"] == "bad_source", bad


def test_two_lines_that_want_the_same_new_ingredient_make_it_once(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(
        kitchen, "Dal\nIngredients\n1 cup basmati rice\n2 cups basmati rice\nMethod\n1. Cook.\n"
    )
    new = {"kind": "new", "name": "Basmati rice", "counted_as": "weight"}
    saved = ok(save(kitchen, to_save(shown, {0: new, 1: new})), 201)
    assert [i["name"] for i in saved["new_ingredients"]] == ["Basmati rice"]
    assert counts(kitchen)[1] == 1


def test_a_new_ingredient_with_a_name_the_household_has_uses_that_one_not_a_refusal(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    # F213 (cabledrawer 10 Nov): another draft made the ingredient first, so this one is matched to
    # it at Save and never refused with "There's already an ingredient called ...".
    shown = review(kitchen, "Dal\nIngredients\n1 cup basmati rice\n1 onion\nMethod\n1. Cook.\n")
    before = counts(kitchen)[1]
    saved = ok(save(kitchen, to_save(shown, {1: {"kind": "new", "name": "onions"}})), 201)
    assert saved["new_ingredients"] == []
    assert counts(kitchen)[1] == before  # no second Onions
    recipe = kitchen.get(f"/api/v1/recipes/{saved['recipe']['id']}").json()
    assert [line["food"]["id"] for line in recipe["lines"] if line.get("food")][-1] == pantry[
        "Onions"
    ]["id"]
    assert counts(kitchen)[0] == 1


def test_a_name_another_ingredient_already_has_is_not_stolen_when_learning(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    shown = review(kitchen, "Dal\nIngredients\n1 red onion\n1 onion\nMethod\n1. Cook.\n")
    onions = pantry["Onions"]["id"]
    choices = {
        0: {"kind": "ingredient", "food_id": pantry["Toor dal"]["id"], "learn": "salt"},
        1: {"kind": "ingredient", "food_id": onions, "learn": "red onion"},
    }
    saved = ok(save(kitchen, to_save(shown, choices)), 201)
    assert saved["learned"] == 1  # "salt" belongs to Salt; "red onion" went to Onions
    dal = ok(kitchen.get(f"{API}/foods/{pantry['Toor dal']['id']}"))
    assert "salt" not in dal["other_names"]


def test_save_checks_the_recipe_again_as_the_editor_does(kitchen: TestClient, web: Web) -> None:
    good = to_save(review(kitchen, PASTED))
    assert save(kitchen, {**good, "name": "  "}).status_code == 422
    assert save(kitchen, {**good, "serves": 100}).status_code == 422
    assert save(kitchen, {**good, "tags": ["x"] * 21}).status_code == 422
    huge = {**good, "lines": [{**good["lines"][0], "amount": 1_000_001}]}
    assert save(kitchen, huge).status_code == 422
    assert counts(kitchen)[0] == 0


def test_a_step_over_5000_characters_is_cut_in_the_review_and_refused_if_sent_whole(
    links_on: TestClient, web: Web
) -> None:
    # The page reader doesn't cut a step by length, so the review does (and says how many).
    long = "Stir the pot slowly. " * 400  # 8,400 characters
    web.pages[LINK] = page_text("big_magazine.html").replace(
        "Heat oven to", long + "Heat oven to", 1
    )
    shown = review(links_on, LINK)
    assert shown["steps_shortened"] == 1
    assert all(len(step["text"]) <= 5000 for step in shown["steps"])
    ok(save(links_on, to_save(shown)), 201)
    body = to_save(shown)
    body["steps"][0]["text"] = long
    refused = save(links_on, body)
    assert refused.status_code == 422
    # Refused where it is, as the editor's own save is.
    assert refused.json()["detail"][0]["loc"] == ["body", "steps", 0, "text"]
    assert counts(links_on)[0] == 1


def test_a_retry_with_the_same_key_saves_once(kitchen: TestClient, web: Web) -> None:
    body = to_save(review(kitchen, PASTED))
    first = ok(save(kitchen, body, **{"Idempotency-Key": "k1"}), 201)
    second = save(kitchen, body, **{"Idempotency-Key": "k1"})
    assert second.status_code == 200 and second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["recipe"] == first["recipe"]
    assert counts(kitchen)[0] == 1
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert (
            db.scalar(
                select(func.count()).select_from(Change).where(Change.kind == "recipe_imported")
            )
            == 1
        )


def test_save_makes_the_import_date_in_the_recipes_own_list_of_changes(
    kitchen: TestClient, web: Web
) -> None:
    saved = ok(save(kitchen, to_save(review(kitchen, PASTED))), 201)
    mine = ok(kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}))
    assert mine["changes"][0]["id"] == saved["change"]["id"]


# --- Two households ---------------------------------------------------------------------------


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    from test_recipes_isolation import neighbour as make_neighbour

    yield from make_neighbour.__wrapped__(kitchen)  # type: ignore[attr-defined]


def test_another_households_ingredients_places_and_photos_are_not_reachable(
    kitchen: TestClient,
    neighbour: TestClient,
    web: Web,
    pantry: dict[str, dict[str, Any]],
) -> None:
    mine = review(neighbour, PASTED)
    # The neighbour sees none of Tess's ingredients in the review.
    assert all(line["food"] is None or line["label"] != "matched" for line in mine["lines"][:1])
    assert mine["counts"]["matched"] == 0
    foreign_food = {1: {"kind": "ingredient", "food_id": pantry["Onions"]["id"]}}
    response = save(neighbour, to_save(mine, foreign_food))
    assert response.status_code == 404 and response.json()["line"] == 1
    foreign_place = {1: {"kind": "new", "name": "Rice", "place_id": cupboard(kitchen)}}
    response = save(neighbour, to_save(mine, foreign_place))
    assert response.status_code == 404
    assert counts(neighbour)[0] == 0
    # A size of Tess's ingredients can't be used on the neighbour's line either.
    sized = food(kitchen, "Eggs", counted_as="count")
    size = ok(
        kitchen.post(f"{API}/foods/{sized['id']}/sizes", json={"name": "dozen", "amount": 12}),
        201,
    )
    own = review(neighbour, "Dal\nIngredients\n1 egg\nMethod\n1. Cook.\n")
    own_body = to_save(own, {0: {"kind": "new", "name": "Egg", "counted_as": "count"}})
    own_body["lines"][0]["size_id"] = size["food"]["sizes"][0]["id"]
    response = save(neighbour, own_body)
    assert response.status_code in (404, 422)
    assert counts(neighbour)[0] == 0
    # A waiting photo of Tess's household can't be taken by the neighbour's recipe.
    upload = ok(
        kitchen.post(
            f"{API}/recipes/photos", content=kit.jpeg(), headers={"Content-Type": "image/jpeg"}
        ),
        201,
    )
    response = save(neighbour, {**to_save(mine), "photo_id": upload["id"]})
    assert response.status_code == 404
    # Nor can a line use a recipe of Tess's (W4d, F188), or give it a place of his.
    theirs = ok(
        kitchen.post(f"{API}/recipes", json={"name": "Dosa batter", "made_ahead": True}), 201
    )
    foreign_recipe = {1: {"kind": "recipe", "recipe_id": theirs["id"]}}
    response = save(neighbour, to_save(mine, foreign_recipe))
    assert response.status_code == 404 and response.json()["line"] == 1
    foreign_home = {1: {"kind": "recipe", "recipe_id": theirs["id"], "place_id": cupboard(kitchen)}}
    assert save(neighbour, to_save(mine, foreign_home)).status_code == 404


def test_the_neighbours_link_import_does_not_see_my_recipes_as_duplicates(
    kitchen: TestClient, neighbour: TestClient, web: Web
) -> None:
    switch(kitchen, Connection.RECIPE_IMPORT)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        set_switch(db, 2, Connection.RECIPE_IMPORT, True)
        db.commit()
    ok(save(kitchen, to_save(review(kitchen, LINK))), 201)
    assert start(neighbour, LINK).status_code == 200


def test_import_is_in_the_public_api_only(kitchen: TestClient) -> None:
    paths = ok(kitchen.get("/api/v1/openapi.json"))["paths"]
    assert "/api/v1/recipes/import" in paths and "/api/v1/recipes/import/save" in paths
    assert "post" in paths["/api/v1/recipes/import"]


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.post(f"{API}/recipes/import", json={"text": "x"}).status_code == 401
    assert client.post(f"{API}/recipes/import/save", json={"name": "x"}).status_code == 401


def test_a_new_ingredient_made_by_an_import_gets_the_suggested_shop(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], web: Web
) -> None:
    del web
    ok(kitchen.post(f"{API}/shops", json={"name": "Tesco"}), 201)
    indian = ok(kitchen.post(f"{API}/shops", json={"name": "Indian grocer"}), 201)["id"]
    shown = review(kitchen, PASTED)
    lines = {line["written"]: index for index, line in enumerate(shown["lines"])}
    choices = {
        lines["1/4 tsp asafoetida"]: {
            "kind": "new",
            "name": "Mystery dust",
            "counted_as": "weight",
        },
        lines["a sprig of curry leaves"]: {"kind": "staple", "name": "Curry leaves"},
    }
    ok(save(kitchen, to_save(shown, choices)), 201)
    ids = {f["name"]: f["id"] for f in ok(kitchen.get(f"{API}/foods"))["foods"]}
    foods = {name: ok(kitchen.get(f"{API}/foods/{i}")) for name, i in ids.items()}
    # "Curry leaves" is specialist (Indian) in the pack-size table; "Mystery dust" is not.
    assert foods["Curry leaves"]["shop"]["id"] == indian
    assert foods["Mystery dust"]["shop"] is None
