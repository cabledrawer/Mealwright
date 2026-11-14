"""The export's optional password (0.9.5, cabledrawer 13 Nov; the format: docs/export-format.md,
"The encrypted file", encryption format 1).

With a password the export zip is sent encrypted, in chunks, so a big export (photos) is never
held in memory. Without one nothing here runs and the file stays a plain zip.

- Key: Argon2id (`argon2-cffi`'s low-level call) from the password and a random 16-byte salt;
  the cost goes in the file's header, so a later version can raise it. 64 MiB, 3 passes,
  1 lane: about 0.2 s on a desktop (measured); on a Raspberry Pi 4 about 1 to 2 s (estimated, not
  measured; docs/export-format.md).
- Cipher: AES-256-GCM (`cryptography`). The nonce of each chunk is its position (a counter), so
  none repeats under one key, and the key is new for every file (new salt). Each chunk's
  additional authenticated data is the whole header, its position and a "last chunk" byte, so
  a chunk can't be moved, dropped or added, the file can't be cut short or have bytes added
  after it, and the header can't be changed, without the reader noticing.
- Chunk 0 is a short fixed "key check": when it fails to open the password is wrong (or the
  header was changed); when a later chunk fails the file is damaged.

Nothing here logs or keeps a password or key, and nothing compares a secret with `==`.
The reader (`decrypt`) is for the tests and for whoever brings the data back in; the header's
cost numbers are capped there, so a hostile file can't ask for gigabytes or hours.
"""

import secrets
import struct
import threading
import unicodedata
from collections.abc import Iterable, Iterator
from typing import BinaryIO

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MWEXPORT"
VERSION = 1
KDF_ARGON2ID = 1
CIPHER_AES_256_GCM = 1

# What a new file asks for.
TIME_COST = 3
MEMORY_KIB = 64 * 1024
LANES = 1
CHUNK = 64 * 1024  # plaintext bytes per chunk (the last one may be shorter)

# What a reader accepts from a header (so a hostile file can't ask for the moon).
MAX_TIME_COST = 10
MAX_MEMORY_KIB = 256 * 1024
MAX_LANES = 4
MIN_MEMORY_KIB = 8 * 1024
MAX_CHUNK = 1024 * 1024
MIN_CHUNK = 1024

PASSWORD_LEAST = 8
PASSWORD_MOST = 1024

SALT_BYTES = 16
TAG_BYTES = 16
_KEY_CHECK = b"mealwright export"
_HEADER = struct.Struct(">8sBBBIII16sI")  # magic, version, kdf, cipher, t, m, p, salt, chunk
HEADER_BYTES = _HEADER.size

WRONG_WORDS = "That password doesn’t open this file."
DAMAGED = "This file is damaged or cut short, so it can’t be opened."
NOT_ENCRYPTED = "That isn’t a Mealwright encrypted export."


class CantOpen(ValueError):
    """The file can't be opened; the message is plain words and says nothing about the file's
    insides or the password."""


SUFFIX = ".mwenc"  # the encrypted file's name: mealwright-export-<day>.zip.mwenc


def secret_text(password: str) -> str:
    """The password in Unicode NFC, so the same typed letters give the same key whichever way a
    keyboard made them (and its length is counted the same way)."""
    return unicodedata.normalize("NFC", password)


def secret_bytes(password: str) -> bytes:
    """The password as the bytes the key is made from: NFC, then UTF-8."""
    return secret_text(password).encode("utf-8")


def _key(password: bytes, salt: bytes, time_cost: int, memory_kib: int, lanes: int) -> bytes:
    return hash_secret_raw(password, salt, time_cost, memory_kib, lanes, hash_len=32, type=Type.ID)


def _nonce(index: int) -> bytes:
    return b"\x00\x00\x00\x00" + index.to_bytes(8, "big")


def _aad(header: bytes, index: int, last: bool) -> bytes:
    return header + index.to_bytes(8, "big") + (b"\x01" if last else b"\x00")


BUSY = "An export is being made. Try again in a moment."


class Busy(Exception):
    """An encrypted export is already being made (the key costs 64 MiB of memory each)."""


_ONE_AT_A_TIME = threading.Lock()


class OneAtATime:
    """Holds the one place for an encrypted export. Taken with `take()` (which raises `Busy`
    at once rather than wait) before the export is built; given back by `release()`, which may
    be called any number of times, by whichever of these happens first: the stream ends, it
    fails, it is closed (the client went away), or it is dropped."""

    def __init__(self) -> None:
        self._held = False  # first, so a refused one has nothing to give back
        self._mine = threading.Lock()
        if not _ONE_AT_A_TIME.acquire(blocking=False):
            raise Busy(BUSY)
        self._held = True

    def release(self) -> None:
        with self._mine:
            if not self._held:
                return
            self._held = False
        _ONE_AT_A_TIME.release()

    def __del__(self) -> None:
        self.release()

    def stream(self, pieces: Iterator[bytes]) -> Iterator[bytes]:
        return _Held(self, pieces)


