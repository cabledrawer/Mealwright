"""The export's optional password, the file format (0.9.5; docs/export-format.md, "The encrypted
file"): round trip, wrong password, damage, cut-short, reordered and added chunks, capped
header, nothing in the clear. Costs are small here so the tests are quick; the default cost is
checked to be what the page says."""

import io
import struct
from collections.abc import Iterator

import pytest

from mealwright import export_crypto as xc

FAST = {"time_cost": 1, "memory_kib": xc.MIN_MEMORY_KIB, "chunk": xc.MIN_CHUNK}
PASSWORD = "lorna's long passphrase"


def _seal(data: bytes, password: str = PASSWORD, **more: object) -> bytes:
    options = {**FAST, **more}
    pieces = [data[i : i + 700] for i in range(0, len(data), 700)]
    return b"".join(xc.encrypt(pieces, password, **options))  # type: ignore[arg-type]


def _open(blob: bytes, password: str = PASSWORD) -> bytes:
    return b"".join(xc.decrypt(io.BytesIO(blob), password))


def _chunks(blob: bytes, chunk: int = xc.MIN_CHUNK) -> list[bytes]:
    body = blob[xc.HEADER_BYTES :]
    first = len(xc._KEY_CHECK) + xc.TAG_BYTES
    out = [body[:first]]
    rest = body[first:]
    size = chunk + xc.TAG_BYTES
    out += [rest[i : i + size] for i in range(0, len(rest), size)]
    return out


def _join(blob: bytes, chunks: list[bytes]) -> bytes:
    return blob[: xc.HEADER_BYTES] + b"".join(chunks)


@pytest.mark.parametrize("size", [0, 1, 1023, 1024, 1025, 2048, 5000, 70_000])
def test_every_size_round_trips(size: int) -> None:
    data = bytes(i % 251 for i in range(size))
    assert _open(_seal(data)) == data


def test_the_file_shows_nothing_of_the_zip_or_the_password() -> None:
    data = b"PK\x03\x04 recipes for Noor " * 200
    blob = _seal(data)
    assert blob.startswith(xc.MAGIC)
    assert b"PK\x03\x04" not in blob
    assert b"Noor" not in blob
    assert PASSWORD.encode() not in blob


def test_two_files_of_the_same_data_and_password_differ() -> None:
    assert _seal(b"same") != _seal(b"same")


def test_no_nonce_repeats_in_one_file() -> None:
    blob = _seal(b"x" * 10_000)
    assert len({xc._nonce(i) for i in range(len(_chunks(blob)))}) == len(_chunks(blob))


def test_a_wrong_password_says_so_and_gives_nothing() -> None:
    blob = _seal(b"secret recipes")
    with pytest.raises(xc.CantOpen) as error:
        _open(blob, "not the right one")
    assert str(error.value) == xc.WRONG_WORDS


def test_the_same_letters_made_two_ways_open_the_same_file() -> None:
    blob = _seal(b"data", "café au lait")  # é as one letter
    assert _open(blob, "café au lait") == b"data"  # e and an accent


def test_a_changed_byte_anywhere_is_noticed() -> None:
    blob = _seal(b"q" * 3000)
    for where in (xc.HEADER_BYTES - 1, xc.HEADER_BYTES + 3, xc.HEADER_BYTES + 60, len(blob) - 1):
        bad = bytearray(blob)
        bad[where] ^= 1
        with pytest.raises(xc.CantOpen) as error:
            _open(bytes(bad))
        assert str(error.value) in {xc.DAMAGED, xc.WRONG_WORDS, xc.NOT_ENCRYPTED}


def test_a_changed_chunk_after_the_first_says_damaged() -> None:
    blob = _seal(b"q" * 3000)
    chunks = _chunks(blob)
    chunks[2] = bytes([chunks[2][0] ^ 1]) + chunks[2][1:]
    with pytest.raises(xc.CantOpen) as error:
        _open(_join(blob, chunks))
    assert str(error.value) == xc.DAMAGED


def test_a_changed_header_cost_is_noticed() -> None:
    blob = _seal(b"data")
    fields = list(struct.unpack(">8sBBBIII16sI", blob[: xc.HEADER_BYTES]))
    fields[4] = 2  # one more pass
    forged = struct.pack(">8sBBBIII16sI", *fields) + blob[xc.HEADER_BYTES :]
    with pytest.raises(xc.CantOpen):
        _open(forged)


