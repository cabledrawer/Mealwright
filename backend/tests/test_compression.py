"""Compression (0.9.5 speed work): the build's text files come precompressed and are sent as
they are to a browser that accepts them; the API's bigger JSON answers are gzipped; and
nothing else is (photos, the live stream, downloads, secrets, writes)."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse
from sync_kit import ok

from mealwright.compression import JsonGzipMiddleware, accepted_encodings
from mealwright.config import Settings
from mealwright.main import create_app

CODE = "export const word = 'compressible';\n" * 80
PLAIN_BR = b"pretend-brotli-bytes"  # the server never reads a compressed copy, only sends it


@pytest.fixture
def build(tmp_path: Path) -> Path:
    folder = tmp_path / "build"
    (folder / "_app/immutable").mkdir(parents=True)
    (folder / "index.html").write_text("<!doctype html><p>app</p>")
    js = folder / "_app/immutable/app.abc.js"
    js.write_text(CODE)
    (folder / "_app/immutable/app.abc.js.gz").write_bytes(gzip.compress(CODE.encode(), mtime=0))
    (folder / "_app/immutable/app.abc.js.br").write_bytes(PLAIN_BR)
    (folder / "_app/immutable/only-gz.js").write_text(CODE)
    (folder / "_app/immutable/only-gz.js.gz").write_bytes(gzip.compress(CODE.encode(), mtime=0))
    (folder / "_app/immutable/plain.js").write_text(CODE)
    (folder / "pic.png").write_bytes(b"\x89PNG not really")
    (folder / "font.woff2").write_bytes(b"wOF2 not really")
    return folder


@pytest.fixture
def web(tmp_path: Path, build: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", frontend_dir=build)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


def get(web: TestClient, path: str, **headers: str) -> object:
    # The test client would unpack gzip itself; ask for the bytes as they were sent.
    return web.get(path, headers=headers)


# --- The build's files ----------------------------------------------------------------------


def test_brotli_is_sent_as_it_is_when_accepted(web: TestClient) -> None:
    got = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br, gzip"})
    assert got.status_code == 200
    assert got.headers["content-encoding"] == "br"
    assert got.headers["vary"] == "Accept-Encoding"
    assert got.headers["content-type"].startswith("text/javascript")
    assert got.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert got.content == PLAIN_BR
    assert int(got.headers["content-length"]) == len(PLAIN_BR)


def test_gzip_is_sent_when_brotli_is_not_accepted_and_unpacks_to_the_file(
    web: TestClient,
) -> None:
    got = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "gzip"})
    assert got.headers["content-encoding"] == "gzip"
    assert got.headers["vary"] == "Accept-Encoding"
    assert got.text == CODE  # the test client unpacks it, as a browser does


def test_the_plain_file_goes_to_a_browser_that_accepts_nothing(web: TestClient) -> None:
    got = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in got.headers
    assert got.headers["vary"] == "Accept-Encoding"
    assert got.text == CODE and int(got.headers["content-length"]) == len(CODE.encode())


def test_an_encoding_given_q_0_is_not_sent(web: TestClient) -> None:
    got = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br;q=0, gzip"})
    assert got.headers["content-encoding"] == "gzip"


def test_a_file_with_only_a_gzip_copy_gets_it_and_a_file_with_none_gets_neither(
    web: TestClient,
) -> None:
    got = web.get("/_app/immutable/only-gz.js", headers={"Accept-Encoding": "br, gzip"})
    assert got.headers["content-encoding"] == "gzip"
    plain = web.get("/_app/immutable/plain.js", headers={"Accept-Encoding": "br, gzip"})
    assert "content-encoding" not in plain.headers and "vary" not in plain.headers
    assert plain.text == CODE


def test_a_byte_range_is_of_the_file_itself(web: TestClient) -> None:
    got = web.get(
        "/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br, gzip", "Range": "bytes=0-9"}
    )
    assert got.status_code == 206
    assert "content-encoding" not in got.headers
    assert got.content == CODE.encode()[:10]


def test_the_etag_belongs_to_the_copy_sent(web: TestClient) -> None:
    first = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br"})
    plain = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "identity"})
    again = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br"})
    assert first.headers["etag"] != plain.headers["etag"]
    assert first.headers["etag"] == again.headers["etag"]


def test_pictures_and_fonts_are_never_packed_and_say_nothing_about_it(web: TestClient) -> None:
    for path in ("/pic.png", "/font.woff2"):
        got = web.get(path, headers={"Accept-Encoding": "br, gzip"})
        assert got.status_code == 200
        assert "content-encoding" not in got.headers and "vary" not in got.headers


def test_a_compressed_copy_is_not_a_page_of_the_app_and_the_cache_rules_stay(
    web: TestClient,
) -> None:
    page = web.get("/", headers={"Accept-Encoding": "br, gzip"})
    assert page.headers["cache-control"] == "no-cache"
    assert "content-encoding" not in page.headers  # this page has no compressed copy


# --- The service worker's list of files has none of them ---------------------------------------


def test_the_precache_list_never_names_a_compressed_copy() -> None:
    from mealwright import frontend

    assert {ext for _, ext in frontend.ENCODINGS} == {".br", ".gz"}
    # The worker caches what SvelteKit's manifest lists (the files Vite built and static/), which
    # the compress step runs after and never adds to; its list is checked in the browser code's
    # own test (src/lib/offline/rules.test.ts), which names `.br` and `.gz`.


# --- JSON answers --------------------------------------------------------------------------------


def lists_big_enough(kitchen: TestClient) -> None:
    for i in range(40):
        ok(kitchen.post("/api/v1/foods", json={"name": f"Ingredient number {i:03d}"}), 201)


def test_a_big_json_answer_is_gzipped_for_a_client_that_accepts_it(kitchen: TestClient) -> None:
    lists_big_enough(kitchen)
    plain = kitchen.get("/api/v1/foods?limit=500", headers={"Accept-Encoding": "identity"})
    packed = kitchen.get("/api/v1/foods?limit=500", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in plain.headers
    assert packed.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in packed.headers["vary"]
    assert packed.json() == plain.json()
    assert int(packed.headers["content-length"]) < int(plain.headers["content-length"]) / 2


def test_a_small_json_answer_is_left_as_it_is(kitchen: TestClient) -> None:
    got = kitchen.get("/api/v1/me", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in got.headers
    assert "Accept-Encoding" in got.headers["vary"]


def test_a_write_is_never_gzipped(kitchen: TestClient) -> None:
    made = kitchen.post(
        "/api/v1/foods",
        json={"name": "X" * 90, "other_names": ["Y" * 90] * 15},
        headers={"Accept-Encoding": "gzip"},
    )
    assert "content-encoding" not in made.headers


def test_the_live_stream_and_the_secret_paths_are_never_gzipped() -> None:
    # Built here, so what is checked is the middleware's own rule, not what a route happens to send.
    app = FastAPI()
    big = {"text": "x" * 5000}

    @app.get("/api/v1/events")
    def events() -> StreamingResponse:
        return StreamingResponse(
            iter([b"data: " + b"x" * 5000 + b"\n\n"]), media_type="text/event-stream"
        )

    for path in (
        "/api/v1/api-tokens",
        "/api/v1/sso/settings",
        "/api/v1/your-data/backups",
        "/api/v1/your-data/x",
    ):
        app.add_api_route(path, lambda: big, methods=["GET"])

    @app.get("/api/v1/download")
    def download() -> JSONResponse:
        return JSONResponse(big, headers={"Content-Disposition": 'attachment; filename="a.json"'})

    @app.get("/api/v1/text")
    def text() -> PlainTextResponse:
        return PlainTextResponse("x" * 5000)

    @app.get("/api/v1/already")
    def already() -> JSONResponse:
        return JSONResponse(big, headers={"Content-Encoding": "br"})

    @app.get("/api/v1/ok")
    def fine() -> dict[str, str]:
        return big

    app.add_middleware(JsonGzipMiddleware)
    client = TestClient(app)
    asked = {"Accept-Encoding": "gzip"}
    for path in (
        "/api/v1/events",
        "/api/v1/api-tokens",
        "/api/v1/sso/settings",
        "/api/v1/your-data/backups",
        "/api/v1/your-data/x",
        "/api/v1/download",
        "/api/v1/text",
    ):
        got = client.get(path, headers=asked)
        assert "content-encoding" not in got.headers, path
    assert client.get("/api/v1/already", headers=asked).headers["content-encoding"] == "br"
    assert client.get("/api/v1/ok", headers=asked).headers["content-encoding"] == "gzip"
    assert (
        client.get("/api/v1/ok", headers={"Accept-Encoding": "identity"}).headers.get(
            "content-encoding"
        )
        is None
    )
    assert (
        client.get("/api/v1/ok", headers={"Accept-Encoding": "gzip;q=0"}).headers.get(
            "content-encoding"
        )
        is None
    )
    assert client.get("/api/v1/ok", headers=asked).json() == big
    assert client.head("/api/v1/ok", headers=asked).headers.get("content-encoding") is None


def test_what_a_header_allows() -> None:
    assert accepted_encodings("br;q=0, gzip;q=0.5, deflate") == {"gzip", "deflate"}
    assert accepted_encodings("") == set()
    assert accepted_encodings("GZIP") == {"gzip"}
    assert json.dumps(sorted(accepted_encodings("gzip;q=x"))) == "[]"


def test_a_compressed_copy_cannot_be_asked_for_by_name(web: TestClient) -> None:
    for path in (
        "/_app/immutable/app.abc.js.gz",
        "/_app/immutable/app.abc.js.br",
        "/_app/immutable/app.abc.js.GZ",
        "/_app/immutable/app.abc.js.Br",
        "/_app/immutable/only-gz.js.gz",
        # Written another way, the same file is found by the lookup, so the name is judged there.
        "/_app/immutable/app.abc.js.gz/",
        "/_app/immutable/app.abc.js.gz/.",
        "/_app/immutable/app.abc.js.gz//",
        "/_app/immutable/app.abc.js.gz%2F",
        "/_app/immutable/x/../app.abc.js.br/",
    ):
        got = web.get(path, headers={"Accept-Encoding": "br, gzip"})
        assert got.status_code == 404, path
        assert "immutable" not in got.headers.get("cache-control", ""), path
    # The file itself still gets its compressed copy.
    got = web.get("/_app/immutable/app.abc.js", headers={"Accept-Encoding": "br"})
    assert got.status_code == 200 and got.headers["content-encoding"] == "br"
