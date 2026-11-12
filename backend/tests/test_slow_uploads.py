"""A photo upload whose body arrives slowly holds nothing while it arrives: no database
connection and no place among the requests using the database (`REQUESTS_AT_ONCE`), so
everyone else is still answered (pool-fix sweep, item 9).

Before: the sign-in check's session stayed open, with its place, until the 15 MB body was in,
so 40 slow uploads from signed-in devices kept every other request waiting.
"""

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import Future
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from test_many_at_once import connections_out

from mealwright.config import Settings
from mealwright.db import REQUESTS_AT_ONCE
from mealwright.main import create_app

# More than there are places, so uploads that held one could never all reach their body.
UPLOADS = REQUESTS_AT_ONCE + 5
PATIENCE = 20  # seconds; nothing here waits unless something is wrong


@pytest.fixture
def quiet_client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        yield client


class SlowUploads:
    """Uploads sent straight to the app (the test client would send the whole body at once):
    each one's body arrives only when the test says `finish()`."""

    def __init__(self, client: TestClient, cookie: str) -> None:
        self.client = client
        self.cookie = cookie
        self.asked = 0  # how many uploads have asked for their body
        self.wanted = 0
        self.all_asked = threading.Event()
        self.body_may_arrive: asyncio.Event = client.portal.call(self._event)  # type: ignore[union-attr]
        self.answers: list[Future[int]] = []

    @staticmethod
    async def _event() -> asyncio.Event:
        return asyncio.Event()

    async def _one(self) -> int:
        status: list[int] = []
        asked = False

        async def receive() -> dict[str, Any]:
            nonlocal asked
            if not asked:
                asked = True
                self.asked += 1
                if self.asked == self.wanted:
                    self.all_asked.set()
            await self.body_may_arrive.wait()
            return {"type": "http.request", "body": b"not a photo", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status.append(message["status"])

        headers = [(b"host", b"testserver"), (b"content-type", b"image/jpeg")]
        if self.cookie:
            headers.append((b"cookie", self.cookie.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/recipes/photos",
            "raw_path": b"/api/v1/recipes/photos",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 443),
        }
        await self.client.app(scope, receive, send)
        return status[0]

    def start(self, how_many: int) -> None:
        self.wanted = how_many
        portal = self.client.portal
        assert portal is not None
        self.answers = [portal.start_task_soon(self._one) for _ in range(how_many)]

    def finish(self) -> list[int]:
        """Let every body arrive; the answers' status codes."""
        portal = self.client.portal
        assert portal is not None
        portal.call(self._let_arrive)
        return [answer.result(PATIENCE) for answer in self.answers]

    async def _let_arrive(self) -> None:
        self.body_may_arrive.set()


def cookie_of(client: TestClient) -> str:
    return "; ".join(f"{name}={value}" for name, value in client.cookies.items())


def test_slow_uploads_hold_no_connection_and_no_place(quiet_client: TestClient) -> None:
    uploads = SlowUploads(quiet_client, cookie_of(quiet_client))
    with connections_out(quiet_client) as count:
        uploads.start(UPLOADS)
        try:
            # Every upload got as far as waiting for its body, past the sign-in check...
            assert uploads.all_asked.wait(PATIENCE), f"only {uploads.asked} of {UPLOADS}"
            # ...holding no connection...
            assert count[0] == 0
            # ...and no place: a full house of plain reads is answered meanwhile.
            answered: list[int] = []

            def read() -> None:
                answered.append(quiet_client.get("/api/v1/recipes").status_code)

            readers = [threading.Thread(target=read) for _ in range(REQUESTS_AT_ONCE)]
            for reader in readers:
                reader.start()
            for reader in readers:
                reader.join(PATIENCE)
            assert answered == [200] * REQUESTS_AT_ONCE
        finally:
            codes = uploads.finish()
    # Signed in, so once its body was in each got through to the photo check ("not a photo"),
    # or was told the household has 10 uploads in hand already.
    assert len(codes) == UPLOADS
    assert set(codes) <= {422, 409}
    assert 422 in codes
    assert count[0] == 0


def test_a_signed_out_upload_is_refused_before_its_body_is_read(quiet_client: TestClient) -> None:
    uploads = SlowUploads(quiet_client, cookie="")
    uploads.start(1)
    # The body never arrives (finish() is not called): the answer comes all the same.
    assert uploads.answers[0].result(PATIENCE) == 401
    assert uploads.asked == 0


def test_an_upload_signed_out_while_its_body_arrives_is_refused(quiet_client: TestClient) -> None:
    """The sign-in is checked again once the body is in."""
    uploads = SlowUploads(quiet_client, cookie_of(quiet_client))
    uploads.start(1)
    assert uploads.all_asked.wait(PATIENCE)
    assert quiet_client.delete("/api/v1/session").status_code in (200, 204)
    assert uploads.finish() == [401]
