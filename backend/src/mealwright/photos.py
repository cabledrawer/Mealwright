"""Recipe photos: cleaned, made small, and kept on this server (cabledrawer 19 Oct).

An upload is read by Pillow, and only JPEG, PNG and WebP are taken, decided by what the
bytes are (never the file name or the Content-Type). Then:

1. The picture is turned the way its EXIF note says is up.
2. It's rebuilt from the pixels alone, so nothing else in the file is kept: no EXIF (camera,
   date, GPS place), XMP, PNG text, thumbnails or colour profile. A colour profile is used
   first, to turn the colours into sRGB. See-through parts become white. An animated image
   keeps its first frame.
3. Two JPEGs are saved: a large copy (longest side at most 1600 px, never made bigger) and
   a list copy (shortest side 156 px: the 52 px square in the recipe list, at 3x).

The uploaded file itself is never kept. The copies go in `photos/<household id>/` in the
data folder, under a random name nobody can guess, written to a temporary file first and
then renamed, so a half-written photo is never served.

When a photo record is deleted, its files are deleted once the database change is
committed (and not at all if it's rolled back). Files with no record, for example after a
crash, are deleted by the hourly job once they're a day old.

Nothing here makes a network connection.
"""

import io
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps
from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

log = logging.getLogger(__name__)

MAX_PIXELS = 40_000_000
LARGE_SIDE = 1600  # longest side of the large copy
LIST_SIDE = 156  # shortest side of the list copy: 52 px at 3x (Recipes-Phone)
QUALITY = 85
FORMATS = ("JPEG", "PNG", "WEBP")
MAX_WAITING = 10  # uploads not saved on a recipe yet, per household (cabledrawer 20 Oct)
WAITING_HOURS = 24  # an upload no recipe took is deleted after this

NOT_A_PHOTO = "That isn't a photo Mealwright can use. Try a JPEG, PNG or WebP."
TOO_MANY_PIXELS = "That photo has too many pixels. Try one under 40 megapixels."
TOO_MANY_WAITING = "Too many photos waiting to be saved. Save or cancel a recipe first."

# Pillow refuses anything over twice this by itself, and only warns over it; while a photo
# is opened that warning is an error too (`_clean`), and the size is also checked by hand
# before any pixel is read.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# One photo at a time: a 40-megapixel picture needs a few hundred MB while it's worked on.
_ONE_AT_A_TIME = threading.Semaphore(1)

_KEY = re.compile(r"^[0-9a-f]{32}$")
_FILE = re.compile(r"^([0-9a-f]{32})(-list)?\.jpg$")
_TEMP_PREFIX = ".upload-"
_DELETE_LATER = "mealwright.photos.delete"
STORE = "mealwright.photos.store"  # Session.info key: where the photo files are (db.py)


class NotAPhoto(Exception):
    pass


class TooManyPixels(Exception):
    pass


@dataclass
class Cleaned:
    large: bytes
    large_size: tuple[int, int]
    small: bytes
    small_size: tuple[int, int]


# --- Cleaning -------------------------------------------------------------------------------


def clean(data: bytes) -> Cleaned:
    """The two cleaned JPEGs made from an upload. Raises NotAPhoto or TooManyPixels."""
    with _ONE_AT_A_TIME:
        return _clean(data)


def _clean(data: bytes) -> Cleaned:
    try:
        with warnings.catch_warnings():
            # Here Pillow's "too many pixels" warning refuses the photo, whatever the
            # warning filters elsewhere say.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(FORMATS)) as opened:
                width, height = opened.size
                if width < 1 or height < 1:
                    raise NotAPhoto
                if width * height > MAX_PIXELS:
                    raise TooManyPixels
                opened.seek(0)  # an animated image keeps its first frame
                if opened.format == "JPEG":
                    # Decode at a smaller scale when the photo is much bigger than needed.
                    opened.draft(opened.mode, _fit((width, height), LARGE_SIDE))
                opened.load()
                icc = opened.info.get("icc_profile")
                picture = _upright(opened)
    except TooManyPixels, NotAPhoto:
        raise
    except Image.DecompressionBombError, Image.DecompressionBombWarning:
        raise TooManyPixels from None
    except Exception:
        # Not one of the three formats, damaged or cut short: Pillow's own reasons vary.
        raise NotAPhoto from None

    rgb = _to_srgb_on_white(picture, icc)
    # Rebuilt from the pixels alone: nothing from the file's own metadata comes along.
    bare = Image.frombytes("RGB", rgb.size, rgb.tobytes())
    large = bare.copy()
    large.thumbnail((LARGE_SIDE, LARGE_SIDE), Image.Resampling.LANCZOS)
    small = bare.resize(_list_size(bare.size), Image.Resampling.LANCZOS)
    return Cleaned(_jpeg(large), large.size, _jpeg(small), small.size)


