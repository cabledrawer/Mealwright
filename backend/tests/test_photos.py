"""Recipe photos: cleaned, made small and kept on this server (cabledrawer 19 Oct), attached
by the recipe's own Save (cabledrawer 20 Oct)."""

import io
import os
import re
import stat
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import photo_kit as kit
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageCms
from sqlalchemy import select, update
from sync_kit import ok
from test_recipes import make, save

from mealwright import jobs, photos
from mealwright.limits import MAX_BODY_BYTES, MAX_PHOTO_BYTES
from mealwright.models import Recipe, RecipePhoto, utcnow

API = "/api/v1"
NOT_A_PHOTO = "That isn’t a photo Mealwright can use. Try a JPEG, PNG or WebP."
TOO_BIG = "That photo is bigger than 15 MB."
WAITING = "Too many photos waiting to be saved. Save or cancel a recipe first."
GONE = "That photo isn’t here any more."
TOO_MANY_PIXELS = "That photo is too big to use (over 50 megapixels). Try a smaller copy."


def store(client: TestClient) -> Path:
    return Path(client.app.state.settings.data_dir) / "photos"  # type: ignore[attr-defined]


def files_of(client: TestClient) -> list[Path]:
    root = Path(client.app.state.settings.data_dir)  # type: ignore[attr-defined]
    return sorted(p for p in root.rglob("*") if p.is_file() and "photos" in p.parts)


def record(client: TestClient, photo_id: int) -> RecipePhoto | None:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return db.get(RecipePhoto, photo_id)


def photo_files(client: TestClient, photo_id: int) -> tuple[Path, Path]:
    found = record(client, photo_id)
    assert found is not None
    return photos.paths(store(client), found.household_id, found.file_key)


def fetch(client: TestClient, photo: dict[str, Any], copy: str = "large") -> Any:
    return client.get(photo["url"] if copy == "large" else photo["list_url"])


def metadata(data: bytes) -> dict[str, Any]:
    """Everything Pillow can find in a file besides the pixels."""
    image = kit.opened(data)
    found = {k: v for k, v in image.info.items() if not k.startswith(("jfif", "dpi"))}
    exif = image.getexif()
    if exif:
        found["exif"] = dict(exif)
        gps = exif.get_ifd(0x8825)
        if gps:
            found["gps"] = dict(gps)
    if isinstance(image, Image.Image) and hasattr(image, "text") and image.text:
        found["text"] = dict(image.text)
    return found


def colour(image: Image.Image, x: int, y: int) -> str:
    r, g, b = image.convert("RGB").getpixel((x, y))  # type: ignore[misc]
    if min(r, g, b) > 230:
        return "white"
    if r > 180 and g < 80 and b < 80:
        return "red"
    if b > 180 and r < 80 and g < 80:
        return "blue"
    if g > 100 and r < 80 and b < 80:
        return "green"
    return f"{r},{g},{b}"


# --- Cleaning ---------------------------------------------------------------------------------


@pytest.mark.parametrize("make_file", [kit.jpeg, kit.png, kit.webp], ids=["jpeg", "png", "webp"])
def test_every_hidden_detail_is_removed(make_file: Any) -> None:
    sent = make_file()
    before = metadata(sent)
    # The test files really do carry them, so the test can't pass by accident.
    assert before.get("exif", {}).get(0x010F) == "SecretCam"
    assert before.get("gps", {}).get(1) == "N"
    if make_file is not kit.png:
        assert b"Secret Person" in sent  # XMP
    else:
        assert before["text"]["Author"] == "Secret Person"
        assert before["text"]["Comment"] == "Hidden note"  # a compressed text chunk
    cleaned = photos.clean(sent)
    for data in (cleaned.large, cleaned.small):
        assert data.startswith(b"\xff\xd8")
        assert kit.opened(data).format == "JPEG"
        assert metadata(data) == {}
        for secret in kit.SECRETS:
            assert secret not in data
        assert b"Exif" not in data and b"http://ns.adobe.com/xap" not in data
        assert b"ICC_PROFILE" not in data


def test_the_jpeg_comment_and_xmp_are_gone_too() -> None:
    sent = kit.jpeg()
    assert b"Hidden note" in sent and b"adobe:ns:meta" in sent
    cleaned = photos.clean(sent)
    assert b"Hidden note" not in cleaned.large and b"adobe:ns:meta" not in cleaned.large


@pytest.mark.parametrize(
    ("orientation", "size", "top", "bottom"),
    [(1, (400, 300), "red", "red"), (6, (300, 400), "red", "blue"), (8, (300, 400), "blue", "red")],
)
def test_the_photo_is_turned_the_way_up_its_exif_note_says(
    orientation: int, size: tuple[int, int], top: str, bottom: str
) -> None:
    cleaned = photos.clean(kit.jpeg(orientation=orientation))
    large = kit.opened(cleaned.large)
    assert large.size == size == cleaned.large_size
    assert colour(large, 20, 20) == top
    assert colour(large, 20, size[1] - 20) == bottom
    assert kit.opened(cleaned.small).getexif().get(0x0112) is None


