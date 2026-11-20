"""An amount sent as text is at most 20 characters, everywhere the server reads one
(security pass, 0.4; cabledrawer 21 Oct: "put the length cap where every amount is read").

Recipe amounts are read by parse_amount (test_recipes.py has its own tests). Every other
amount is a number field, which ShortAmount (api/v1/schemas.py) caps. The cap must never
refuse anything those fields took before: the web app, and an old phone's offline queue,
send amounts as numbers, which the cap leaves alone, and every value the fields take is
short when written plainly. Only text padded out with spaces or zeros is refused now.
"""

import gc
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, TypeAdapter, ValidationError
from sync_kit import action, main_id, new_id, send

from mealwright.amounts import MAX_AMOUNT_TEXT
from mealwright.api.v1.pantry import AmountOrNone, SetLeft
from mealwright.api.v1.recipe_schemas import BAD_AMOUNT, Nutrient
from mealwright.api.v1.schemas import CupGrams, ItemGrams, Number, PositiveNumber
from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.sync import Amount

API = "/api/v1"
ITEM = "00000000-0000-4000-8000-000000000001"
NOT_A_NUMBER = "Input should be a valid decimal"
PADDED = "0" * (MAX_AMOUNT_TEXT - 2) + "1.5"  # 21 characters: 1.5 until now, refused now
HUGE = "1" * 800_000


@contextmanager
def _stopwatch() -> Iterator[Callable[[], float]]:
    """Seconds taken inside the block, with Python's tidy-up of left-over objects paused. In
    the whole test run it can stop everything for 1 to 2 seconds at any moment (measured 28 Oct:
    23 such stops in one run), and these huge texts set it off. That isn't the server being slow."""
    gc.disable()
    started = time.process_time()
    ended: list[float] = []
    try:
        yield lambda: (ended[0] if ended else time.process_time()) - started
    finally:
        ended.append(time.process_time())
        gc.enable()


def _type(kind: Any) -> Callable[[Any], Any]:
    return TypeAdapter(kind).validate_python


def _field(model: type[BaseModel], name: str, **rest: Any) -> Callable[[Any], Any]:
    return lambda value: getattr(model.model_validate({name: value, **rest}), name)


# Each amount field that isn't a recipe's, and the longest values it takes written plainly:
# the biggest with every decimal place, and the smallest. (A sync amount over 1,000,000 is
# refused too_big after this; the convert query is tested through the API below.)
FIELDS: dict[str, tuple[Callable[[Any], Any], list[str]]] = {
    "Number (not used yet)": (_type(Number), ["-999999999999.999", "999999999999.999"]),
    "PositiveNumber (AmountIn, answers, sizes)": (_type(PositiveNumber), ["999999.999", "0.001"]),
    "CupGrams": (_type(CupGrams), ["1999.999", "0.001"]),
    "ItemGrams": (_type(ItemGrams), ["49999.999", "0.001"]),
    "AmountOrNone (what's left)": (_field(AmountOrNone, "amount", unit="g"), ["999999.999", "0"]),
    "SetLeft.fraction (¼ ½ ¾ Full)": (_field(SetLeft, "fraction"), ["0.0001", "1.0000"]),
    "sync Amount (queued changes)": (_type(Amount), ["999999.999", "1000000.000", "0.001"]),
    "Nutrient (recipe nutrition)": (_type(Nutrient), ["99999.999", "100000.000", "0"]),
}


def _refused(read: Callable[[Any], Any], value: Any) -> str:
    with pytest.raises(ValidationError) as caught:
        read(value)
    return str(caught.value.errors()[0]["msg"])


@pytest.mark.parametrize("name", FIELDS)
def test_every_value_a_field_takes_still_fits(name: str) -> None:
    read, longest = FIELDS[name]
    for text in longest:
        assert len(text) <= MAX_AMOUNT_TEXT
        assert read(text) == Decimal(text)


@pytest.mark.parametrize("name", FIELDS)
def test_text_over_20_characters_is_refused_like_any_other_text(name: str) -> None:
    read, _ = FIELDS[name]
    assert read("0" * (MAX_AMOUNT_TEXT - 3) + "0.1") is not None  # 20 characters: still fine
    assert _refused(read, "0" * (MAX_AMOUNT_TEXT - 2) + "0.1") == NOT_A_NUMBER
    assert _refused(read, " " * MAX_AMOUNT_TEXT + "1") == NOT_A_NUMBER
    assert _refused(read, "lots") == NOT_A_NUMBER  # the same words as before
    with _stopwatch() as took:
        assert _refused(read, HUGE) == NOT_A_NUMBER
    assert took() < 0.5


@pytest.mark.parametrize("name", FIELDS)
def test_numbers_are_left_alone(name: str) -> None:
    """The web app sends amounts as numbers (JSON numbers, so floats or whole numbers here).
    However they were written, the cap never sees them as text."""
    read, _ = FIELDS[name]
    assert read(0.5) == read("0.5")
    assert read(1) == read("1")


# --- Through the API: every amount a request can carry, found from the API's description ----


def _amount(schema: dict[str, Any]) -> bool:
    """A number that may also be sent as text: how a decimal (or a recipe amount) looks."""
    kinds = {option.get("type") for option in schema.get("anyOf", [])}
    return {"number", "string"} <= kinds


