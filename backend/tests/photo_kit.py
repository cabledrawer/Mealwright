"""Pictures for the photo tests, made here so no test file is a binary blob."""

import io
import struct
import zlib
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo

API = "/api/v1"

XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/'
    b'22-rdf-syntax-ns#"><rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:creator>Secret Person</dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>"
)
SECRETS = (b"Secret Person", b"SecretCam", b"Model X9", b"2026:10:19", b"Hidden note")


def exif(orientation: int | None = None) -> Image.Exif:
    """Camera, date, a GPS place and (if given) the "this way up" note."""
    data = Image.Exif()
    data[0x010F] = "SecretCam"  # Make
    data[0x0110] = "Model X9"  # Model
    data[0x0132] = "2026:10:19 08:00:00"  # DateTime
    if orientation is not None:
        data[0x0112] = orientation
    gps = data.get_ifd(0x8825)
    gps.update({1: "N", 2: (51.0, 30.0, 12.5), 3: "W", 4: (0.0, 7.0, 39.0)})
    return data


def picture(width: int = 400, height: int = 300, mode: str = "RGB") -> Image.Image:
    """Left half red, right half blue, so turning it is easy to see."""
    image = Image.new(mode, (width, height), "red")
    image.paste(Image.new(mode, (width // 2, height), "blue"), (width // 2, 0))
    return image


def jpeg(
    width: int = 400, height: int = 300, *, orientation: int | None = None, **save: Any
) -> bytes:
    out = io.BytesIO()
    picture(width, height).save(
        out, "JPEG", exif=exif(orientation).tobytes(), xmp=XMP, comment=b"Hidden note", **save
    )
    return out.getvalue()


def png(width: int = 400, height: int = 300, *, see_through: bool = False) -> bytes:
    image = picture(width, height, "RGBA")
    if see_through:
        image.paste(Image.new("RGBA", (width, height // 2), (0, 0, 0, 0)), (0, 0))
    text = PngInfo()
    text.add_text("Author", "Secret Person")
    text.add_text("Comment", "Hidden note", zip=True)
    text.add_itxt("Description", "SecretCam", lang="en")
    out = io.BytesIO()
    image.save(out, "PNG", pnginfo=text, exif=exif().tobytes())
    return out.getvalue()


def webp(width: int = 400, height: int = 300) -> bytes:
    out = io.BytesIO()
    picture(width, height).save(out, "WEBP", exif=exif().tobytes(), xmp=XMP)
    return out.getvalue()


def animated_webp() -> bytes:
    frames = [Image.new("RGB", (200, 100), colour) for colour in ("green", "black", "white")]
    out = io.BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=100)
    return out.getvalue()


def wide_gamut_profile() -> bytes:
    """A colour profile like Adobe RGB (1998): its red, green and blue are wider than
    sRGB's, so the same numbers mean other colours. Pillow can't make one, so it's built
    here, the smallest ICC profile littlecms takes (version 2, three colours and a curve)."""

    def number(value: float) -> bytes:
        return struct.pack(">i", round(value * 65536))

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ " + b"\0" * 4 + number(x) + number(y) + number(z)

    name = b"Wide test RGB\0"
    desc = b"desc" + b"\0" * 4 + struct.pack(">I", len(name)) + name + b"\0" * 78
    curve = b"curv" + b"\0" * 4 + struct.pack(">IH", 1, 0x0233) + b"\0\0"  # gamma 2.2
    white = (0.9642, 1.0, 0.8249)  # D50
    tags = [
        (b"desc", desc),
        (b"wtpt", xyz(*white)),
        (b"rXYZ", xyz(0.60974, 0.31111, 0.01947)),
        (b"gXYZ", xyz(0.20528, 0.62567, 0.06087)),
        (b"bXYZ", xyz(0.14919, 0.06322, 0.74457)),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
        (b"cprt", b"text" + b"\0" * 4 + b"Test only\0"),
    ]
    table, data = b"", b""
    start = 128 + 4 + 12 * len(tags)
    for kind, body in tags:
        body += b"\0" * (-len(body) % 4)
        table += kind + struct.pack(">II", start + len(data), len(body))
        data += body
    header = (
        struct.pack(">I", start + len(data))
        + b"\0" * 4
        + struct.pack(">I", 0x02100000)
        + b"mntrRGB XYZ "
        + b"\0" * 12
        + b"acsp"
        + b"\0" * 28
        + xyz(*white)[8:]
        + b"\0" * 48
    )
    return header + struct.pack(">I", len(tags)) + table + data


def gif() -> bytes:
    out = io.BytesIO()
    picture(40, 30).convert("P").save(out, "GIF")
    return out.getvalue()


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10"/></svg>'
# The start of an iPhone HEIC file: an ISO box saying "heic".
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 200
TEXT = b"Not a photo at all, just words in a file called photo.jpg\n"


def png_header_only(width: int, height: int) -> bytes:
    """A PNG that says it's this big, with almost no pixels: Pillow refuses it on the
    header alone, so no test needs that much memory."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 10))
        + chunk(b"IEND", b"")
    )


def upload(client: TestClient, data: bytes, kind: str = "image/jpeg") -> Any:
    return client.post(f"{API}/recipes/photos", content=data, headers={"Content-Type": kind})


def uploaded(client: TestClient, data: bytes | None = None) -> dict[str, Any]:
    response = upload(client, data if data is not None else jpeg())
    assert response.status_code == 201, response.text
    return dict(response.json())


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image