def test_a_cut_short_file_says_damaged_at_every_length() -> None:
    blob = _seal(b"z" * 2500)
    for cut in range(xc.HEADER_BYTES + 1, len(blob)):
        with pytest.raises(xc.CantOpen) as error:
            _open(blob[:cut])
        assert str(error.value) in {xc.DAMAGED, xc.WRONG_WORDS}, cut


def test_cut_at_a_chunk_boundary_is_noticed() -> None:
    blob = _seal(b"z" * 3000)
    chunks = _chunks(blob)
    with pytest.raises(xc.CantOpen) as error:
        _open(_join(blob, chunks[:-1]))
    assert str(error.value) == xc.DAMAGED


def test_a_dropped_middle_chunk_is_noticed() -> None:
    blob = _seal(b"z" * 4000)
    chunks = _chunks(blob)
    with pytest.raises(xc.CantOpen) as error:
        _open(_join(blob, chunks[:2] + chunks[3:]))
    assert str(error.value) == xc.DAMAGED


def test_swapped_chunks_are_noticed() -> None:
    blob = _seal(b"z" * 4000)
    chunks = _chunks(blob)
    chunks[1], chunks[2] = chunks[2], chunks[1]
    with pytest.raises(xc.CantOpen) as error:
        _open(_join(blob, chunks))
    assert str(error.value) == xc.DAMAGED


def test_a_repeated_chunk_is_noticed() -> None:
    blob = _seal(b"z" * 4000)
    chunks = _chunks(blob)
    with pytest.raises(xc.CantOpen):
        _open(_join(blob, [*chunks[:2], chunks[1], *chunks[2:]]))


def test_bytes_added_at_the_end_are_noticed() -> None:
    blob = _seal(b"z" * 2000)
    for extra in (b"\x00", b"\x00" * 16, b"\x00" * 5000):
        with pytest.raises(xc.CantOpen):
            _open(blob + extra)


def test_a_file_that_isnt_one_is_refused_in_plain_words() -> None:
    for junk in (b"", b"PK\x03\x04" + b"\x00" * 100, b"MWEXPORT", b"x" * 500):
        with pytest.raises(xc.CantOpen) as error:
            _open(junk)
        assert str(error.value) == xc.NOT_ENCRYPTED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (4, xc.MAX_TIME_COST + 1),
        (4, 0),
        (5, xc.MAX_MEMORY_KIB + 1),
        (5, 64 * 1024 * 1024),  # 64 GiB
        (5, 1),
        (6, xc.MAX_LANES + 1),
        (6, 0),
        (8, xc.MAX_CHUNK + 1),
        (8, 0),
        (1, 2),  # a version we don't know
        (2, 2),  # another key derivation
        (3, 2),  # another cipher
    ],
)
def test_a_hostile_header_is_refused_before_any_work(field: int, value: int) -> None:
    blob = _seal(b"data")
    fields = list(struct.unpack(">8sBBBIII16sI", blob[: xc.HEADER_BYTES]))
    fields[field] = value
    forged = struct.pack(">8sBBBIII16sI", *fields) + blob[xc.HEADER_BYTES :]
    with pytest.raises(xc.CantOpen) as error:
        _open(forged)
    assert str(error.value) == xc.NOT_ENCRYPTED


def test_what_a_new_file_asks_for_is_what_the_page_says() -> None:
    blob = b"".join(xc.encrypt([b"data"], PASSWORD))
    magic, version, kdf, cipher, t, m, p, salt, chunk = struct.unpack(
        ">8sBBBIII16sI", blob[: xc.HEADER_BYTES]
    )
    assert (magic, version, kdf, cipher) == (b"MWEXPORT", 1, 1, 1)
    assert (t, m, p, chunk) == (3, 65536, 1, 65536)
    assert len(salt) == 16
    assert xc.HEADER_BYTES == 43
    assert _open(blob) == b"data"


def test_it_streams_in_pieces_and_never_holds_the_whole_file() -> None:
    made = 0

    def pieces() -> Iterator[bytes]:
        nonlocal made
        for _ in range(100):
            made += 1
            yield b"\x07" * 1024

    out = xc.encrypt(pieces(), PASSWORD, **FAST)  # type: ignore[arg-type]
    next(out)  # the header
    next(out)  # the key check
    next(out)  # the first data chunk
    assert made < 10  # the source is read on demand, not all at once
