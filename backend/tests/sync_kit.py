"""Helpers for the sync tests (docs/dev/sync-protocol.md section 14): a second person, a
batch, the catching-up answer. Time travel is done by editing rows."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright.auth import hash_password
from mealwright.models import Change, Household, ListTick, Login, Place, StockLot

API = "/api/v1"
PHONE_A = "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d42"  # Tess's phone
PHONE_B = "1c7d4a1f-8d2b-4a8f-8e1c-3a8b4d2f6e53"  # Tess's other phone
PHONE_R = "2d8e5b2a-9e3c-4b9a-9f2d-4b9c5e3a7f64"  # Wren's phone
WREN_PASSWORD = "wren's long password"


def db(client: TestClient) -> Any:
    return client.app.state.sessionmaker()  # type: ignore[attr-defined]


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


def food(client: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    made: dict[str, Any] = ok(client.post(f"{API}/foods", json={"name": name, **extra}), 201)
    return dict(made["food"])


def main_id(client: TestClient) -> str:
    lists = ok(client.get(f"{API}/shopping/lists"))["lists"]
    return str(next(row["id"] for row in lists if row["main"]))


def counter(client: TestClient) -> int:
    with db(client) as session:
        return int(session.get(Household, 1).list_seq)


def login_id(client: TestClient) -> int:
    return int(ok(client.get(f"{API}/me"))["id"])


def person(kitchen: TestClient, name: str = "Wren", username: str = "wren") -> TestClient:
    """A second login in the household, signed in on its own client (S0)."""
    with db(kitchen) as session:
        session.add(
            Login(
                household_id=1,
                username=username,
                name=name,
                password_hash=hash_password(WREN_PASSWORD),
                role="member",
            )
        )
        session.commit()
    other = TestClient(kitchen.app, base_url="https://testserver")
    ok(other.post(f"{API}/session", json={"username": username, "password": WREN_PASSWORD}))
    return other


def action(kind: str, seen: int = 0, **fields: Any) -> dict[str, Any]:
    return {
        "id": fields.pop("id", None) or new_id(),
        "kind": kind,
        "made_at": now(),
        "seen": seen,
        **fields,
    }


def send(
    client: TestClient,
    *actions: dict[str, Any],
    device: str = PHONE_A,
    since: int = 0,
    login: int | None = None,
    sent_at: str | None = None,
    status: int = 200,
) -> Any:
    body = {
        "protocol": 1,
        "device_id": device,
        "login_id": login if login is not None else login_id(client),
        "since": since,
        "sent_at": sent_at or now(),
        "actions": list(actions),
    }
    return ok(client.post(f"{API}/shopping/actions", json=body), status)


def one(client: TestClient, kind: str, seen: int = 0, device: str = PHONE_A, **fields: Any) -> Any:
    """Send one action; return its result (the batch answer is in result["_answer"])."""
    answer = send(client, action(kind, seen, **fields), device=device)
    result = dict(answer["results"][0])
    result["_answer"] = answer
    return result


def changes(client: TestClient, since: int = 0, device: str | None = None) -> Any:
    query = f"?since={since}" + (f"&device_id={device}" if device else "")
    return ok(client.get(f"{API}/shopping/sync{query}"))


def item_row(answer: Any, item_id: str) -> Any:
    return next(row for row in answer["items"] if row["id"] == item_id)


# --- Setup S0 (sync protocol section 14) ------------------------------------------------------


@dataclass
class S0:
    """One household; Tess (phone A) and Wren (phone R); two shops; the four places;
    seven ingredients; the main list with six items, none ticked; both phones at C0."""

    kitchen: TestClient
    wren: TestClient
    main: str
    shops: dict[str, int]
    places: dict[str, int]
    foods: dict[str, int]
    sizes: dict[str, int]
    items: dict[str, str]
    c0: int

    def lots(self, name: str) -> list[tuple[str, int]]:
        """(place name, amount in base units) of each non-empty lot of an ingredient."""
        names = {v: k for k, v in self.places.items()}
        with db(self.kitchen) as session:
            rows = session.scalars(
                select(StockLot)
                .where(StockLot.food_id == self.foods[name], StockLot.amount_milli > 0)
                .order_by(StockLot.id)
            ).all()
            return [(names[row.place_id], row.amount_milli // 1000) for row in rows]

    def total(self, name: str) -> int:
        return sum(amount for _, amount in self.lots(name))

    def changes_of(self, name: str, kind: str | None = None) -> list[Change]:
        with db(self.kitchen) as session:
            query = select(Change).where(Change.food_id == self.foods[name])
            if kind is not None:
                query = query.where(Change.kind == kind)
            rows = session.scalars(query.order_by(Change.id)).all()
            session.expunge_all()
            return list(rows)

    def ticks(self, item: str, standing: bool = True) -> list[ListTick]:
        with db(self.kitchen) as session:
            query = select(ListTick).where(ListTick.item_id == self.items[item])
            if standing:
                query = query.where(ListTick.reversed_at.is_(None))
            rows = session.scalars(query.order_by(ListTick.ticked_at)).all()
            session.expunge_all()
            return list(rows)

    def item(self, client: TestClient, name: str, since: int = 0) -> Any:
        return item_row(changes(client, since), self.items[name])

    def questions(self, client: TestClient) -> list[Any]:
        return [q for q in changes(client)["questions"] if q.get("open", True)]

    def notes(self, client: TestClient) -> list[Any]:
        return list(changes(client)["notes"])


def s0(kitchen: TestClient) -> S0:
    wren = person(kitchen)
    with db(kitchen) as session:
        places = {
            p.name: p.id for p in session.scalars(select(Place).where(Place.household_id == 1))
        }
    shops = {
        name: ok(kitchen.post(f"{API}/shops", json={"name": name}), 201)["id"]
        for name in ("Supermarket", "Indian grocer")
    }
    market = shops["Supermarket"]
    specs: list[tuple[str, dict[str, Any]]] = [
        ("Toor dal", {"counted_as": "weight", "place_id": places["Cupboard"]}),
        ("Paneer", {"counted_as": "weight", "place_id": places["Fridge"]}),
        ("Milk", {"counted_as": "volume", "place_id": places["Fridge"]}),
        ("Coriander", {"counted_as": "count", "place_id": places["Fridge"]}),
        ("Onions", {"counted_as": "count"}),
        ("Salt", {"counted_as": "weight", "staple": True}),
        ("Eggs", {"counted_as": "count", "place_id": places["Fridge"]}),
    ]
    foods = {name: food(kitchen, name, shop_id=market, **extra)["id"] for name, extra in specs}
    ok(kitchen.patch(f"{API}/foods/{foods['Coriander']}", json={"count_word": "bunch"}))
    sizes = {}
    for name, size, amount in (
        ("Toor dal", "packet", 500),
        ("Paneer", "pack", 200),
        ("Eggs", "box", 6),
    ):
        made = ok(
            kitchen.post(f"{API}/foods/{foods[name]}/sizes", json={"name": size, "amount": amount}),
            201,
        )
        sizes[name] = next(row["id"] for row in made["food"]["sizes"] if row["name"] == size)
    main = main_id(kitchen)
    lines: list[tuple[str, dict[str, Any]]] = [
        ("Toor dal", {"amount": 500, "size_id": sizes["Toor dal"]}),
        ("Paneer", {"amount": 400, "size_id": sizes["Paneer"]}),
        ("Milk", {"amount": 2000}),
        ("Coriander", {"amount": 1}),
        ("Onions", {"amount": 5}),
        ("Salt", {}),
    ]
    items = {name: new_id() for name, _ in lines}
    send(
        kitchen,
        *(
            action("add", list_id=main, item_id=items[name], food_id=foods[name], **extra)
            for name, extra in lines
        ),
    )
    return S0(kitchen, wren, main, shops, places, foods, sizes, items, counter(kitchen))


def tick(
    client: TestClient,
    s: S0,
    name: str,
    device: str = PHONE_A,
    seen: int | None = None,
    **extra: Any,
) -> Any:
    return one(
        client, "tick", s.c0 if seen is None else seen, device, item_id=s.items[name], **extra
    )
