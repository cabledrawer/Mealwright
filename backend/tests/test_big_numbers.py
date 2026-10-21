"""Numbers too big for the database are refused, never a server error (security audit, 0.4).

SQLite stores whole numbers up to 2^63 - 1. A bigger ID or cursor used to reach the
database and fail with a 500 there; in a sync batch it failed the whole batch instead of
refusing just that change.

Each one is refused where the request is read (`StoredInt` in errors.py), not by catching
the database's OverflowError afterwards: any other OverflowError is a bug and must show
as one.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import action, main_id, new_id, send

from mealwright.config import Settings
from mealwright.main import create_app

API = "/api/v1"
HUGE = 10**30


@pytest.fixture
def quiet_client(kitchen: TestClient) -> TestClient:
    """The same app, but a server error comes back as a 500 rather than raising."""
    quiet = TestClient(kitchen.app, base_url="https://testserver", raise_server_exceptions=False)
    quiet.cookies = kitchen.cookies
    return quiet


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", f"{API}/foods/{HUGE}", None),
        ("PATCH", f"{API}/foods/{HUGE}", {"staple": True}),
        ("POST", f"{API}/changes/{HUGE}/undo", None),
        ("GET", f"{API}/changes?before={HUGE}", None),
        ("GET", f"{API}/changes?food_id={HUGE}", None),
        ("POST", f"{API}/foods", {"name": "Butter", "place_id": HUGE}),
        ("POST", f"{API}/foods", {"name": "Butter", "shop_id": HUGE}),
        ("POST", f"{API}/stock/{HUGE}/used", {}),
        ("DELETE", f"{API}/conversions/{HUGE}", None),
    ],
)
def test_a_huge_number_is_refused(
    kitchen: TestClient, quiet_client: TestClient, method: str, url: str, body: Any
) -> None:
    response = quiet_client.request(method, url, json=body)
    assert response.status_code in {404, 422}, (url, response.status_code, response.text)
    assert response.json().get("code") in {"bad_number", "not_found"}, response.text


ITEM = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "tick", "item_id": ITEM, "seen": HUGE},
        {"kind": "dismiss_note", "note_id": HUGE},
        {"kind": "answer_double_tick", "question_id": HUGE, "answer": "two"},
        {"kind": "add", "item_id": ITEM, "food_id": HUGE},
        {"kind": "add", "item_id": ITEM, "food_id": 1, "size_id": HUGE},
        {"kind": "add", "item_id": ITEM, "food_id": 1, "shop_id": HUGE},
        {"kind": "set_amount", "item_id": ITEM, "amount": 1, "size_id": HUGE},
        {"kind": "put_away", "item_id": ITEM, "place_id": HUGE, "tick_ids": []},
        {
            "kind": "different_pack",
            "item_id": ITEM,
            "tick_id": "t1",
            "count": 1,
            "pack": 1,
            "size_id": HUGE,
        },
    ],
)
def test_a_huge_number_in_a_batch_refuses_only_that_change(
    kitchen: TestClient, quiet_client: TestClient, fields: dict[str, Any]
) -> None:
    fields = dict(fields)
    if fields["kind"] == "add":
        fields["list_id"] = main_id(kitchen)
    seen = fields.pop("seen", 0)
    bad = action(fields.pop("kind"), seen, **fields)
    good = action("create_list", list_id=new_id(), name="Party")
    first, second = send(quiet_client, bad, good)["results"]
    assert first["status"] == "refused" and first["reason"] == "bad_action", first
    assert second["status"] == "applied", second


# --- Every whole number the API reads, from its own description (OpenAPI) ----------------


def _ints(
    spec: dict[str, Any], schema: dict[str, Any], path: tuple[str | int, ...]
) -> Iterator[tuple[tuple[str | int, ...], dict[str, Any]]]:
    """Each whole number with no upper limit in a schema, as a path into the JSON."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in path:  # a schema that contains itself: once is enough
            return
        yield from _ints(spec, spec["components"]["schemas"][name], (*path, name))
        return
    for key in ("anyOf", "oneOf", "allOf"):
        for option in schema.get(key, []):
            yield from _ints(spec, option, path)
    fixed = "enum" in schema or "const" in schema  # one of a few numbers, like a cup's 240 or 250
    if schema.get("type") == "integer" and "maximum" not in schema and not fixed:
        yield path, schema
    for name, field in schema.get("properties", {}).items():
        yield from _ints(spec, field, (*path, name))
    if schema.get("type") == "array" and "items" in schema:
        yield from _ints(spec, schema["items"], (*path, 0))