class _Held:
    """The stream, which gives the place back as it ends, fails or is closed or dropped (a
    generator that never started would never run its own `finally`, so this is a class)."""

    def __init__(self, guard: OneAtATime, pieces: Iterator[bytes]) -> None:
        self._guard = guard
        self._pieces = pieces

    def __iter__(self) -> _Held:
        return self

    def __next__(self) -> bytes:
        try:
            return next(self._pieces)
        except BaseException:  # the end, or a failure: either way the place is free
            self.close()
            raise

    def close(self) -> None:
        close = getattr(self._pieces, "close", None)
        try:
            if close:
                close()
        finally:
            self._guard.release()

    def __del__(self) -> None:
        self._guard.release()


def encrypt(
    pieces: Iterable[bytes],
    password: str,
    *,
    time_cost: int = TIME_COST,
    memory_kib: int = MEMORY_KIB,
    lanes: int = LANES,
    chunk: int = CHUNK,
    salt: bytes | None = None,
) -> Iterator[bytes]:
    """The encrypted file, piece by piece, from the plain pieces (any sizes). At most two
    chunks are held at a time. (The cost, chunk size and salt are parameters for the tests.)"""
    salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    header = _HEADER.pack(
        MAGIC, VERSION, KDF_ARGON2ID, CIPHER_AES_256_GCM, time_cost, memory_kib, lanes, salt, chunk
    )
    cipher = AESGCM(_key(secret_bytes(password), salt, time_cost, memory_kib, lanes))
    yield header
    yield cipher.encrypt(_nonce(0), _KEY_CHECK, _aad(header, 0, False))
    index = 1
    buffer = bytearray()
    held: bytes | None = None  # a full chunk waits until we know whether it is the last
    for piece in pieces:
        buffer += piece
        while len(buffer) >= chunk:
            if held is not None:
                yield cipher.encrypt(_nonce(index), held, _aad(header, index, False))
                index += 1
            held = bytes(buffer[:chunk])
            del buffer[:chunk]
    if held is not None and buffer:
        yield cipher.encrypt(_nonce(index), held, _aad(header, index, False))
        index += 1
        held = None
    final = held if held is not None else bytes(buffer)  # may be empty, never missing
    yield cipher.encrypt(_nonce(index), final, _aad(header, index, True))


def decrypt(source: BinaryIO, password: str) -> Iterator[bytes]:
    """The plain pieces of an encrypted file. Raises `CantOpen` (one plain message each) for
    a file that isn't one, a wrong password, or a damaged or cut-short file.

    The pieces are handed on as each chunk is checked; the whole file is good only when the
    iterator ends without raising, so a caller keeps them aside (a temporary file) and uses them
    only then."""
    raw = source.read(HEADER_BYTES)
    if len(raw) != HEADER_BYTES:
        raise CantOpen(NOT_ENCRYPTED)
    magic, version, kdf, cipher_id, t, m, p, salt, chunk = _HEADER.unpack(raw)
    if magic != MAGIC or version != VERSION or kdf != KDF_ARGON2ID or cipher_id != 1:
        raise CantOpen(NOT_ENCRYPTED)
    if not (
        1 <= t <= MAX_TIME_COST
        and MIN_MEMORY_KIB <= m <= MAX_MEMORY_KIB
        and 1 <= p <= MAX_LANES
        and MIN_CHUNK <= chunk <= MAX_CHUNK
    ):
        raise CantOpen(NOT_ENCRYPTED)
    cipher = AESGCM(_key(secret_bytes(password), salt, t, m, p))
    size = chunk + TAG_BYTES

    def read() -> bytes:
        return source.read(size)

    try:
        first = source.read(len(_KEY_CHECK) + TAG_BYTES)
        try:
            ok = cipher.decrypt(_nonce(0), first, _aad(raw, 0, False))
        except InvalidTag:
            raise CantOpen(WRONG_WORDS) from None
        if ok != _KEY_CHECK:  # pragma: no cover (the tag already vouched for it)
            raise CantOpen(DAMAGED)
        index = 1
        current = read()
        while True:
            following = read() if current else b""
            last = not following
            if len(current) < TAG_BYTES:
                raise CantOpen(DAMAGED)  # cut short in the middle of a chunk, or no last chunk
            try:
                yield cipher.decrypt(_nonce(index), current, _aad(raw, index, last))
            except InvalidTag:
                raise CantOpen(DAMAGED) from None
            if last:
                return
            current = following
            index += 1
    except OSError:
        raise CantOpen(DAMAGED) from None