@pytest.mark.parametrize("stored", [(4000, 3000), (8160, 6120)], ids=["12mp", "50mp"])
def test_a_big_photo_is_turned_too(stored: tuple[int, int]) -> None:
    """A big photo is made small first (a JPEG decoded smaller) and turned after, so test
    ones bigger than the copies: the shrink works on the photo as it's stored, sideways,
    and the turned photo still gets the large copy's full size."""
    cleaned = photos.clean(kit.jpeg(*stored, orientation=6))
    large = kit.opened(cleaned.large)
    assert large.size == cleaned.large_size == (1200, 1600)
    assert colour(large, 20, 20) == "red"
    assert colour(large, 20, 1580) == "blue"


@pytest.mark.parametrize("size", [(400, 300), (4000, 3000)], ids=["small", "shrunk"])
def test_a_colour_profile_is_used_then_dropped(size: tuple[int, int]) -> None:
    profile = kit.wide_gamut_profile()
    green = (60, 160, 90)
    # What those numbers are in sRGB, under that profile: far from the numbers themselves.
    expected = ImageCms.profileToProfile(
        Image.new("RGB", (1, 1), green),
        ImageCms.ImageCmsProfile(io.BytesIO(profile)),
        ImageCms.createProfile("sRGB"),
    )
    assert expected is not None
    in_srgb = expected.getpixel((0, 0))
    assert isinstance(in_srgb, tuple) and abs(in_srgb[0] - green[0]) > 40

    def cleaned(**save: Any) -> photos.Cleaned:
        out = io.BytesIO()
        Image.new("RGB", size, green).save(out, "JPEG", quality=95, **save)
        return photos.clean(out.getvalue())

    def near(found: Any, wanted: Any) -> bool:
        return all(abs(a - b) <= 4 for a, b in zip(found, wanted, strict=True))

    plain = cleaned()  # no profile: the numbers are taken as they are
    tagged = cleaned(icc_profile=profile)
    assert near(kit.opened(plain.large).getpixel((200, 150)), green)
    assert tagged.large_size == (min(size[0], 1600), min(size[1], 1200))
    for data in (tagged.large, tagged.small):
        saved = kit.opened(data)
        assert near(saved.getpixel((saved.width // 2, saved.height // 2)), in_srgb)
        assert "icc_profile" not in saved.info and b"ICC_PROFILE" not in data


def profile_reaching_the_converter(
    monkeypatch: pytest.MonkeyPatch, profile: bytes
) -> tuple[list[int], photos.Cleaned]:
    """Cleans a photo carrying this profile; returns the sizes of the profiles that reached
    littlecms (`profileToProfile`) and the result."""
    reached: list[int] = []
    real = ImageCms.profileToProfile

    def spy(image: Image.Image, source: Any, *args: Any, **kwargs: Any) -> Any:
        reached.append(1)
        return real(image, source, *args, **kwargs)

    monkeypatch.setattr(photos.ImageCms, "profileToProfile", spy)
    return reached, photos.clean(kit.jpeg(icc_profile=profile))


def test_a_colour_profile_over_1_mb_is_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    big = kit.wide_gamut_profile().ljust(photos.MAX_PROFILE_BYTES + 1, b"\0")
    reached, cleaned = profile_reaching_the_converter(monkeypatch, big)
    assert reached == []  # it never went near littlecms
    assert kit.opened(cleaned.large).size == (400, 300)  # and the photo was still kept
    assert "icc_profile" not in kit.opened(cleaned.large).info


def test_a_colour_profile_of_exactly_1_mb_is_still_used(monkeypatch: pytest.MonkeyPatch) -> None:
    edge = kit.wide_gamut_profile().ljust(photos.MAX_PROFILE_BYTES, b"\0")
    assert photos.MAX_PROFILE_BYTES == 1_048_576
    reached, _ = profile_reaching_the_converter(monkeypatch, edge)
    assert reached == [1]


def test_a_small_colour_profile_is_still_used(monkeypatch: pytest.MonkeyPatch) -> None:
    reached, _ = profile_reaching_the_converter(monkeypatch, kit.wide_gamut_profile())
    assert reached == [1]


def test_a_profile_pillow_cannot_use_is_ignored_not_refused() -> None:
    cleaned = photos.clean(kit.jpeg(icc_profile=b"not really a colour profile"))
    assert "icc_profile" not in kit.opened(cleaned.large).info


@pytest.mark.parametrize("mode", ["CMYK", "L"])
def test_cmyk_and_grey_jpegs_are_taken_big_or_small(mode: str) -> None:
    """JPEGs are decoded at a smaller scale when they'll be shrunk anyway; CMYK (from
    print software) and grey ones work both ways."""
    for size, large_size in (((400, 300), (400, 300)), ((4000, 3000), (1600, 1200))):
        out = io.BytesIO()
        kit.picture(*size).convert(mode).save(out, "JPEG", quality=95)
        cleaned = photos.clean(out.getvalue())
        large = kit.opened(cleaned.large)
        assert large.mode == "RGB" and large.size == cleaned.large_size == large_size
        left = large.getpixel((20, 20))
        right = large.getpixel((large_size[0] - 20, 20))
        if mode == "CMYK":
            assert (colour(large, 20, 20), colour(large, large_size[0] - 20, 20)) == ("red", "blue")
        else:  # red and blue as grey: two different greys, the same in each channel
            assert isinstance(left, tuple) and isinstance(right, tuple)
            assert len(set(left)) == len(set(right)) == 1 and abs(left[0] - right[0]) > 20


def test_see_through_parts_become_white() -> None:
    cleaned = photos.clean(kit.png(see_through=True))
    large = kit.opened(cleaned.large)
    assert large.mode == "RGB"
    assert colour(large, 20, 20) == "white"  # the top half was see-through
    assert colour(large, 20, 280) == "red"
    assert colour(kit.opened(cleaned.small), 5, 5) == "white"


def test_an_animated_image_keeps_its_first_frame() -> None:
    cleaned = photos.clean(kit.animated_webp())
    assert colour(kit.opened(cleaned.large), 50, 50) == "green"


@pytest.mark.parametrize(
    ("sent", "large", "small"),
    [
        ((4000, 3000), (1600, 1200), (208, 156)),
        ((3000, 4000), (1200, 1600), (156, 208)),
        ((400, 300), (400, 300), (208, 156)),  # the large copy is never made bigger
        ((120, 90), (120, 90), (120, 90)),  # nor the list copy
        ((1600, 1600), (1600, 1600), (156, 156)),
    ],
)
def test_both_copies_are_jpegs_of_the_right_size(
    sent: tuple[int, int], large: tuple[int, int], small: tuple[int, int]
) -> None:
    cleaned = photos.clean(kit.jpeg(*sent))
    assert (cleaned.large_size, cleaned.small_size) == (large, small)
    assert kit.opened(cleaned.large).size == large
    assert kit.opened(cleaned.small).size == small
    assert kit.opened(cleaned.small).format == "JPEG"


def test_the_list_copy_is_the_list_square_at_three_times() -> None:
    mockup = Path(__file__).parents[2] / "docs" / "mockups" / "Recipes-Phone.dc.html"
    # The recipe list's photo square in the mockup, at 3x for the sharpest phones.
    assert "width:52px;height:52px" in mockup.read_text().replace(" ", "")
    assert photos.LIST_SIDE == 52 * 3


@pytest.mark.parametrize(
    "sent",
    [kit.gif(), kit.SVG, kit.HEIC, kit.TEXT, kit.jpeg()[:1500], b""],
    ids=["gif", "svg", "heic", "text-named-jpg", "cut-short-jpeg", "empty"],
)
def test_files_that_are_not_a_usable_photo_are_refused(sent: bytes) -> None:
    with pytest.raises(photos.NotAPhoto):
        photos.clean(sent)


def test_a_png_cut_short_is_refused() -> None:
    with pytest.raises(photos.NotAPhoto):
        photos.clean(kit.png()[:-200])


@pytest.mark.parametrize(
    "size",
    [(16_666_667, 3), (10_001, 5000), (50_001, 1000), (20_000, 20_000), (100_000, 100_000)],
)
def test_more_than_50_megapixels_is_refused_before_any_pixel_is_read(size: tuple[int, int]) -> None:
    # 16,666,667 x 3 is 50,000,001 pixels: one more than the limit (cabledrawer 20 Oct).
    with pytest.raises(photos.TooManyPixels):
        photos.clean(kit.png_header_only(*size))


def test_exactly_50_megapixels_is_taken() -> None:
    assert photos.MAX_PIXELS == 10_000 * 5000 == 50_000_000
    assert photos.clean(kit.jpeg(10_000, 5000)).large_size == (1600, 800)


def test_pillows_too_many_pixels_warning_refuses_the_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pillow warns over its limit and refuses over twice it. Its limit is 50 megapixels,
    the same as Mealwright's own check, so there's no real photo in between: the limit is
    lowered here to show the warning alone refuses it."""
    import warnings

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    sent = kit.jpeg(40, 30)  # 1,200 pixels: over the limit, under twice it
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # whatever the filters outside say
        with pytest.raises(photos.TooManyPixels):
            photos.clean(sent)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 2000)
    assert photos.clean(sent).large_size == (40, 30)


PEAK = r"""
import re, sys
from mealwright import photos

def peak():  # the process's own highest memory use so far, in KiB (Linux)
    with open("/proc/self/status") as status:
        return int(re.search(r"VmHWM:\s+(\d+) kB", status.read()).group(1))

data = open(sys.argv[1], "rb").read()
before = peak()
cleaned = photos.clean(data)
print(cleaned.large_size, (peak() - before) // 1024)
"""


def peak_mb(path: Path) -> tuple[str, int]:
    """Cleans the photo in a process of its own: its large copy's size and its peak memory
    less what it had before cleaning, in MB. (VmHWM, not getrusage: that one starts from
    the test runner's own peak.)"""
    import subprocess
    import sys

    assert os.path.getsize(path) < MAX_PHOTO_BYTES
    source = str(Path(photos.__file__).parents[1])
    found = subprocess.run(  # noqa: S603 (fixed command, no user input)
        [sys.executable, "-c", PEAK, str(path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=path.parent,
        env={**os.environ, "PYTHONPATH": source},
        timeout=120,
    ).stdout.split()
    return " ".join(found[:2]), int(found[2])


@pytest.mark.parametrize(("mode", "at_most"), [("RGB", 300), ("RGBA", 500)])
def test_a_50_megapixel_png_is_cleaned_in_a_few_hundred_mb(
    tmp_path: Path, mode: str, at_most: int
) -> None:
    """Made small first, so the full-size picture is in memory once. Before, a 40 MP PNG
    took about 820 MB (RGB) and 950 MB (see-through); now a 50 MP one takes about 260 MB
    and 450 MB (Pillow 13's quick first shrink now applies to see-through pictures too:
    about 32 MB more than Pillow 12, and faster; cabledrawer 20 Oct)."""
    path = tmp_path / "big.png"
    kit.picture(10_000, 5000, mode).save(path, "PNG")
    size, used = peak_mb(path)
    assert size == "(1600, 800)"
    assert used < at_most


@pytest.mark.parametrize("pictures", [1, 2])
def test_a_50_megapixel_jpeg_is_decoded_small(tmp_path: Path, pictures: int) -> None:
    """A JPEG that will be shrunk anyway is decoded at a smaller scale (Pillow's draft
    mode; cabledrawer 20 Oct), so a 50 MP phone photo takes about 46 MB, not the 240 MB a
    full decode takes. The same for a phone's multi-picture JPEG (MPO: 2 pictures)."""
    path = tmp_path / "phone.jpg"
    if pictures == 1:
        path.write_bytes(kit.jpeg(8160, 6120))  # a 50 MP phone camera's size
    else:
        extra = Image.new("RGB", (640, 480), "green")
        kit.picture(8160, 6120).save(path, "MPO", save_all=True, append_images=[extra])
        with Image.open(path) as opened:
            assert opened.format == "MPO"
    size, used = peak_mb(path)
    assert size == "(1600, 1200)"
    assert used < 100


def test_the_pillow_limits_are_set() -> None:
    assert Image.MAX_IMAGE_PIXELS == 50_000_000
    assert photos.FORMATS == ("JPEG", "PNG", "WEBP")


# --- Upload and show ----------------------------------------------------------------------


def test_an_upload_answers_with_the_photo_at_once(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen, kit.jpeg(4000, 3000))
    assert photo == {
        "id": photo["id"],
        "width": 1600,
        "height": 1200,
        "url": f"{API}/recipes/photos/{photo['id']}/large",
        "list_width": 208,
        "list_height": 156,
        "list_url": f"{API}/recipes/photos/{photo['id']}/list",
    }
    saved = record(kitchen, photo["id"])
    assert saved is not None and saved.recipe_id is None and saved.added_by_name == "Tess"
    large, small = photo_files(kitchen, photo["id"])
    assert saved.bytes == large.stat().st_size + small.stat().st_size


def test_the_photo_is_shown_as_a_jpeg_with_safe_headers(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    for copy, size in (("large", (400, 300)), ("list", (208, 156))):
        response = fetch(kitchen, photo, copy)
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["x-content-type-options"] == "nosniff"
        # As every /api answer: the browser's own cache keeps nothing (sync protocol 12).
        assert response.headers["cache-control"] == "no-store"
        assert "img-src 'self' data: blob:" in response.headers["content-security-policy"]
        assert kit.opened(response.content).size == size
        assert metadata(response.content) == {}


def test_only_a_known_copy_can_be_asked_for(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    assert kitchen.get(f"{API}/recipes/photos/{photo['id']}/original").status_code == 422
    assert kitchen.get(f"{API}/recipes/photos/{photo['id']}/..%2F..%2Fx").status_code in {404, 422}


def test_signed_out_nothing_is_shown_or_taken(client: TestClient, kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    with TestClient(client.app, base_url="https://testserver") as stranger:
        assert stranger.get(photo["url"]).status_code == 401
        assert stranger.get(photo["list_url"]).status_code == 401
        assert kit.upload(stranger, kit.jpeg()).status_code == 401
        assert stranger.delete(f"{API}/recipes/photos/{photo['id']}").status_code == 401
    assert len(files_of(kitchen)) == 2


@pytest.mark.parametrize(
    ("sent", "kind"),
    [
        (kit.gif(), "image/gif"),
        (kit.SVG, "image/svg+xml"),
        (kit.HEIC, "image/heic"),
        (kit.TEXT, "image/jpeg"),
        (kit.jpeg()[:1500], "image/jpeg"),
    ],
    ids=["gif", "svg", "heic", "text-named-jpg", "cut-short-jpeg"],
)
def test_refused_uploads_say_so_and_keep_nothing(
    kitchen: TestClient, sent: bytes, kind: str
) -> None:
    response = kit.upload(kitchen, sent, kind)
    assert response.status_code == 422
    assert response.json() == {"detail": NOT_A_PHOTO, "code": "not_a_photo"}
    assert files_of(kitchen) == []


def test_what_it_is_comes_from_the_bytes_not_the_content_type(kitchen: TestClient) -> None:
    assert kit.upload(kitchen, kit.png(), "text/plain").status_code == 201
    assert kit.upload(kitchen, kit.TEXT, "image/png").status_code == 422


def test_too_many_pixels_is_refused(kitchen: TestClient) -> None:
    response = kit.upload(kitchen, kit.png_header_only(10_001, 5000), "image/png")
    assert response.status_code == 422
    assert response.json() == {"detail": TOO_MANY_PIXELS, "code": "too_many_pixels"}
    assert files_of(kitchen) == []


def noise_png(at_least: int) -> bytes:
    """A PNG that can't be squeezed: random pixels."""
    side = int((at_least / 3) ** 0.5) + 16
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    out = io.BytesIO()
    image.save(out, "PNG", compress_level=1)
    return out.getvalue()


def test_a_5_mb_photo_is_taken_by_the_upload_route(kitchen: TestClient) -> None:
    sent = noise_png(5 * 1000 * 1000)
    assert MAX_BODY_BYTES < len(sent) < MAX_PHOTO_BYTES
    photo = kit.uploaded(kitchen, sent)
    assert photo["width"] <= 1600


def test_5_mb_anywhere_else_is_still_too_much(kitchen: TestClient) -> None:
    big = b'{"name": "' + b"x" * (5 * 1000 * 1000) + b'"}'
    for method, path in (
        ("POST", f"{API}/recipes"),
        ("PUT", f"{API}/recipes/1"),
        ("DELETE", f"{API}/recipes/photos/1"),
        ("POST", f"{API}/recipes/photos/1/large"),
        ("POST", f"{API}/recipes/photos/"),
        ("POST", f"{API}/foods"),
    ):
        response = kitchen.request(
            method, path, content=big, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413, (method, path, response.status_code)
        assert response.json()["code"] == "body_too_big", (method, path)


def test_over_15_mb_is_refused_by_its_length_alone(kitchen: TestClient) -> None:
    response = kitchen.post(
        f"{API}/recipes/photos",
        content=iter([b"x" * 1024]),
        headers={"Content-Type": "image/jpeg", "Content-Length": str(MAX_PHOTO_BYTES + 1)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": TOO_BIG, "code": "photo_too_big"}


def test_over_15_mb_is_refused_without_reading_it_all() -> None:
    """The test client reads a whole body before the app sees it, so this talks to the
    body limit directly, the way the server does: one piece at a time."""
    import anyio
    from starlette.requests import Request

    from mealwright.limits import BodyLimitMiddleware

    pieces = MAX_PHOTO_BYTES // 65536 + 40
    asked = 0
    answer: list[Any] = []

    async def route(scope: Any, receive: Any, send: Any) -> None:
        await Request(scope, receive).body()  # what the upload route does
        raise AssertionError("the whole body was read")

    async def receive() -> Any:
        nonlocal asked
        asked += 1
        return {"type": "http.request", "body": b"x" * 65536, "more_body": asked < pieces}

    async def send(message: Any) -> None:
        answer.append(message)

    scope = {"type": "http", "method": "POST", "path": f"{API}/recipes/photos", "headers": []}
    anyio.run(BodyLimitMiddleware(route), scope, receive, send)
    assert answer[0]["status"] == 413
    assert b"photo_too_big" in answer[1]["body"]
    assert asked == MAX_PHOTO_BYTES // 65536 + 1 < pieces
    # Anywhere else, the 4 MiB limit stops it sooner.
    asked, answer[:] = 0, []
    anyio.run(BodyLimitMiddleware(route), {**scope, "path": f"{API}/recipes"}, receive, send)
    assert b"body_too_big" in answer[1]["body"]
    assert asked == MAX_BODY_BYTES // 65536 + 1


def test_over_15_mb_sent_in_pieces_is_refused(kitchen: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_PHOTO_BYTES // 65536 + 2):
            yield b"x" * 65536

    response = kitchen.post(
        f"{API}/recipes/photos", content=chunks(), headers={"Content-Type": "image/jpeg"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": TOO_BIG, "code": "photo_too_big"}
    assert files_of(kitchen) == []


def test_exactly_15_mb_is_still_read(kitchen: TestClient) -> None:
    response = kit.upload(kitchen, b"x" * MAX_PHOTO_BYTES)
    assert response.status_code == 422  # read all the way, then found not to be a photo
    assert response.json()["code"] == "not_a_photo"


# --- Ten waiting at most ----------------------------------------------------------------------


def test_at_most_10_uploads_wait_to_be_saved(kitchen: TestClient) -> None:
    waiting = [kit.uploaded(kitchen, kit.jpeg(40, 30)) for _ in range(10)]
    response = kit.upload(kitchen, kit.jpeg(40, 30))
    assert response.status_code == 409
    assert response.json() == {"detail": WAITING, "code": "too_many_photos_waiting"}
    assert len(files_of(kitchen)) == 20
    # Saving one on a recipe frees a place.
    make(kitchen, "Rasam", photo_id=waiting[0]["id"])
    kit.uploaded(kitchen, kit.jpeg(40, 30))
    assert kit.upload(kitchen, kit.jpeg(40, 30)).status_code == 409
    # So does deleting one.
    assert kitchen.delete(f"{API}/recipes/photos/{waiting[1]['id']}").status_code == 204
    kit.uploaded(kitchen, kit.jpeg(40, 30))


def test_11_uploads_at_once_give_exactly_one_refusal(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each upload takes its place before its photo is worked on, so the 11th is refused
    straight away, not after the work, however they overlap."""
    import threading

    worked: list[int] = []
    real = photos.clean

    def slow(data: bytes) -> photos.Cleaned:
        worked.append(1)
        time.sleep(0.2)  # so all 11 are under way together
        return real(data)

    monkeypatch.setattr(photos, "clean", slow)
    sent = kit.jpeg(40, 30)
    answers: list[Any] = []

    def one() -> None:
        other = TestClient(kitchen.app, base_url="https://testserver")
        other.cookies.update(kitchen.cookies)
        answers.append(kit.upload(other, sent))

    threads = [threading.Thread(target=one) for _ in range(11)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert sorted(a.status_code for a in answers) == [201] * 10 + [409]
    refused = next(a for a in answers if a.status_code == 409)
    assert refused.json() == {"detail": WAITING, "code": "too_many_photos_waiting"}
    assert len(worked) == 10
    assert len(files_of(kitchen)) == 20
    assert kit.upload(kitchen, sent).status_code == 409


def test_an_upload_that_fails_gives_its_place_back(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mealwright.api.v1.photos as route

    for _ in range(9):
        kit.uploaded(kitchen, kit.jpeg(40, 30))
    assert kit.upload(kitchen, kit.TEXT).status_code == 422
    assert kit.upload(kitchen, kit.png_header_only(8001, 5000)).status_code == 422
    real = photos.write

    def broken(*_args: Any, **_kwargs: Any) -> int:
        raise OSError("the disk is full")

    monkeypatch.setattr(photos, "write", broken)
    with pytest.raises(OSError, match="the disk is full"):
        kit.upload(kitchen, kit.jpeg(40, 30))
    monkeypatch.setattr(photos, "write", real)
    assert route._IN_HAND == {}
    kit.uploaded(kitchen, kit.jpeg(40, 30))  # the 10th
    assert kit.upload(kitchen, kit.jpeg(40, 30)).status_code == 409
    assert route._IN_HAND == {}


def test_the_24_hour_clean_up_frees_a_place(kitchen: TestClient) -> None:
    for _ in range(10):
        kit.uploaded(kitchen, kit.jpeg(40, 30))
    assert kit.upload(kitchen, kit.jpeg(40, 30)).status_code == 409
    jobs.purge_removed_ingredients(
        kitchen.app.state.sessionmaker,  # type: ignore[attr-defined]
        utcnow() + timedelta(hours=25),
    )
    kit.uploaded(kitchen, kit.jpeg(40, 30))


# --- Attach, replace, clear on Save ------------------------------------------------------


def test_a_new_recipe_saves_with_its_photo(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    assert recipe["photo"] == photo
    listed = ok(kitchen.get(f"{API}/recipes"))["recipes"][0]
    assert listed["photo"] == photo
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["photo"] == photo
    saved = record(kitchen, photo["id"])
    assert saved is not None and saved.recipe_id == recipe["id"]


def test_nothing_changes_until_save(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    kit.uploaded(kitchen)
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["photo"] is None


def test_saving_again_keeps_the_photo(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    again = ok(save(kitchen, recipe, serves=2))
    assert again["photo"] == photo
    assert fetch(kitchen, photo).status_code == 200


def test_replacing_the_photo_deletes_the_old_one(kitchen: TestClient) -> None:
    old = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=old["id"])
    old_files = photo_files(kitchen, old["id"])
    new = kit.uploaded(kitchen, kit.png())
    saved = ok(save(kitchen, recipe, photo_id=new["id"]))
    assert saved["photo"] == new
    assert record(kitchen, old["id"]) is None
    assert not any(p.exists() for p in old_files)
    assert fetch(kitchen, old).status_code == 404
    assert fetch(kitchen, new).status_code == 200
    assert len(files_of(kitchen)) == 2


def test_clearing_the_photo_deletes_it(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    old_files = photo_files(kitchen, photo["id"])
    assert ok(save(kitchen, recipe, photo_id=None))["photo"] is None
    assert not any(p.exists() for p in old_files)
    assert record(kitchen, photo["id"]) is None
    assert files_of(kitchen) == []


def test_left_out_keeps_the_photo_and_an_explicit_null_removes_it(kitchen: TestClient) -> None:
    """cabledrawer 20 Oct: a save that leaves the photo out keeps it; "Remove photo" sends
    `"photo_id": null`. Both on the same recipe."""
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    files = photo_files(kitchen, photo["id"])
    body = {"name": recipe["name"], "version": recipe["version"]}
    saved = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert saved["photo"] == photo and saved["version"] == recipe["version"] + 1
    assert fetch(kitchen, photo).status_code == 200
    assert all(p.is_file() for p in files) and len(files_of(kitchen)) == 2
    body = {"name": recipe["name"], "version": saved["version"], "photo_id": None}
    removed = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert removed["photo"] is None and record(kitchen, photo["id"]) is None
    assert not any(p.exists() for p in files) and files_of(kitchen) == []
    assert fetch(kitchen, photo).status_code == 404
    # Left out on a new recipe: it has none.
    assert make(kitchen, "Rasam")["photo"] is None


def test_photo_id_null_removes_it_and_a_new_id_replaces_it(kitchen: TestClient) -> None:
    first = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=first["id"])
    second = kit.uploaded(kitchen, kit.png())
    body = {"name": recipe["name"], "version": recipe["version"], "photo_id": second["id"]}
    replaced = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert replaced["photo"] == second and record(kitchen, first["id"]) is None
    body = {"name": recipe["name"], "version": replaced["version"], "photo_id": None}
    assert ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))["photo"] is None
    assert record(kitchen, second["id"]) is None
    assert files_of(kitchen) == []


def test_a_save_that_is_refused_keeps_the_photo(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    ok(save(kitchen, recipe, serves=3))
    # Opened before that save: refused, and nothing changes, files included.
    stale = save(kitchen, recipe, photo_id=None)
    assert stale.status_code == 409
    assert fetch(kitchen, photo).status_code == 200
    assert len(files_of(kitchen)) == 2
    # And a save with a bad line changes nothing either.
    current = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    bad = save(kitchen, current, photo_id=None, lines=[{"words": "x", "food_id": 999_999}])
    assert bad.status_code == 404
    assert fetch(kitchen, photo).status_code == 200


def commit_fails_after_the_photo_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """The next commit fails once a photo has been deleted in the request (the disk is
    full, say), as a commit can after the photo step."""
    from sqlalchemy.orm import Session

    import mealwright.api.v1.photos as route
    from mealwright import recipes

    stepped: list[int] = []
    real_delete, real_commit = recipes.delete_photo, Session.commit

    def delete_photo(db: Session, photo: RecipePhoto) -> None:
        stepped.append(photo.id)
        real_delete(db, photo)

    def commit(self: Session) -> None:
        if stepped:
            stepped.clear()
            raise RuntimeError("the disk is full")
        real_commit(self)

    monkeypatch.setattr(recipes, "delete_photo", delete_photo)
    monkeypatch.setattr(route, "delete_photo", delete_photo)
    monkeypatch.setattr(Session, "commit", commit)


@pytest.mark.parametrize("replace", [True, False], ids=["replaced", "cleared"])
def test_a_save_whose_commit_fails_keeps_the_old_photo_and_its_files(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch, replace: bool
) -> None:
    old = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=old["id"])
    old_files = photo_files(kitchen, old["id"])
    new = kit.uploaded(kitchen, kit.png())
    commit_fails_after_the_photo_step(monkeypatch)
    with pytest.raises(RuntimeError, match="the disk is full"):
        save(kitchen, recipe, photo_id=new["id"] if replace else None)
    kept = record(kitchen, old["id"])
    assert kept is not None and kept.recipe_id == recipe["id"]
    assert all(p.exists() for p in old_files)
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["photo"] == old
    assert fetch(kitchen, old).status_code == 200
    waiting = record(kitchen, new["id"])
    assert waiting is not None and waiting.recipe_id is None
    assert len(files_of(kitchen)) == 4


def test_a_delete_whose_commit_fails_keeps_the_upload_and_its_files(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = kit.uploaded(kitchen)
    files = photo_files(kitchen, photo["id"])
    commit_fails_after_the_photo_step(monkeypatch)
    with pytest.raises(RuntimeError, match="the disk is full"):
        kitchen.delete(f"{API}/recipes/photos/{photo['id']}")
    assert record(kitchen, photo["id"]) is not None
    assert all(p.exists() for p in files)
    assert fetch(kitchen, photo).status_code == 200


def test_a_photo_on_one_recipe_cannot_be_put_on_another(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    first = make(kitchen, "Sambar", photo_id=photo["id"])
    response = kitchen.post(f"{API}/recipes", json={"name": "Rasam", "photo_id": photo["id"]})
    assert response.status_code == 404
    assert response.json() == {"detail": GONE, "code": "not_found"}
    assert ok(kitchen.get(f"{API}/recipes/{first['id']}"))["photo"] == photo


def test_an_unknown_photo_id_is_refused(kitchen: TestClient) -> None:
    for photo_id in (999_999, 0, -1):
        response = kitchen.post(f"{API}/recipes", json={"name": "Rasam", "photo_id": photo_id})
        assert response.status_code == 404
        assert response.json() == {"detail": GONE, "code": "not_found"}
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 0


def test_a_retried_create_attaches_the_photo_once(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    body = {"name": "Sambar", "photo_id": photo["id"]}
    headers = {"Idempotency-Key": "make-sambar-1"}
    first = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    again = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["photo"] == photo
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 1


# --- Deleting an unsaved upload -------------------------------------------------------------


def test_an_unsaved_upload_can_be_deleted(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    assert kitchen.delete(f"{API}/recipes/photos/{photo['id']}").status_code == 204
    assert files_of(kitchen) == []
    assert fetch(kitchen, photo).status_code == 404
    again = kitchen.delete(f"{API}/recipes/photos/{photo['id']}")
    assert again.status_code == 404
    assert again.json() == {"detail": GONE, "code": "not_found"}


def test_a_photo_on_a_recipe_is_not_deleted_that_way(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    response = kitchen.delete(f"{API}/recipes/photos/{photo['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "photo_in_use"
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["photo"] == photo
    assert len(files_of(kitchen)) == 2


# --- Deleting a recipe ----------------------------------------------------------------------


def test_a_deleted_recipe_hides_its_photo_and_undo_brings_it_back(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    change = ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))["change"]
    assert fetch(kitchen, photo).status_code == 404
    assert len(files_of(kitchen)) == 2
    ok(kitchen.post(f"{API}/changes/{change['id']}/undo"))
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["photo"] == photo
    assert fetch(kitchen, photo).status_code == 200


def test_the_files_go_when_the_recipe_is_deleted_for_good(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    keep = make(kitchen, "Rasam", photo_id=kit.uploaded(kitchen)["id"])
    ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    old_files = photo_files(kitchen, photo["id"])
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    jobs.purge_removed_ingredients(factory, utcnow() + timedelta(days=6))
    assert all(p.exists() for p in old_files)
    jobs.purge_removed_ingredients(factory, utcnow() + timedelta(days=8))
    assert not any(p.exists() for p in old_files)
    assert record(kitchen, photo["id"]) is None
    assert fetch(kitchen, keep["photo"]).status_code == 200
    assert len(files_of(kitchen)) == 2


# --- The hourly clean-up --------------------------------------------------------------------


def test_an_upload_no_recipe_took_within_24_hours_is_deleted(kitchen: TestClient) -> None:
    waiting = kit.uploaded(kitchen)
    young = kit.uploaded(kitchen)
    saved = kit.uploaded(kitchen)
    make(kitchen, photo_id=saved["id"])
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            update(RecipePhoto)
            .where(RecipePhoto.id.in_([waiting["id"], saved["id"]]))
            .values(added_at=utcnow() - timedelta(hours=25))
        )
        db.commit()
    waiting_files = photo_files(kitchen, waiting["id"])
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    assert record(kitchen, waiting["id"]) is None
    assert not any(p.exists() for p in waiting_files)
    assert record(kitchen, young["id"]) is not None
    assert fetch(kitchen, saved).status_code == 200  # on a recipe: kept however old
    assert len(files_of(kitchen)) == 4


def test_files_with_no_record_are_deleted_once_a_day_old(kitchen: TestClient) -> None:
    kept = kit.uploaded(kitchen)
    folder = store(kitchen) / "1"
    old_orphan = folder / f"{'a' * 32}.jpg"
    old_temp = folder / ".upload-left-over"
    young_orphan = folder / f"{'b' * 32}-list.jpg"
    not_ours = folder / "notes.txt"
    for path in (old_orphan, old_temp, young_orphan, not_ours):
        path.write_bytes(b"x")
    day_ago = time.time() - 25 * 3600
    for path in (old_orphan, old_temp, not_ours, *photo_files(kitchen, kept["id"])):
        os.utime(path, (day_ago, day_ago))
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    assert not old_orphan.exists() and not old_temp.exists()
    assert young_orphan.exists() and not_ours.exists()
    assert fetch(kitchen, kept).status_code == 200


def test_the_clean_up_makes_no_network_connection(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    def no(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the photo clean-up tried to connect")

    kit.uploaded(kitchen)
    monkeypatch.setattr(socket.socket, "connect", no)
    monkeypatch.setattr(socket, "getaddrinfo", no)
    jobs.purge_removed_ingredients(
        kitchen.app.state.sessionmaker,  # type: ignore[attr-defined]
        utcnow() + timedelta(days=2),
    )
    assert files_of(kitchen) == []


# --- Where the files go ---------------------------------------------------------------------


def test_files_are_in_the_households_own_folder_under_random_names(kitchen: TestClient) -> None:
    first = kit.uploaded(kitchen)
    second = kit.uploaded(kitchen)
    found = files_of(kitchen)
    assert len(found) == 4
    folder = store(kitchen) / "1"
    names = set()
    for path in found:
        assert path.parent == folder
        assert re.fullmatch(r"[0-9a-f]{32}(-list)?\.jpg", path.name)
        names.add(path.name[:32])
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    assert len(names) == 2
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    # The name has nothing to do with the photo's id.
    keys = set()
    for photo in (first, second):
        saved = record(kitchen, photo["id"])
        assert saved is not None
        assert saved.file_key not in {
            str(photo["id"]),
            f"{photo['id']:032x}",
            f"{photo['id']:032d}",
        }
        keys.add(saved.file_key)
    assert keys == names


def test_nothing_is_written_outside_the_households_folder(
    kitchen: TestClient, tmp_path: Path
) -> None:
    def everything() -> set[Path]:
        return {p for p in tmp_path.rglob("*") if p.is_file()}

    before = everything()
    photo = kit.uploaded(kitchen)
    make(kitchen, photo_id=photo["id"])
    new = everything() - before
    folder = store(kitchen) / "1"
    photo_new = {p for p in new if folder in p.parents}
    assert len(photo_new) == 2
    # Anything else new is the database's own files.
    assert all(p.name.startswith("mealwright.db") for p in new - photo_new)


@pytest.mark.parametrize("key", ["../x", "a" * 31, "A" * 32, f"{'a' * 32}/../../b", ""])
def test_a_file_name_mealwright_did_not_make_is_never_used(key: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        photos.paths(tmp_path, 1, key)


def test_a_photo_whose_files_are_missing_is_not_found(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    for path in photo_files(kitchen, photo["id"]):
        path.unlink()
    response = fetch(kitchen, photo)
    assert response.status_code == 404
    assert response.json() == {"detail": GONE, "code": "not_found"}


def test_a_failed_save_after_writing_leaves_no_files(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mealwright.api.v1.photos as route

    def broken(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(route, "lock_household", broken)
    with pytest.raises(RuntimeError):
        kit.upload(kitchen, kit.jpeg())
    assert files_of(kitchen) == []


def test_recipe_rows_and_photo_records_stay_in_step(kitchen: TestClient) -> None:
    photo = kit.uploaded(kitchen)
    recipe = make(kitchen, photo_id=photo["id"])
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        found = db.scalars(select(RecipePhoto)).all()
        assert [(p.recipe_id, p.household_id) for p in found] == [(recipe["id"], 1)]
        assert db.get(Recipe, recipe["id"]) is not None