def _amounts(
    spec: dict[str, Any], schema: dict[str, Any], path: tuple[str | int, ...]
) -> Iterator[tuple[str | int, ...]]:
    """The path to each amount in a request body, e.g. ("amount", "answers", 0, "grams")."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in path:  # a schema that contains itself: once is enough
            return
        yield from _amounts(spec, spec["components"]["schemas"][name], (*path, name))
        return
    if _amount(schema):
        yield path
        return
    for key in ("anyOf", "oneOf", "allOf"):
        for option in schema.get(key, []):
            yield from _amounts(spec, option, path)
    for name, field in schema.get("properties", {}).items():
        yield from _amounts(spec, field, (*path, name))
    if schema.get("type") == "array" and "items" in schema:
        yield from _amounts(spec, schema["items"], (*path, 0))


def _keys(path: tuple[str | int, ...]) -> list[str | int]:
    """Without the schema names _amounts keeps in the path."""
    return [k for k in path if isinstance(k, int) or k[:1].islower()]


def _body(path: tuple[str | int, ...], value: Any) -> Any:
    out: Any = value
    for key in reversed(_keys(path)):
        out = [out] if isinstance(key, int) else {key: out}
    return out


def _cases() -> Iterator[Any]:
    spec = create_app(Settings(run_jobs=False)).openapi()
    for route, methods in spec["paths"].items():
        if route == f"{API}/shopping/actions":  # a queued change is refused on its own: below
            continue
        for method, op in methods.items():
            for param in op.get("parameters", []):
                if _amount(param["schema"]):
                    yield pytest.param(
                        method, route, param["name"], None, id=f"{route} ?{param['name']}"
                    )
            content = op.get("requestBody", {}).get("content", {}).get("application/json")
            for path in _amounts(spec, content["schema"], ()) if content else ():
                where = ".".join(str(k) for k in _keys(path))
                yield pytest.param(method, route, None, path, id=f"{method} {route} {where}")


CASES = list(_cases())


def test_the_api_description_shows_the_amounts() -> None:
    """The next test finds every amount from the API's description, so a new one is sent
    without anyone listing it. This checks that finding them works."""
    found = {case.id for case in CASES}
    assert f"{API}/foods/{{food_id}}/convert ?amount" in found
    assert f"patch {API}/foods/{{food_id}} cup_weight" in found
    assert f"post {API}/stock/{{stock_id}}/set-left fraction" in found
    assert f"post {API}/recipes nutrition.kcal" in found
    assert len(found) == len(CASES) > 40


@pytest.mark.parametrize(("method", "route", "query", "body_path"), CASES)
def test_every_amount_the_api_reads_is_at_most_20_characters(
    kitchen: TestClient, method: str, route: str, query: str | None, body_path: Any
) -> None:
    url = (
        route.replace("{list_id}", "00000000-0000-4000-8000-000000000002")
        .replace("{item_id}", ITEM)
        .replace("{food_id}", "1")
        .replace("{size_id}", "1")
        .replace("{stock_id}", "1")
        .replace("{recipe_id}", "1")
    )
    # A web address can't hold 800k characters (the client refuses one over 64 KiB), so a
    # query amount is sent as 30,000 characters, which fits.
    for value in (PADDED, HUGE[:30_000] if query else HUGE):
        params = {query: value, "unit": "g"} if query else None
        body = _body(body_path, value) if body_path is not None else None
        with _stopwatch() as took:
            response = kitchen.request(
                method.upper(), url, params=params, json=body, headers={"Idempotency-Key": new_id()}
            )
        assert took() < 1
        assert response.status_code == 422, (url, response.status_code, response.text[:300])
        want = ["query", query] if query else ["body", *_keys(body_path)]
        found = [
            problem
            for problem in response.json()["detail"]
            if [part for part in problem["loc"] if part in want] == want
            and (problem["msg"] == NOT_A_NUMBER or BAD_AMOUNT in problem["msg"])
        ]
        assert found, (url, body_path, response.text[:600])


def test_a_queued_change_with_a_long_amount_is_refused_on_its_own(kitchen: TestClient) -> None:
    """A change in a phone's queue whose amount is long text is refused bad_action, as text
    that isn't a number always was; the changes around it still go through."""
    main = main_id(kitchen)
    ok_before = action("create_list", list_id=new_id(), name="Party")
    long_ones = [
        action(
            "add",
            list_id=main,
            item_id=new_id(),
            new_food={"name": "Rice", "counted_as": "weight"},
            amount=PADDED,
        ),
        action(
            "add",
            list_id=main,
            item_id=new_id(),
            new_food={
                "name": "Dal",
                "counted_as": "weight",
                "sizes": [{"name": "packet", "amount": PADDED}],
            },
        ),
        action("set_amount", item_id=ITEM, amount=HUGE),
        action("different_pack", item_id=ITEM, tick_id="t1", count=1, pack=PADDED),
    ]
    ok_after = action(
        "add",
        list_id=main,
        item_id=new_id(),
        new_food={"name": "Oats", "counted_as": "weight"},
        amount=1.5,
    )
    results = send(kitchen, ok_before, *long_ones, ok_after)["results"]
    assert results[0]["status"] == "applied", results[0]
    for result in results[1:-1]:
        assert (result["status"], result["reason"]) == ("refused", "bad_action"), result
        assert NOT_A_NUMBER in result["message"], result
    assert results[-1]["status"] == "applied", results[-1]
