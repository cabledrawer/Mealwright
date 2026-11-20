"""F259 (hand test 20 Nov, 0.9.5-beta.3): on Drafts by ingredient, "+ more" under a group's two
lines as written shows more. The server lists every way the group's unanswered lines are
written, most-used first, with how many lines write it that way. Made-up recipes only."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_mealie_answers import KASURI, SOY, A, B, C, answer, draft_names, file, groups
from test_mealie_import import API, bring_in, zipped

from mealwright import mealie_answers

D = f"a{3:031d}"
OTHER = ["1 tsp soya sauce", "soya sauce, to taste", "a splash of soya sauce"]


@pytest.fixture
def many(kitchen: TestClient, tmp_path: Path) -> TestClient:
    """Soya sauce written four ways across four drafts; the first way twice."""
    raw = zipped(
        tmp_path / "f.zip",
        file({A: [SOY, KASURI], B: [OTHER[0]], C: [SOY, OTHER[1]], D: [OTHER[2]]}),
        photo=False,
    )
    job = bring_in(kitchen, raw)
    assert job["counts"]["drafts"] == 4, job
    return kitchen


def lines(client: TestClient, key: str) -> Any:
    return client.get(f"{API}/recipes/drafts/by-food/lines", params={"key": key})


def test_every_way_a_group_is_written_most_used_first(many: TestClient) -> None:
    soy = next(g for g in groups(many)["groups"] if g["key"] == "soya sauce")
    assert len(soy["examples"]) == 2 and soy["lines"] == 5
    found = lines(many, "soya sauce")
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["key"] == "soya sauce" and body["total"] == 4
    assert body["lines"][0] == {"written": SOY, "count": 2}
    assert sorted(line["written"] for line in body["lines"][1:]) == sorted(OTHER)
    assert all(line["count"] == 1 for line in body["lines"][1:])
    # Looking changes nothing.
    assert len(draft_names(many)) == 4


def test_the_list_stops_at_its_limit_and_total_counts_them_all(
    many: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mealie_answers, "WRITTEN_LIMIT", 2)
    body = lines(many, "soya sauce").json()
    assert len(body["lines"]) == 2 and body["total"] == 4
    assert body["lines"][0]["written"] == SOY


def test_an_answered_or_unknown_group_is_not_found(many: TestClient) -> None:
    assert answer(many, "kasuri methi", "text").status_code == 200
    assert lines(many, "kasuri methi").status_code == 404
    assert lines(many, "nothing like it").status_code == 404
    assert lines(many, "").status_code == 422
    assert lines(many, "x" * 301).status_code == 422


def test_signed_out_refused_and_another_household_sees_nothing(
    many: TestClient, neighbour: TestClient
) -> None:
    assert lines(neighbour, "soya sauce").status_code == 404
    out = TestClient(many.app, base_url="https://testserver")
    assert lines(out, "soya sauce").status_code == 401
