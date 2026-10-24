# ruff: noqa: F811  (the fixtures come from test_recipe_import.py and are used by name)
"""Drafts: an import left unfinished, kept for 15 days (spec section 6, "Drafts (cabledrawer 21 Oct)",
"Drafts: how long they last (cabledrawer 22 Oct, question 8)" and "Size limits (cabledrawer 22 Oct,
question 9)"). The web is faked as in test_recipe_import.py: no test goes online.

Every test here fails without the behaviour it names; the revert proofs are in the pull
request."""

import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import photo_kit as kit
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sync_kit import ok, person
from test_recipe_import import (  # noqa: F401
    LINK,
    PASTED,
    Web,
    counts,
    cupboard,
    links_on,
    pantry,
    review,
    save,
    switch,
    to_save,
    web,
)

from mealwright import jobs, photos
from mealwright.auth import hash_password
from mealwright.db import Base
from mealwright.drafts import PHOTO_GONE, TOO_MANY, purge
from mealwright.household import add_default_places
from mealwright.models import (
    Change,
    Household,
    ImportDraft,
    Login,
    Recipe,
    RecipePhoto,
    utcnow,
)
from mealwright.outbound import Connection

API = "/api/v1"
ANY_PHOTO = {
    "id": 1,
    "width": 10,
    "height": 10,
    "url": "/x",
    "list_width": 5,
    "list_height": 5,
    "list_url": "/y",
}
NEIGHBOUR = {"username": "neighbour", "password": "next door's own password"}


def db(client: TestClient) -> Any:
    return client.app.state.sessionmaker()  # type: ignore[attr-defined]


def keep(
    client: TestClient,
    shown: dict[str, Any],
    text_: str = PASTED,
    choices: dict[str, Any] | None = None,
    key: str | None = None,
) -> Any:
    body = {"text": text_, "review": shown, "choices": choices or {}}
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"{API}/recipes/drafts", json=body, headers=headers)


