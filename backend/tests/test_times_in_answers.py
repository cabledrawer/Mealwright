"""Every moment the API answers carries its zone (0.9.5-beta.3, D4, BE6).

SQLite gives stored times back without their zone, so a builder that passed one straight
through sent "2026-11-20T10:00:00", which a browser reads as its own local time. Every
datetime in an answer is a `Moment` (mealwright.moment), which is given UTC on the way out, so
no builder can forget. The first test walks every route's answer model for a plain datetime;
the others read real answers (some of them replays, read back from the database) and look for
a time with no zone.
"""

import re
import types
import typing
from datetime import datetime
from typing import Any, Union, get_args, get_origin

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pydantic.functional_validators import AfterValidator

from mealwright.models import as_utc

API = "/api/v1"
# An ISO moment: a date, "T", a time. A zone is "Z" or "+hh:mm"/"-hh:mm" at the end.
MOMENT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(?P<zone>Z|[+-]\d{2}:\d{2})?$")


def _is_moment(annotation: Any, metadata: list[Any]) -> bool:
    return any(isinstance(m, AfterValidator) and m.func is as_utc for m in metadata)


def _plain_datetimes(
    annotation: Any, where: str, seen: set[type], metadata: list[Any] | None = None
) -> list[str]:
    """Where a type holds a datetime that is not a Moment."""
    found: list[str] = []
    origin = get_origin(annotation)
    if origin is typing.Annotated:
        inner, *extra = get_args(annotation)
        return _plain_datetimes(inner, where, seen, [*(metadata or []), *extra])
    if annotation is datetime:
        return [] if _is_moment(annotation, metadata or []) else [where]
    if origin in (Union, types.UnionType, list, tuple, set, frozenset, dict) or (
        origin is not None and get_args(annotation)
    ):
        for arg in get_args(annotation):
            found += _plain_datetimes(arg, where, seen)
        return found
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return []
        seen.add(annotation)
        for name, field in annotation.model_fields.items():
            found += _plain_datetimes(
                field.annotation, f"{annotation.__name__}.{name}", seen, list(field.metadata)
            )
    return found


def _api_routes(routes: list[Any]) -> list[APIRoute]:
    """Every route of the API, through the routers it includes (FastAPI keeps an included
    router as one entry that points at the original)."""
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "original_router"):
            found += _api_routes(route.original_router.routes)
    return found


def test_every_moment_in_an_answer_model_is_given_its_zone() -> None:
    from mealwright.api.v1 import router

    routes = _api_routes(router.routes)
    assert len(routes) > 100  # the walk reached the routes
    plain: set[str] = set()
    seen: set[type] = set()
    for route in routes:
        if route.response_model is not None:
            plain.update(_plain_datetimes(route.response_model, route.path, seen))
    assert sorted(plain) == []


def _zoneless(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [z for k, v in value.items() for z in _zoneless(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [z for i, v in enumerate(value) for z in _zoneless(v, f"{path}[{i}]")]
    if isinstance(value, str):
        match = MOMENT.match(value)
        if match and not match.group("zone"):
            return [f"{path} = {value}"]
    return []


def _answers_have_zones(*answers: Any) -> None:
    for answer in answers:
        assert answer.status_code < 300, answer.text
        assert _zoneless(answer.json()) == [], answer.request.url


def test_recent_changes_and_a_replayed_change_carry_their_zone(kitchen: TestClient) -> None:
    """The lead's note from D2: a replayed change gave its `at` with no zone (read back from
    SQLite). The people route answers with its change, once fresh and once as a replay."""
    key = {"Idempotency-Key": "4d1c7c2e-5b0a-4e8e-9d1b-0d5bb8a1c001"}
    body = {"name": "Asha"}
    first = kitchen.post(f"{API}/people", json=body, headers=key)
    again = kitchen.post(f"{API}/people", json=body, headers=key)
    assert again.headers.get("Idempotent-Replayed") == "true"
    _answers_have_zones(first, again, kitchen.get(f"{API}/changes"), kitchen.get(f"{API}/people"))
    assert again.json()["change"]["at"].endswith("Z")


def test_settings_answers_carry_their_zone(kitchen: TestClient) -> None:
    made = kitchen.post(f"{API}/api-tokens", json={"name": "Script", "scope": "read"})
    assert made.status_code == 201, made.text
    _answers_have_zones(
        kitchen.get(f"{API}/api-tokens"),
        kitchen.get(f"{API}/me/sign-in"),
        kitchen.get(f"{API}/your-data/backups"),
        kitchen.get(f"{API}/updates"),
        kitchen.get(f"{API}/conversions"),
    )


@pytest.mark.parametrize("path", ["/me", "/household", "/mealie-imports/current"])
def test_other_answers_carry_their_zone(kitchen: TestClient, path: str) -> None:
    answer = kitchen.get(f"{API}{path}")
    if answer.status_code == 404:
        pytest.skip(f"{path} answers 404 with nothing made")
    _answers_have_zones(answer)
