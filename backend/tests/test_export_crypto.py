"""The export's optional password, the file format (0.9.5; docs/export-format.md, "The encrypted
file"): round trip, wrong password, damage, cut-short, reordered and added chunks, capped
header, nothing in the clear. Costs are small here so the tests are quick; the default cost is
checked to be what the page says."""

import io
import re
import struct
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mealwright import export_crypto as xc

FAST = {"time_cost": 1, "memory_kib": xc.MIN_MEMORY_KIB, "chunk": xc.MIN_CHUNK}
PASSWORD = "lorna's long passphrase"


def _seal(data: bytes, password: str = PASSWORD, **more: object) -> bytes:
    options = {**FAST, **more}
    pieces = [data[i : i + 700] for i in range(0, len(data), 700)]
    return b"".join(xc.encrypt(pieces, password, **options))


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


def test_every_chunk_was_sealed_under_its_own_nonce() -> None:
    """Read from the real output, not from the code's own helper: each chunk opens under the
    nonce for its position (4 zero bytes, then its number), and under no other chunk's."""
    blob = _seal(b"x" * 10_000)
    header = blob[: xc.HEADER_BYTES]
    key = hash_secret_raw(
        xc.secret_bytes(PASSWORD), header[23:39], 1, xc.MIN_MEMORY_KIB, 1, 32, Type.ID
    )
    aes = AESGCM(key)
    chunks = _chunks(blob)
    assert len(chunks) > 3
    for number, chunk in enumerate(chunks):
        last = b"\x01" if number == len(chunks) - 1 else b"\x00"
        data = header + number.to_bytes(8, "big") + last
        aes.decrypt(b"\x00" * 4 + number.to_bytes(8, "big"), chunk, data)  # raises if not
        with pytest.raises(InvalidTag):
            aes.decrypt(b"\x00" * 4 + (number + 1).to_bytes(8, "big"), chunk, data)


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

    out = xc.encrypt(pieces(), PASSWORD, **FAST)
    next(out)  # the header
    next(out)  # the key check
    next(out)  # the first data chunk
    assert made < 10  # the source is read on demand, not all at once


# --- The by-hand snippet in docs/export-format.md is the one that is tested ----------------


def _snippet() -> str:
    page = (Path(__file__).parents[2] / "docs" / "export-format.md").read_text(encoding="utf-8")
    found = re.findall(r"```python\n(.*?)```", page, flags=re.S)
    assert len(found) == 1
    return str(found[0])


def _by_hand(blob: bytes, password: str, tmp_path: Path) -> bytes:
    scope: dict[str, object] = {}
    exec(compile(_snippet(), "export-format.md", "exec"), scope)  # noqa: S102
    source, target = tmp_path / "in.mwenc", tmp_path / "out.zip"
    source.write_bytes(blob)
    scope["open_export"](str(source), str(target), password)  # type: ignore[operator]
    return target.read_bytes()


@pytest.mark.parametrize("size", [0, 1, 65_535, 65_536, 65_537, 200_000])
def test_the_page_snippet_opens_a_file_of_the_real_app_settings(tmp_path: Path, size: int) -> None:
    data = bytes(i % 253 for i in range(size))
    blob = b"".join(xc.encrypt([data], PASSWORD))  # the real cost and chunk size
    assert _by_hand(blob, PASSWORD, tmp_path) == data


def test_the_page_snippet_refuses_a_wrong_password_and_a_cut_file(tmp_path: Path) -> None:
    blob = b"".join(xc.encrypt([b"x" * 70_000], PASSWORD))
    with pytest.raises(InvalidTag):
        _by_hand(blob, "wrong one entirely", tmp_path)
    with pytest.raises(InvalidTag):
        _by_hand(blob[:-30], PASSWORD, tmp_path)


def test_the_page_snippet_has_no_assert_and_works_under_python_O(tmp_path: Path) -> None:
    """With -O every `assert` is dropped: a good file must still open and a hostile header must
    still be refused (so no check may be an assert)."""
    assert "assert" not in _snippet()
    blob = b"".join(xc.encrypt([b"recipes for Sam" * 5000], PASSWORD, **FAST))
    hostile = bytearray(blob)
    hostile[15:19] = (64 * 1024 * 1024).to_bytes(4, "big")  # 64 GiB of memory asked for
    (tmp_path / "good.mwenc").write_bytes(blob)
    (tmp_path / "hostile.mwenc").write_bytes(bytes(hostile))
    (tmp_path / "snippet.py").write_text(_snippet(), encoding="utf-8")
    runner = tmp_path / "run.py"
    runner.write_text(
        "import sys\n"
        "exec(open(sys.argv[1]).read())\n"
        "open_export(sys.argv[2], sys.argv[3], sys.argv[4])\n",
        encoding="utf-8",
    )

    def run(name: str, password: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-O",
                "-I",
                str(runner),
                str(tmp_path / "snippet.py"),
                str(tmp_path / name),
                str(tmp_path / "out.zip"),
                password,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    assert run("good.mwenc", PASSWORD).returncode == 0
    assert (tmp_path / "out.zip").read_bytes() == b"recipes for Sam" * 5000
    bad = run("hostile.mwenc", PASSWORD)
    assert bad.returncode != 0
    assert "costs out of range" in bad.stderr
    assert run("good.mwenc", "wrong password").returncode != 0


KEY: dict[str, Any] = {"time_cost": 1, "memory_kib": xc.MIN_MEMORY_KIB}


# --- One key being made at a time (each takes 64 MiB while it is made) --------------------


def test_two_keys_are_never_made_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    inside = 0
    most = 0
    count = threading.Lock()
    real = xc._key

    def slow(*args: object) -> bytes:
        nonlocal inside, most
        with count:
            inside += 1
            most = max(most, inside)
        time.sleep(0.3)
        with count:
            inside -= 1
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(xc, "_key", slow)
    answers: list[str] = []

    def one() -> None:
        try:
            xc.make_key(PASSWORD, one_at_a_time=True, **KEY)
            answers.append("made")
        except xc.Busy:
            answers.append("busy")

    threads = [threading.Thread(target=one) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert most == 1
    assert answers.count("made") >= 1
    assert answers.count("made") + answers.count("busy") == 6
    xc.make_key(PASSWORD, one_at_a_time=True, **KEY)  # free again


def test_a_busy_refusal_does_no_key_work(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def counted(*_args: object) -> bytes:
        calls.append(1)
        return b"k" * 32

    monkeypatch.setattr(xc, "_key", counted)
    assert xc._MAKING_A_KEY.acquire(blocking=False)
    try:
        with pytest.raises(xc.Busy):
            xc.make_key(PASSWORD, one_at_a_time=True)
    finally:
        xc._MAKING_A_KEY.release()
    assert calls == []


def test_the_place_is_given_back_when_making_the_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_args: object) -> bytes:
        raise MemoryError("no room")

    with monkeypatch.context() as patch:
        patch.setattr(xc, "_key", broken)
        with pytest.raises(MemoryError):
            xc.make_key(PASSWORD, one_at_a_time=True)
    xc.make_key(PASSWORD, one_at_a_time=True, **KEY)


def test_a_file_made_in_two_steps_opens_like_one_made_in_one() -> None:
    sealing = xc.make_key(PASSWORD, **KEY)
    blob = b"".join(xc.encrypt_with([b"in two steps"], sealing, chunk=xc.MIN_CHUNK))
    assert _open(blob) == b"in two steps"