def _fit(size: tuple[int, int], longest: int) -> tuple[int, int]:
    scale = min(1.0, longest / max(size))
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def _list_size(size: tuple[int, int]) -> tuple[int, int]:
    """Shortest side LIST_SIDE, never made bigger, and never longer than the large copy."""
    scale = min(1.0, LIST_SIDE / min(size), LARGE_SIDE / max(size))
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def _upright(picture: Image.Image) -> Image.Image:
    """Turned the way the EXIF note says. A broken note is ignored, not a reason to refuse."""
    try:
        turned = ImageOps.exif_transpose(picture)
    except Exception:
        turned = None
    # Always a copy: the opened file's own pixels go when it's closed.
    return turned if turned is not None else picture.copy()


def _to_srgb_on_white(picture: Image.Image, icc: bytes | None) -> Image.Image:
    alpha = None
    if picture.has_transparency_data:
        rgba = picture.convert("RGBA")
        alpha = rgba.getchannel("A")
        colour = picture.convert("L") if picture.mode in {"LA", "La"} else rgba.convert("RGB")
    elif picture.mode in {"RGB", "L", "CMYK"}:
        colour = picture
    else:
        colour = picture.convert("RGB")

    rgb = None
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            converted = ImageCms.profileToProfile(
                colour, source, ImageCms.createProfile("sRGB"), outputMode="RGB"
            )
            rgb = converted if converted is not None else None
        except Exception:
            rgb = None  # a profile Pillow can't use: the colours are taken as they are
    if rgb is None:
        rgb = colour.convert("RGB")
    if alpha is not None:
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        white.paste(rgb, mask=alpha)
        rgb = white
    return rgb


def _jpeg(picture: Image.Image) -> bytes:
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=QUALITY, optimize=True)
    return out.getvalue()


# --- Files ------------------------------------------------------------------------------------


def store_of(db: Session) -> Path:
    store = db.info.get(STORE)
    if store is None:  # pragma: no cover (every app session carries it)
        raise RuntimeError("This database session doesn't know where photos are kept.")
    return Path(store)


def household_folder(store: Path, household_id: int) -> Path:
    return store / str(int(household_id))


def paths(store: Path, household_id: int, key: str) -> tuple[Path, Path]:
    """The large and list files for a key. Only a key Mealwright made is accepted, so a
    path can never point outside the household's folder."""
    if not _KEY.match(key):
        raise ValueError("Not a photo file name")
    folder = household_folder(store, household_id)
    return folder / f"{key}.jpg", folder / f"{key}-list.jpg"


def new_key() -> str:
    return secrets.token_hex(16)


def write(store: Path, household_id: int, key: str, cleaned: Cleaned) -> int:
    """Write both copies; returns their size together. Each goes to a temporary file in the
    same folder first and is then renamed, so it appears whole or not at all."""
    folder = household_folder(store, household_id)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    large, small = paths(store, household_id, key)
    written: list[Path] = []
    try:
        for path, data in ((large, cleaned.large), (small, cleaned.small)):
            _write_one(folder, path, data)
            written.append(path)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return len(cleaned.large) + len(cleaned.small)


def _write_one(folder: Path, path: Path, data: bytes) -> None:
    handle, temp = tempfile.mkstemp(prefix=_TEMP_PREFIX, dir=folder)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def remove_files(store: Path, household_id: int, key: str) -> None:
    for path in paths(store, household_id, key):
        path.unlink(missing_ok=True)


# --- Deleting files after the database change is committed -------------------------------


def delete_after_commit(db: Session, household_id: int, keys: Iterable[str]) -> None:
    """Delete these photos' files once this transaction is committed; if it's rolled
    back, they stay."""
    store_of(db)  # fail now, not after the commit, if this session can't find them
    db.info.setdefault(_DELETE_LATER, []).extend((household_id, key) for key in keys)


@event.listens_for(Session, "after_commit")
def _delete_now(db: Session) -> None:
    waiting = db.info.pop(_DELETE_LATER, None)
    if not waiting:
        return
    store = store_of(db)
    for household_id, key in waiting:
        try:
            remove_files(store, household_id, key)
        except Exception:
            # The hourly job deletes files with no record, so it's tried again.
            log.exception("Couldn't delete a photo's files (will try again within the hour)")


@event.listens_for(Session, "after_transaction_end")
def _forget(db: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:  # the whole transaction, not a savepoint
        db.info.pop(_DELETE_LATER, None)


# --- Files with no record ------------------------------------------------------------------


def sweep_files(store: Path, household_id: int, known: set[str], now: float | None = None) -> int:
    """Delete files in the household's folder that no photo record has, once they're
    older than a day (a younger one may belong to an upload still being saved). Returns
    how many went."""
    folder = household_folder(store, household_id)
    if not folder.is_dir():
        return 0
    cutoff = (now if now is not None else time.time()) - WAITING_HOURS * 3600
    gone = 0
    for entry in folder.iterdir():
        match = _FILE.match(entry.name)
        ours = match is not None or entry.name.startswith(_TEMP_PREFIX)
        if not ours or not entry.is_file() or entry.is_symlink():
            continue
        if match is not None and match.group(1) in known:
            continue
        if entry.stat().st_mtime < cutoff:
            entry.unlink(missing_ok=True)
            gone += 1
    return gone