def kept(client: TestClient, shown: dict[str, Any], **more: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(keep(client, shown, **more), 201)
    return found


def put(client: TestClient, draft_id: int, shown: dict[str, Any], **more: Any) -> Any:
    body = {
        "text": more.get("text_", PASTED),
        "review": shown,
        "choices": more.get("choices") or {},
    }
    return client.put(f"{API}/recipes/drafts/{draft_id}", json=body)


def listed(client: TestClient) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = ok(client.get(f"{API}/recipes/drafts"))["drafts"]
    return found


def age(client: TestClient, draft_id: int, **by: float) -> None:
    """Make the draft's last change that long ago."""
    with db(client) as session:
        session.execute(
            update(ImportDraft)
            .where(ImportDraft.id == draft_id)
            .values(updated_at=utcnow() - timedelta(**by))
        )
        session.commit()


_KEYS: dict[int, tuple[int, str]] = {}


@pytest.fixture(autouse=True)
def _forget_keys() -> None:
    _KEYS.clear()


def photo_files(client: TestClient, photo_id: int) -> tuple[bool, bool]:
    """Whether the photo's large and list files are on the disk. Asked while its record is
    there, it remembers which files they are, so that after the record is gone it still checks
    the files themselves, not just the record."""
    with db(client) as session:
        photo = session.get(RecipePhoto, photo_id)
        if photo is not None:
            _KEYS[photo_id] = (photo.household_id, photo.file_key)
        if photo_id not in _KEYS:
            raise AssertionError("ask about the photo while it is still there, first")
        household_id, key = _KEYS[photo_id]
        large, small = photos.paths(photos.store_of(session), household_id, key)
        return (large.is_file(), small.is_file())


def draft_photo(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    """A link import with a downloaded photo, kept as a draft. Returns (draft, review)."""
    shown = review(client, LINK)
    assert shown["photo"]["state"] == "downloaded"
    return kept(client, shown, text_=LINK), shown


@pytest.fixture
def photos_on(links_on: TestClient, web: Web) -> TestClient:
    switch(links_on, Connection.RECIPE_PHOTOS)
    web.photo = kit.jpeg(1200, 900)
    return links_on


def choices_for(shown: dict[str, Any], places: int) -> dict[str, Any]:
    """Every kind of choice: Same as…, New ingredient, Treat as staple."""
    onion = shown["lines"][2]
    return {
        "name": "My sambar",
        "serves": "6",
        "minutes": "45",
        "lines": {
            "2": {"kind": "ingredient", "food": onion["food"], "learn": True},
            "3": {"kind": "new", "name": "Asafoetida", "counted_as": "volume", "place_id": places},
            "4": {"kind": "staple", "name": "Curry leaves", "counted_as": "count"},
        },
    }


# --- Keeping a draft ----------------------------------------------------------------------


def test_a_draft_keeps_the_box_the_review_and_the_choices_and_lists_with_its_days(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    wanted = choices_for(shown, cupboard(kitchen))
    draft = kept(kitchen, shown, choices=wanted)
    assert draft["name"] == "My sambar"  # the Name box as it is now
    assert draft["source"] == {"kind": "text", "site": None}
    assert draft["started_by"] == "Tess"
    assert draft["days_left"] == 15 and draft["lines_total"] == 6
    assert draft["lines_checked"] == 6  # 3 matched or staple, and 3 chosen
    got = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert got["text"] == PASTED
    assert got["review"] == shown
    assert got["choices"]["name"] == "My sambar"
    assert got["choices"]["lines"]["3"]["place_id"] == cupboard(kitchen)
    assert {k: v["kind"] for k, v in got["choices"]["lines"].items()} == {
        "2": "ingredient",
        "3": "new",
        "4": "staple",
    }
    assert [d["id"] for d in listed(kitchen)] == [draft["id"]]
    assert ok(kitchen.get(f"{API}/recipes/drafts"))["count"] == 1


def test_the_list_counts_the_lines_that_are_tied_to_an_ingredient(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    bare = kept(kitchen, shown)
    # Matched and staple lines count without a choice; the 3 others need one.
    assert (bare["lines_total"], bare["lines_checked"]) == (6, 3)
    more = ok(put(kitchen, bare["id"], shown, choices=choices_for(shown, cupboard(kitchen))))
    assert more["lines_checked"] == 6


def test_a_link_draft_says_where_it_came_from(links_on: TestClient, web: Web) -> None:
    shown = review(links_on, LINK)
    draft = kept(links_on, shown, text_=LINK)
    assert draft["source"] == {"kind": "link", "site": "bananaleaf.example"}
    assert ok(links_on.get(f"{API}/recipes/drafts/{draft['id']}"))["text"] == LINK


def test_nothing_in_a_draft_touches_ingredients_until_save(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    """Keeping, changing, reading, deleting and undoing a draft with New ingredient, Treat as
    staple and Same as choices makes no ingredient, staple or other name, and writes nothing
    to Ingredients' Recent changes."""
    shown = review(kitchen, PASTED)
    before = counts(kitchen)
    recent = ok(kitchen.get(f"{API}/changes?area=ingredients"))["changes"]
    with db(kitchen) as session:
        known = set(session.scalars(select(Change.id)))
    wanted = choices_for(shown, cupboard(kitchen))
    draft = kept(kitchen, shown, choices=wanted)
    ok(put(kitchen, draft["id"], shown, choices=wanted))
    ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert counts(kitchen) == before
    gone = ok(kitchen.delete(f"{API}/recipes/drafts/{draft['id']}"))
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert counts(kitchen) == before
    assert ok(kitchen.get(f"{API}/changes?area=ingredients"))["changes"] == recent
    with db(kitchen) as session:
        new = list(session.scalars(select(Change.kind).where(Change.id.not_in(known))))
    assert sorted(new) == ["draft_removed", "draft_saved", "undo"]
    # Saving it is what makes them.
    body = to_save(shown, {3: {"kind": "new", "name": "Asafoetida", "counted_as": "volume"}})
    ok(save(kitchen, {**body, "draft_id": draft["id"]}), 201)
    assert counts(kitchen)[1] == before[1] + 1


def test_a_second_try_with_the_same_change_id_keeps_one_draft(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    first = ok(keep(kitchen, shown, key="keep-1"), 201)
    again = keep(kitchen, shown, key="keep-1")
    assert again.status_code == 200 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first["id"]
    assert len(listed(kitchen)) == 1
    other = keep(kitchen, shown, key="keep-2")
    assert other.status_code == 201 and len(listed(kitchen)) == 2


def test_a_number_too_big_for_the_database_is_refused_anywhere_in_a_draft(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    """A review's ids and counts, and the ids in the choices, are looked up or stored: a huge
    one is 422 `bad_number`, never a server error (test_big_numbers.py checks every review
    field from the OpenAPI; this is the choices, which it doesn't walk)."""
    shown = review(kitchen, PASTED)
    quiet = TestClient(kitchen.app, base_url="https://testserver", raise_server_exceptions=False)
    quiet.cookies = kitchen.cookies
    huge = 10**30
    food = {"id": huge, "name": "Onions"}
    for choices in (
        {"lines": {"2": {"kind": "ingredient", "food": food}}},
        {"lines": {"3": {"kind": "new", "name": "Hing", "place_id": huge}}},
        {"lines": {str(huge): {"kind": "new", "name": "Hing"}}},
    ):
        response = keep(quiet, shown, choices=choices)
        assert response.status_code == 422, (choices, response.text)
    shown["photo"] = {"state": "downloaded", "photo": {**ANY_PHOTO, "id": huge}, "message": None}
    response = keep(quiet, shown)
    assert response.status_code == 422 and response.json()["code"] == "bad_number"
    assert listed(kitchen) == []


def test_a_drafts_choices_have_a_size_limit_too(
    kitchen: TestClient, pantry: dict[str, Any], web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The choices are stored with the draft, so they are bounded: an ingredient's name in
    them is at most 200 characters (201 is refused, 200 saves), and they count towards the
    same cap as the review."""
    shown = review(kitchen, PASTED)
    food = {"id": 1, "name": "x" * 200}
    ok_choices = {"lines": {"2": {"kind": "ingredient", "food": food}}}
    assert keep(kitchen, shown, choices=ok_choices, key="fits").status_code == 201
    # The name's own limit: 201 characters is refused, with the total cap far away.
    long = {"lines": {"2": {"kind": "ingredient", "food": {"id": 1, "name": "x" * 201}}}}
    refused = keep(kitchen, shown, choices=long)
    assert refused.status_code == 422, refused.text[:200]
    # And a huge name is refused too (by the name limit, before the total is counted).
    huge = {"lines": {"2": {"kind": "ingredient", "food": {"id": 1, "name": "x" * 3_000_000}}}}
    assert keep(kitchen, shown, choices=huge).status_code == 422
    # Choices that are each allowed still count: with the cap just above the review alone,
    # the review plus these is over it.
    from mealwright.api.v1 import draft_schemas

    size = draft_schemas.stored_size(draft_schemas.ImportReview.model_validate(shown))
    nothing = draft_schemas.stored_size(draft_schemas.DraftChoices())
    monkeypatch.setattr(draft_schemas, "MAX_REVIEW_BYTES", size + nothing + 20)
    assert keep(kitchen, shown, key="alone").status_code == 201
    assert keep(kitchen, shown, choices=ok_choices).status_code == 422
    assert len(listed(kitchen)) == 2


def test_the_size_cap_counts_a_draft_as_it_is_stored_not_in_characters(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    """The review and choices are stored as JSON with every non-ASCII character escaped (an
    emoji is 1 character, 4 bytes sent and 12 stored), so the 2 MB cap counts the stored form.
    A review of 100 steps of 5,000 emoji is 500,000 characters but about 6 MB stored."""
    shown = review(kitchen, PASTED)
    heavy = {**shown, "steps": [{"kind": "step", "text": "\U0001f600" * 5_000}] * 100}
    refused = keep(kitchen, heavy)
    assert refused.status_code == 422, refused.text[:200]
    assert listed(kitchen) == []
    # A real-sized draft with names that aren't ASCII still saves, and comes back as it was.
    names = {
        **shown,
        "name": "Thuvaram paruppu \U0001f600",
        "steps": [{"kind": "step", "text": "Fry the jalape\u00f1o in the ghee."}],
    }
    kept_ = kept(kitchen, names, choices={"name": "Jalape\u00f1o dal"})
    assert kept_["name"] == "Jalape\u00f1o dal"
    assert len(listed(kitchen)) == 1


def test_a_nameless_draft_is_still_listed_and_a_review_that_is_too_big_is_refused(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    blank = kept(kitchen, {**shown, "name": ""}, choices={"name": "  "})
    assert blank["name"] == "Untitled recipe"
    big = {**shown, "steps": [{"kind": "step", "text": "x" * 5_001}]}
    assert keep(kitchen, big).status_code == 422
    many = {**shown, "lines": shown["lines"] * 40}  # 240 lines: more than a recipe can have
    assert keep(kitchen, many).status_code == 422
    # A choice for a line that isn't there, or for a heading, is refused too.
    assert (
        keep(kitchen, shown, choices={"lines": {"99": {"kind": "new", "name": "X"}}}).status_code
        == 422
    )
    assert keep(kitchen, shown, choices={"lines": {"2": {"kind": "ingredient"}}}).status_code == 422


# --- Carrying on --------------------------------------------------------------------------


def test_anyone_in_the_household_can_carry_on_and_the_last_save_wins(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    draft = kept(kitchen, shown, choices={"name": "Tess's name"})
    wren = person(kitchen)
    seen = ok(wren.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert seen["started_by"] == "Tess" and seen["choices"]["name"] == "Tess's name"
    assert [d["id"] for d in listed(wren)] == [draft["id"]]
    # Both save at once, one after the other: the second one stands, no error for either.
    ok(put(wren, draft["id"], shown, choices={"name": "Wren's name"}))
    ok(put(kitchen, draft["id"], shown, choices={"name": "Tess's second name"}))
    now = ok(wren.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert now["choices"]["name"] == "Tess's second name"
    assert now["started_by"] == "Tess"  # who started it doesn't change
    # A member can delete it, and bring it back.
    gone = ok(wren.delete(f"{API}/recipes/drafts/{draft['id']}"))
    assert listed(kitchen) == []
    ok(wren.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert len(listed(kitchen)) == 1


def test_each_change_starts_the_15_days_again_and_opening_does_not(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    draft = kept(kitchen, shown)
    age(kitchen, draft["id"], days=10)
    assert listed(kitchen)[0]["days_left"] == 5
    opened = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert opened["days_left"] == 5  # looking changes nothing
    again = ok(put(kitchen, draft["id"], shown, choices={"name": "Changed"}))
    assert again["days_left"] == 15
    assert listed(kitchen)[0]["days_left"] == 15


def test_the_days_left_count_up_to_the_last_day(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    draft = kept(kitchen, review(kitchen, PASTED))
    for ago, left in [
        (timedelta(hours=1), 15),
        (timedelta(days=12, hours=1), 3),
        (timedelta(days=14, hours=23), 1),
    ]:
        age(kitchen, draft["id"], seconds=ago.total_seconds())
        assert listed(kitchen)[0]["days_left"] == left


# --- The 15 days --------------------------------------------------------------------------


def test_a_draft_past_its_15_days_is_gone_and_the_hourly_tidy_up_deletes_it_with_its_photo(
    photos_on: TestClient,
) -> None:
    draft, shown = draft_photo(photos_on)
    photo_id = shown["photo"]["photo"]["id"]
    fresh = kept(photos_on, review(photos_on, LINK, again=True), text_=LINK)
    age(photos_on, draft["id"], days=15, minutes=1)
    # Already hidden, before the tidy-up has run.
    assert [d["id"] for d in listed(photos_on)] == [fresh["id"]]
    assert photos_on.get(f"{API}/recipes/drafts/{draft['id']}").status_code == 404
    assert put(photos_on, draft["id"], shown).status_code == 404
    assert photo_files(photos_on, photo_id)[0] is True
    with db(photos_on) as session:
        household = session.get(Household, 1)
        assert household is not None
        assert purge(session, household) == 1
    assert photo_files(photos_on, photo_id) == (False, False)  # the record and both files
    with db(photos_on) as session:
        assert session.get(ImportDraft, draft["id"]) is None
        assert session.get(ImportDraft, fresh["id"]) is not None


def test_the_scheduler_job_does_the_tidy_up(photos_on: TestClient) -> None:
    draft, shown = draft_photo(photos_on)
    assert photo_files(photos_on, shown["photo"]["photo"]["id"]) == (True, True)
    age(photos_on, draft["id"], days=16)
    jobs.purge_removed_ingredients(photos_on.app.state.sessionmaker)  # type: ignore[attr-defined]
    with db(photos_on) as session:
        assert session.get(ImportDraft, draft["id"]) is None
    assert photo_files(photos_on, shown["photo"]["photo"]["id"]) == (False, False)


def test_a_draft_that_is_still_inside_its_days_is_not_touched_by_the_tidy_up(
    photos_on: TestClient,
) -> None:
    draft, shown = draft_photo(photos_on)
    age(photos_on, draft["id"], days=14, hours=23)
    with db(photos_on) as session:
        household = session.get(Household, 1)
        assert household is not None
        assert purge(session, household) == 0
    assert len(listed(photos_on)) == 1
    assert photo_files(photos_on, shown["photo"]["photo"]["id"]) == (True, True)


def test_the_photo_of_a_draft_past_its_15_days_is_gone_before_the_tidy_up_too(
    photos_on: TestClient,
) -> None:
    draft, shown = draft_photo(photos_on)
    photo = shown["photo"]["photo"]
    assert photos_on.get(photo["url"]).status_code == 200
    age(photos_on, draft["id"], days=14, hours=23)
    assert photos_on.get(photo["url"]).status_code == 200
    age(photos_on, draft["id"], days=15, hours=1)  # out of time; the hourly job hasn't run
    assert photos_on.get(photo["url"]).status_code == 404
    assert photos_on.get(photo["list_url"]).status_code == 404
    assert photo_files(photos_on, photo["id"]) == (True, True)  # still on disk, just not shown


# --- Deleting and Undo --------------------------------------------------------------------


def test_delete_hides_the_draft_and_undo_brings_it_back_with_its_photo(
    photos_on: TestClient,
) -> None:
    draft, shown = draft_photo(photos_on)
    photo = shown["photo"]["photo"]
    age(photos_on, draft["id"], days=9)
    gone = ok(photos_on.delete(f"{API}/recipes/drafts/{draft['id']}"))
    change = gone["change"]
    assert change["summary"] == f"Deleted the {draft['name']} draft"
    assert draft["name"].startswith("Vendakkai Poriyal")
    assert change["can_undo"] is True
    assert listed(photos_on) == []
    assert photos_on.get(f"{API}/recipes/drafts/{draft['id']}").status_code == 404
    assert photos_on.delete(f"{API}/recipes/drafts/{draft['id']}").status_code == 404
    assert photos_on.get(photo["url"]).status_code == 404  # hidden with the draft
    assert photo_files(photos_on, photo["id"]) == (True, True)  # but kept for the Undo
    undone = ok(photos_on.post(f"{API}/changes/{change['id']}/undo"))
    assert undone["result"] == "done"
    assert "back in Drafts" in undone["message"]
    back = listed(photos_on)[0]
    assert back["id"] == draft["id"] and back["days_left"] == 15  # counted as just changed
    assert photos_on.get(photo["url"]).status_code == 200
    # An Undo that has been done can't be done twice.
    assert photos_on.post(f"{API}/changes/{change['id']}/undo").status_code == 409


def test_a_deleted_draft_and_its_photo_go_for_good_after_7_days(photos_on: TestClient) -> None:
    draft, shown = draft_photo(photos_on)
    gone = ok(photos_on.delete(f"{API}/recipes/drafts/{draft['id']}"))
    photo_id = shown["photo"]["photo"]["id"]
    assert photo_files(photos_on, photo_id) == (True, True)
    with db(photos_on) as session:
        household = session.get(Household, 1)
        assert household is not None
        session.execute(
            update(ImportDraft)
            .where(ImportDraft.id == draft["id"])
            .values(removed_at=utcnow() - timedelta(days=6, hours=22))
        )
        session.commit()
        assert purge(session, household) == 0  # still inside the 7 days
        session.execute(
            update(ImportDraft)
            .where(ImportDraft.id == draft["id"])
            .values(removed_at=utcnow() - timedelta(days=7, hours=2))
        )
        session.commit()
        assert purge(session, household) == 1
    assert photo_files(photos_on, photo_id) == (False, False)
    undo = photos_on.post(f"{API}/changes/{gone['change']['id']}/undo")
    assert undo.status_code == 410  # too old, and the draft is gone


def test_ctrl_z_can_find_the_delete_in_the_servers_list_of_your_changes(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    draft = kept(kitchen, review(kitchen, PASTED))
    gone = ok(kitchen.delete(f"{API}/recipes/drafts/{draft['id']}"))
    mine = ok(kitchen.get(f"{API}/changes?mine=true&limit=5"))["changes"]
    assert [c["id"] for c in mine if c["kind"] == "draft_removed"] == [gone["change"]["id"]]
    assert all(c["kind"] != "draft_saved" for c in mine)  # the key-only record isn't listed


def test_undo_at_50_drafts_is_refused_with_the_plain_sentence(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    first = kept(kitchen, shown)
    gone = ok(kitchen.delete(f"{API}/recipes/drafts/{first['id']}"))
    for _ in range(50):
        kept(kitchen, shown)
    undo = kitchen.post(f"{API}/changes/{gone['change']['id']}/undo")
    assert undo.status_code == 409 and undo.json()["detail"] == TOO_MANY
    assert len(listed(kitchen)) == 50


# --- Limits -------------------------------------------------------------------------------


def test_at_50_drafts_the_51st_says_so_and_no_old_draft_is_deleted(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    ids = [kept(kitchen, shown)["id"] for _ in range(50)]
    refused = keep(kitchen, shown)
    assert refused.status_code == 409
    assert refused.json()["code"] == "too_many_drafts"
    assert refused.json()["detail"] == "You have 50 drafts. Finish or delete one first."
    assert sorted(d["id"] for d in listed(kitchen)) == sorted(ids)  # nothing deleted for room
    # A deleted one, or one past its days, doesn't count; Finishing one makes room too.
    ok(kitchen.delete(f"{API}/recipes/drafts/{ids[0]}"))
    age(kitchen, ids[1], days=20)
    assert keep(kitchen, shown).status_code == 201
    assert keep(kitchen, shown).status_code == 201
    assert keep(kitchen, shown).status_code == 409
    ok(save(kitchen, {**to_save(shown), "draft_id": ids[2]}), 201)
    assert keep(kitchen, shown).status_code == 201


def test_a_second_household_has_its_own_50(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    for _ in range(50):
        kept(kitchen, shown)
    with db(kitchen) as session:
        session.add(Household(id=2, name="Next door"))
        session.flush()
        add_default_places(session, 2)
        session.add(
            Login(
                household_id=2,
                username="neighbour",
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        session.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        ok(other.post(f"{API}/session", json=NEIGHBOUR))
        assert keep(other, shown).status_code == 201


def test_pasted_text_of_100000_characters_is_kept_and_more_is_refused(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    long = PASTED + "x" * (100_000 - len(PASTED))
    assert len(long) == 100_000
    draft = kept(kitchen, shown, text_=long)
    assert ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))["text"] == long
    assert keep(kitchen, shown, text_=long + "x").status_code == 422
    assert keep(kitchen, shown, text_="").status_code == 422


def test_a_biggest_possible_review_fits(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    steps = [{"kind": "step", "text": "Stir. " * 833}] * 100  # 100 steps of about 5,000
    huge = {**shown, "steps": steps, "lines": (shown["lines"] * 34)[:200]}
    draft = kept(kitchen, huge, text_="x" * 100_000)
    assert len(ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))["review"]["steps"]) == 100


# --- The photo ----------------------------------------------------------------------------


def test_the_photo_belongs_to_the_draft_and_does_not_count_towards_the_10_waiting(
    photos_on: TestClient,
) -> None:
    draft, shown = draft_photo(photos_on)
    photo = shown["photo"]["photo"]
    assert (
        ok(photos_on.get(f"{API}/recipes/drafts/{draft['id']}"))["review"]["photo"]["photo"]["id"]
        == photo["id"]
    )
    with db(photos_on) as session:
        row = session.get(RecipePhoto, photo["id"])
        assert row is not None and row.draft_id == draft["id"] and row.recipe_id is None
    # 10 uploads can still wait (the draft's photo is not one of them).
    for _ in range(10):
        assert photos_on.post(f"{API}/recipes/photos", content=kit.jpeg()).status_code == 201
    assert photos_on.post(f"{API}/recipes/photos", content=kit.jpeg()).status_code == 409
    assert photos_on.get(photo["url"]).status_code == 200  # the draft shows it


def test_a_download_is_still_allowed_when_drafts_hold_photos_and_9_others_wait(
    photos_on: TestClient,
) -> None:
    """The draft-photo exclusion in the download's own count (recipe_import._store_waiting):
    with drafts holding photos, 9 waiting ones leave room for one more download, then none."""
    for _ in range(3):  # three drafts, each holding a downloaded photo
        draft_photo(photos_on)
        photos_on.post(f"{API}/recipes/photos", content=kit.jpeg())  # one waiting each time...
    # ...which is 3 waiting; add 6 more to make 9.
    for _ in range(6):
        assert photos_on.post(f"{API}/recipes/photos", content=kit.jpeg()).status_code == 201
    assert len(listed(photos_on)) == 3
    one_more = review(photos_on, LINK, again=True)
    assert one_more["photo"]["state"] == "downloaded"  # the 10th waiting one
    full = review(photos_on, LINK, again=True)
    assert (
        full["photo"]["state"] == "failed" and full["photo"]["message"] == photos.TOO_MANY_WAITING
    )


def test_a_draft_photo_is_not_deleted_after_24_hours_but_a_waiting_one_is(
    photos_on: TestClient,
) -> None:
    from mealwright.recipes import drop_waiting_photos

    _draft, shown = draft_photo(photos_on)
    waiting = ok(photos_on.post(f"{API}/recipes/photos", content=kit.jpeg()), 201)
    assert photo_files(photos_on, waiting["id"]) == (True, True)
    with db(photos_on) as session:
        session.execute(update(RecipePhoto).values(added_at=utcnow() - timedelta(hours=30)))
        session.commit()
        household = session.get(Household, 1)
        assert household is not None
        assert drop_waiting_photos(session, household) == 1
    assert photo_files(photos_on, waiting["id"]) == (False, False)
    assert photo_files(photos_on, shown["photo"]["photo"]["id"]) == (True, True)


def test_nothing_else_can_take_or_delete_a_draft_photo(photos_on: TestClient) -> None:
    _draft, shown = draft_photo(photos_on)
    photo_id = shown["photo"]["photo"]["id"]
    deleted = photos_on.delete(f"{API}/recipes/photos/{photo_id}")
    assert deleted.status_code == 409 and deleted.json()["code"] == "photo_in_use"
    recipe = photos_on.post(f"{API}/recipes", json={"name": "Mine", "photo_id": photo_id})
    assert recipe.status_code == 404
    # Nor can a Save that doesn't name the draft.
    refused = save(photos_on, to_save(shown))
    assert refused.status_code == 404
    with db(photos_on) as session:
        assert session.scalar(select(func.count()).select_from(Recipe)) == 0
    assert photo_files(photos_on, photo_id) == (True, True)


def test_a_photo_that_is_no_longer_there_keeps_the_draft_without_it(photos_on: TestClient) -> None:
    shown = review(photos_on, LINK)
    with db(photos_on) as session:
        session.execute(text("DELETE FROM recipe_photo"))
        session.commit()
    draft = kept(photos_on, shown, text_=LINK)
    got = ok(photos_on.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert got["review"]["photo"] == {"state": "failed", "photo": None, "message": PHOTO_GONE}


def test_changing_the_photo_in_a_draft_lets_go_of_the_old_one(photos_on: TestClient) -> None:
    draft, shown = draft_photo(photos_on)
    old = shown["photo"]["photo"]["id"]
    second = review(photos_on, LINK, again=True)
    new = second["photo"]["photo"]["id"]
    assert photo_files(photos_on, old) == (True, True)
    ok(put(photos_on, draft["id"], second, text_=LINK))
    assert photo_files(photos_on, old) == (False, False)  # the old one's files are gone too
    assert photo_files(photos_on, new) == (True, True)
    ok(
        put(
            photos_on,
            draft["id"],
            {**second, "photo": {"state": "none", "photo": None, "message": None}},
            text_=LINK,
        )
    )
    assert photo_files(photos_on, new) == (False, False)


# --- Save from a draft --------------------------------------------------------------------


def test_save_from_a_draft_makes_the_recipe_as_save_does_and_removes_the_draft(
    photos_on: TestClient, pantry: dict[str, Any]
) -> None:
    draft, shown = draft_photo(photos_on)
    photo_id = shown["photo"]["photo"]["id"]
    body = {**to_save(shown), "draft_id": draft["id"]}
    saved = ok(save(photos_on, body), 201)
    assert saved["change"]["kind"] == "recipe_imported"  # the one entry, one Undo
    assert listed(photos_on) == []
    assert photos_on.get(f"{API}/recipes/drafts/{draft['id']}").status_code == 404
    recipe = ok(photos_on.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert recipe["photo"]["id"] == photo_id  # the draft's photo is the recipe's
    assert photo_files(photos_on, photo_id) == (True, True)
    with db(photos_on) as session:
        row = session.get(RecipePhoto, photo_id)
        assert row is not None and row.draft_id is None and row.recipe_id == recipe["id"]
        assert session.get(ImportDraft, draft["id"]) is None
        kinds = list(session.scalars(select(Change.kind).where(Change.kind.like("recipe_%"))))
    assert kinds.count("recipe_imported") == 1
    # The same tidy-up that deletes drafts leaves the recipe's photo alone.
    with db(photos_on) as session:
        household = session.get(Household, 1)
        assert household is not None
        purge(session, household)
    assert photo_files(photos_on, photo_id) == (True, True)


def test_a_save_that_fails_leaves_the_draft_and_its_photo_as_they_were(
    photos_on: TestClient, pantry: dict[str, Any]
) -> None:
    draft, shown = draft_photo(photos_on)
    bad = {**to_save(shown), "draft_id": draft["id"], "name": ""}
    assert save(photos_on, bad).status_code == 422
    first = next(i for i, line in enumerate(shown["lines"]) if line["kind"] == "ingredient")
    clash = to_save(shown, {first: {"kind": "new", "name": "Toor dal", "counted_as": "weight"}})
    assert save(photos_on, {**clash, "draft_id": draft["id"]}).status_code == 409
    assert len(listed(photos_on)) == 1
    with db(photos_on) as session:
        row = session.get(RecipePhoto, shown["photo"]["photo"]["id"])
        assert row is not None and row.draft_id == draft["id"]
        assert session.scalar(select(func.count()).select_from(Recipe)) == 0


def test_a_retry_of_a_save_from_a_draft_saves_once(
    photos_on: TestClient, pantry: dict[str, Any]
) -> None:
    draft, shown = draft_photo(photos_on)
    body = {**to_save(shown), "draft_id": draft["id"]}
    first = ok(save(photos_on, body, **{"Idempotency-Key": "go-1"}), 201)
    again = save(photos_on, body, **{"Idempotency-Key": "go-1"})
    assert again.status_code == 200 and again.json()["recipe"] == first["recipe"]
    with db(photos_on) as session:
        assert session.scalar(select(func.count()).select_from(Recipe)) == 1


def test_a_draft_that_was_deleted_or_ran_out_cannot_be_saved_from(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    gone = kept(kitchen, shown)
    ok(kitchen.delete(f"{API}/recipes/drafts/{gone['id']}"))
    old = kept(kitchen, shown)
    age(kitchen, old["id"], days=16)
    for draft in (gone, old, {"id": 9999}):
        refused = save(kitchen, {**to_save(shown), "draft_id": draft["id"]})
        assert refused.status_code == 404
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(Recipe)) == 0


def test_undo_of_the_save_takes_the_recipe_back_but_the_draft_stays_gone(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    draft = kept(kitchen, shown)
    saved = ok(save(kitchen, {**to_save(shown), "draft_id": draft["id"]}), 201)
    ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    assert listed(kitchen) == []


# --- Stale ingredients --------------------------------------------------------------------


def test_an_ingredient_that_changed_since_is_shown_as_it_is_now(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    onion = pantry["Onions"]
    dal = pantry["Toor dal"]
    chosen = {"lines": {"2": {"kind": "ingredient", "food": onion, "learn": True}}}
    draft = kept(kitchen, shown, choices=chosen)
    # Toor dal is renamed; Onions is merged into Green chillies (to see a merge followed).
    ok(kitchen.patch(f"{API}/foods/{dal['id']}", json={"name": "Tur dal"}))
    ok(
        kitchen.post(
            f"{API}/foods/{onion['id']}/merge", json={"into_id": pantry["Green chillies"]["id"]}
        )
    )
    got = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert got["review"]["lines"][0]["food"]["name"] == "Tur dal"
    assert got["choices"]["lines"]["2"]["food"] == {
        "id": pantry["Green chillies"]["id"],
        "name": "Green chillies",
    }


def test_an_ingredient_that_was_removed_since_is_no_longer_offered(
    kitchen: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    onion = pantry["Onions"]
    dal = pantry["Toor dal"]
    chosen = {"lines": {"2": {"kind": "ingredient", "food": onion, "learn": True}}}
    draft = kept(kitchen, shown, choices=chosen)
    assert draft["lines_checked"] == 4
    ok(kitchen.delete(f"{API}/foods/{onion['id']}"))
    ok(kitchen.delete(f"{API}/foods/{dal['id']}"))
    got = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    line = got["review"]["lines"][0]
    assert (line["label"], line["food"], line["matched_by"]) == ("needs_you", None, None)
    assert got["choices"]["lines"] == {}  # the choice that pointed at Onions is dropped
    # Toor dal's line, and the Onions line whose best guess is gone, now need you too.
    assert got["review"]["counts"] == {"matched": 1, "to_confirm": 0, "needs_you": 4, "staple": 1}
    # What is stored is not rewritten by looking.
    with db(kitchen) as session:
        stored = session.get(ImportDraft, draft["id"])
        assert stored is not None
        assert stored.review["lines"][0]["food"]["id"] == dal["id"]
        assert "2" in stored.choices["lines"]


# --- Other households ---------------------------------------------------------------------


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    with db(kitchen) as session:
        session.add(Household(id=2, name="Next door"))
        session.flush()
        add_default_places(session, 2)
        session.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        session.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        ok(other.post(f"{API}/session", json=NEIGHBOUR))
        yield other


def rows_of_household_1(client: TestClient) -> dict[str, list[tuple[Any, ...]]]:
    found: dict[str, list[tuple[Any, ...]]] = {}
    with db(client) as session:
        for table in Base.metadata.sorted_tables:
            column = "id" if table.name == "household" else "household_id"
            query = f'SELECT * FROM "{table.name}" WHERE {column} = 1 ORDER BY 1, 2'  # noqa: S608
            found[table.name] = [tuple(row) for row in session.execute(text(query)).all()]
    return found


def test_another_household_can_not_read_change_carry_on_delete_undo_or_save_from_a_draft(
    photos_on: TestClient, neighbour: TestClient, pantry: dict[str, Any]
) -> None:
    mine, shown = draft_photo(photos_on)
    photo = shown["photo"]["photo"]
    second = kept(photos_on, review(photos_on, LINK, again=True), text_=LINK)
    gone = ok(photos_on.delete(f"{API}/recipes/drafts/{second['id']}"))
    waiting = review(photos_on, LINK, again=True)["photo"]["photo"]  # no draft has it
    before = rows_of_household_1(photos_on)
    mine_id = mine["id"]

    assert listed(neighbour) == []
    assert ok(neighbour.get(f"{API}/recipes/drafts"))["count"] == 0
    assert neighbour.get(f"{API}/recipes/drafts/{mine_id}").status_code == 404
    assert put(neighbour, mine_id, shown, text_=LINK).status_code == 404
    assert neighbour.delete(f"{API}/recipes/drafts/{mine_id}").status_code == 404
    assert neighbour.post(f"{API}/changes/{gone['change']['id']}/undo").status_code == 404
    refused = save(neighbour, {**to_save(shown), "draft_id": mine_id})
    assert refused.status_code == 404
    assert neighbour.get(photo["url"]).status_code == 404
    assert neighbour.delete(f"{API}/recipes/photos/{photo['id']}").status_code == 404
    # Their own Save can't take my draft's photo, with or without my draft's id.
    for extra in ({}, {"draft_id": mine_id}):
        assert save(neighbour, {**to_save(shown), **extra}).status_code == 404
    # And a draft of theirs can't pick up my photo either: neither the one my draft keeps, nor a
    # waiting one that no draft has yet.
    theirs = kept(neighbour, shown, text_=LINK)
    assert theirs["review"]["photo"] == {"state": "failed", "photo": None, "message": PHOTO_GONE}
    grabbed = kept(
        neighbour, {**shown, "photo": {"state": "downloaded", "photo": waiting}}, text_=LINK
    )
    assert grabbed["review"]["photo"]["state"] == "failed"
    with db(photos_on) as session:
        row = session.get(RecipePhoto, waiting["id"])
        assert row is not None and row.draft_id is None and row.household_id == 1
    ok(neighbour.delete(f"{API}/recipes/drafts/{grabbed['id']}"))
    assert [d["id"] for d in listed(neighbour)] == [theirs["id"]]
    assert [d["id"] for d in listed(photos_on)] == [mine_id]  # theirs isn't mine
    assert photos_on.get(f"{API}/recipes/drafts/{theirs['id']}").status_code == 404

    after = rows_of_household_1(photos_on)
    assert after == before  # not one row of household 1 changed
    assert photo_files(photos_on, photo["id"]) == (True, True)


def test_ids_inside_a_drafts_review_and_choices_give_nothing_of_another_household(
    kitchen: TestClient, neighbour: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    """A review or a choice that names the other household's ingredient (or place) is never
    followed: its name isn't shown back, the line goes back to "needs you", and Save refuses
    the place and the ingredient as not found."""
    ghee = ok(neighbour.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]
    their_place = next(p["id"] for p in ok(neighbour.get(f"{API}/places")))
    shown = review(kitchen, PASTED)
    lines = list(shown["lines"])
    lines[0] = {**lines[0], "food": {"id": ghee["id"], "name": "Ghee"}}
    chosen = {
        "lines": {
            "2": {"kind": "ingredient", "food": {"id": ghee["id"], "name": "Ghee"}},
            "3": {
                "kind": "new",
                "name": "Asafoetida",
                "counted_as": "volume",
                "place_id": their_place,
            },
        }
    }
    draft = kept(kitchen, {**shown, "lines": lines}, choices=chosen)
    got = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert "Ghee" not in str(got)
    assert got["review"]["lines"][0]["food"] is None
    assert got["review"]["lines"][0]["label"] == "needs_you"
    assert list(got["choices"]["lines"]) == ["3"]
    # Saving with the other household's place, or ingredient, is refused and makes nothing.
    before = counts(kitchen)
    new = {"kind": "new", "name": "Asafoetida", "counted_as": "volume", "place_id": their_place}
    for link in (new, {"kind": "ingredient", "food_id": ghee["id"]}):
        refused = save(kitchen, {**to_save(shown, {3: link}), "draft_id": draft["id"]})
        assert refused.status_code == 404, refused.text
    assert counts(kitchen) == before
    assert len(listed(kitchen)) == 1


def test_an_undo_record_pointing_at_another_households_draft_brings_nothing_back(
    kitchen: TestClient, neighbour: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    """Only household 2's own Undo can bring back household 2's deleted draft, even if a change
    of household 1 were made to name it."""
    theirs = kept(neighbour, review(kitchen, PASTED))
    ok(neighbour.delete(f"{API}/recipes/drafts/{theirs['id']}"))
    with db(kitchen) as session:
        forged = Change(
            household_id=1,
            kind="draft_removed",
            request="DELETE /api/v1/recipes/drafts/1",
            login_id=1,
            login_name="Tess",
            at=utcnow(),
            summary="Deleted the draft",
            undo_data={"draft_id": theirs["id"]},
        )
        session.add(forged)
        session.commit()
        forged_id = forged.id
    refused = kitchen.post(f"{API}/changes/{forged_id}/undo")
    assert refused.status_code == 410
    assert listed(neighbour) == []  # still deleted: nothing came back
    with db(kitchen) as session:
        stays = session.get(ImportDraft, theirs["id"])
        assert stays is not None and stays.removed_at is not None


def test_the_tidy_up_of_one_household_leaves_the_other_alone(
    kitchen: TestClient, neighbour: TestClient, pantry: dict[str, Any], web: Web
) -> None:
    shown = review(kitchen, PASTED)
    mine = kept(kitchen, shown)
    theirs = kept(neighbour, shown)
    age(kitchen, mine["id"], days=20)
    age(kitchen, theirs["id"], days=20)
    with db(kitchen) as session:
        household = session.get(Household, 1)
        assert household is not None
        assert purge(session, household) == 1
        assert session.get(ImportDraft, mine["id"]) is None
        stays = session.get(ImportDraft, theirs["id"])
        assert stays is not None and stays.household_id == 2


# --- Logs ---------------------------------------------------------------------------------


def test_logs_never_hold_a_drafts_link_or_text(
    photos_on: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    shown = review(photos_on, LINK)
    text_ = LINK + "\nSecret pasted words about grandma's cake"
    draft = kept(photos_on, shown, text_=text_)
    ok(photos_on.get(f"{API}/recipes/drafts/{draft['id']}"))
    ok(put(photos_on, draft["id"], shown, text_=text_))
    listed(photos_on)
    gone = ok(photos_on.delete(f"{API}/recipes/drafts/{draft['id']}"))
    ok(photos_on.post(f"{API}/changes/{gone['change']['id']}/undo"))
    age(photos_on, draft["id"], days=20)
    jobs.purge_removed_ingredients(photos_on.app.state.sessionmaker)  # type: ignore[attr-defined]
    everything = "\n".join(record.getMessage() for record in caplog.records)
    for secret in ("bananaleaf", "grandma", "vendakkai", "Vendakkai"):
        assert secret not in everything


def test_a_signed_out_visitor_gets_nothing(kitchen: TestClient) -> None:
    with TestClient(kitchen.app, base_url="https://testserver") as stranger:
        assert stranger.get(f"{API}/recipes/drafts").status_code == 401
        assert stranger.get(f"{API}/recipes/drafts/1").status_code == 401
        assert stranger.delete(f"{API}/recipes/drafts/1").status_code == 401