def _body(path: tuple[str | int, ...], value: int) -> Any:
    """{"amount": {"answers": [{"food_id": value}]}} from ("amount", "answers", 0, "food_id"),
    skipping the schema names _ints keeps in the path."""
    keys = [k for k in path if isinstance(k, int) or k[:1].islower()]
    out: Any = value
    for key in reversed(keys):
        out = [out] if isinstance(key, int) else {key: out}
    return out


def _values(schema: dict[str, Any]) -> list[int]:
    """Too big both ways; a number with a lower limit refuses a negative one by that rule."""
    return [HUGE] if "minimum" in schema or "exclusiveMinimum" in schema else [HUGE, -HUGE]


def _cases() -> Iterator[Any]:
    spec = create_app(Settings(run_jobs=False)).openapi()
    for route, methods in spec["paths"].items():
        for method, op in methods.items():
            params = op.get("parameters", [])
            ints = {p["name"] for p in params if any(_ints(spec, p["schema"], ()))}
            for param in params:
                if param["name"] not in ints or param["in"] not in {"path", "query"}:
                    continue
                for _path, schema in _ints(spec, param["schema"], ()):
                    for value in _values(schema):
                        where = f"{param['in']} {param['name']}"
                        yield pytest.param(
                            method,
                            route,
                            ints,
                            (param["in"], param["name"]),
                            None,
                            value,
                            id=f"{method} {route} {where} {'-' if value < 0 else ''}huge",
                        )
            content = op.get("requestBody", {}).get("content", {}).get("application/json")
            for path, schema in _ints(spec, content["schema"], ()) if content else ():
                where = ".".join(str(k) for k in path if isinstance(k, int) or k[:1].islower())
                for value in _values(schema):
                    yield pytest.param(
                        method,
                        route,
                        ints,
                        ("body", None),
                        path,
                        value,
                        id=f"{method} {route} {where} {'-' if value < 0 else ''}huge",
                    )


@pytest.mark.parametrize(("method", "route", "ints", "where", "body_path", "value"), list(_cases()))
def test_every_whole_number_the_api_reads_is_refused_when_too_big(
    quiet_client: TestClient,
    method: str,
    route: str,
    ints: set[str],
    where: tuple[str, str | None],
    body_path: tuple[str | int, ...] | None,
    value: int,
) -> None:
    place, name = where
    url = route
    for param in ints:  # every other whole number in the path is a small, ordinary one
        url = url.replace(f"{{{param}}}", str(value) if (place, name) == ("path", param) else "1")
    url = url.replace("{list_id}", "main").replace("{copy}", "large").replace("{item_id}", ITEM)
    query = {name: str(value)} if place == "query" and name else None
    body = _body(body_path, value) if body_path is not None else None
    response = quiet_client.request(
        method.upper(), url, params=query, json=body, headers={"Idempotency-Key": new_id()}
    )
    assert response.status_code == 422, (url, query, body, response.status_code, response.text)
    assert response.json() == {"detail": "That number is too big.", "code": "bad_number"}


def test_the_biggest_number_the_database_holds_is_read_as_usual(kitchen: TestClient) -> None:
    """Just inside the limit is an ordinary number: nothing has that ID, so it's not found."""
    response = kitchen.get(f"{API}/foods/{2**63 - 1}")
    assert response.status_code == 404, response.text
    assert kitchen.get(f"{API}/foods/{2**63}").json()["code"] == "bad_number"


def test_any_other_overflow_is_a_server_error_that_gives_nothing_away(
    quiet_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only numbers in a request are refused as bad_number. An OverflowError anywhere else
    is a bug: a plain 500, with nothing in it about the server's code."""
    from mealwright.api.v1 import foods

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise OverflowError("Python int too large to convert to SQLite INTEGER: secret_column")

    monkeypatch.setattr(foods, "food_out", broken)
    response = quiet_client.post(
        f"{API}/foods", json={"name": "Butter"}, headers={"Idempotency-Key": new_id()}
    )
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
