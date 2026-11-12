"""Secrets kept encrypted on the server (0.9 O1): the key file and sealing."""

import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from mealwright import secret_box
from mealwright.secret_box import SecretUnreadable, open_sealed, seal


def test_seal_and_open(tmp_path: Path) -> None:
    sealed = seal(tmp_path, "the client secret ✓")
    assert "the client secret" not in sealed
    assert sealed.count(".") == 4  # a compact JWE
    assert open_sealed(tmp_path, sealed) == "the client secret ✓"


def test_each_seal_is_different(tmp_path: Path) -> None:
    # A fresh nonce each time: two equal secrets don't look equal in the database.
    assert seal(tmp_path, "same") != seal(tmp_path, "same")


def test_the_key_file_is_made_once_and_readable_only_by_mealwright(tmp_path: Path) -> None:
    path = tmp_path / "secret.key"
    assert not path.exists()
    seal(tmp_path, "x")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    first = path.read_bytes()
    seal(tmp_path, "y")
    assert path.read_bytes() == first


def test_the_key_file_is_0600_whatever_the_umask(tmp_path: Path) -> None:
    import os

    old = os.umask(0)
    try:
        seal(tmp_path, "x")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "secret.key").stat().st_mode) == 0o600


def test_a_missing_data_folder_is_made(tmp_path: Path) -> None:
    data = tmp_path / "not yet"
    assert open_sealed(data, seal(data, "x")) == "x"


def test_another_key_cant_open_it(tmp_path: Path) -> None:
    sealed = seal(tmp_path / "a", "secret")
    seal(tmp_path / "b", "other")
    with pytest.raises(SecretUnreadable) as caught:
        open_sealed(tmp_path / "b", sealed)
    assert "secret" not in str(caught.value).replace("secret can", "")


def test_no_key_file_means_unreadable_and_none_is_made(tmp_path: Path) -> None:
    sealed = seal(tmp_path / "a", "secret")
    with pytest.raises(SecretUnreadable):
        open_sealed(tmp_path / "b", sealed)
    assert not (tmp_path / "b" / "secret.key").exists()


def test_a_changed_seal_is_refused(tmp_path: Path) -> None:
    sealed = seal(tmp_path, "secret")
    head, key, iv, text, tag = sealed.split(".")
    flipped = ("A" if text[0] != "A" else "B") + text[1:]
    with pytest.raises(SecretUnreadable):
        open_sealed(tmp_path, ".".join([head, key, iv, flipped, tag]))
    with pytest.raises(SecretUnreadable):
        open_sealed(tmp_path, "not a seal at all")


def test_a_seal_with_another_algorithm_is_refused(tmp_path: Path) -> None:
    from authlib.jose import JsonWebEncryption

    key = secret_box.key(tmp_path)
    other = JsonWebEncryption().serialize_compact(
        {"alg": "dir", "enc": "A128CBC-HS256"}, b"secret", key
    )
    with pytest.raises(SecretUnreadable):
        open_sealed(tmp_path, other.decode())


def test_a_broken_key_file_is_unreadable(tmp_path: Path) -> None:
    (tmp_path / "secret.key").write_text("not a key\n")
    with pytest.raises(SecretUnreadable):
        seal(tmp_path, "x")


def test_two_threads_making_the_key_agree(tmp_path: Path) -> None:
    keys: list[bytes] = []
    start = threading.Barrier(8)

    def make() -> None:
        start.wait()
        keys.append(secret_box.key(tmp_path))

    threads = [threading.Thread(target=make) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(keys)) == 1


# O1 review r1 L5: the key file is never there empty or half-written.


def test_the_key_file_is_never_seen_empty_while_it_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever file is opened to write the key, `secret.key` itself is either not there
    yet or already whole: a second start arriving at any such moment reads a good key or
    makes its own try, never SecretUnreadable."""
    path = tmp_path / "secret.key"
    real_open = os.open
    seen: list[str] = []

    def watched(file: object, flags: int, *args: object, **kwargs: object) -> int:
        fd = real_open(file, flags, *args, **kwargs)  # type: ignore[arg-type]
        if flags & os.O_CREAT and Path(os.fsdecode(file)).parent == tmp_path:  # type: ignore[arg-type]
            seen.append(Path(os.fsdecode(file)).name)  # type: ignore[arg-type]
            # What another process starting right now would find.
            if path.exists():
                assert len(secret_box._read_key(path)) == 32
        return fd

    monkeypatch.setattr(os, "open", watched)
    made = secret_box.key(tmp_path)
    monkeypatch.undo()
    assert seen, "the key file was written some way this test doesn't watch"
    assert secret_box._read_key(path) == made
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["secret.key"]  # no temporary file left


def test_a_second_start_that_loses_reads_the_winners_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another process puts its key in place just before this one would: this one gives the
    winner's key, changes nothing, and leaves no temporary file."""
    path = tmp_path / "secret.key"
    winner = secret_box.key(tmp_path / "elsewhere")
    real_link = os.link

    def beaten(src: object, dst: object, **kwargs: object) -> None:
        if not path.exists():
            path.write_bytes((tmp_path / "elsewhere" / "secret.key").read_bytes())
        real_link(src, dst, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "link", beaten)
    assert secret_box.key(tmp_path) == winner
    monkeypatch.undo()
    assert secret_box.key(tmp_path) == winner
    assert sorted(p.name for p in tmp_path.iterdir()) == ["elsewhere", "secret.key"]


def test_a_data_folder_that_cant_make_links_still_gets_a_whole_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    made = secret_box.key(tmp_path)
    assert secret_box.key(tmp_path) == made
    assert stat.S_IMODE((tmp_path / "secret.key").stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["secret.key"]


STARTER = """
import sys, time
from pathlib import Path
from mealwright import secret_box
data, at = Path(sys.argv[1]), float(sys.argv[2])
while time.time() < at:
    pass
try:
    print(secret_box.seal(data, "x")[:0] + secret_box.key(data, make=False).hex())
except secret_box.SecretUnreadable as problem:
    print("UNREADABLE", problem)
"""


def test_two_starts_at_once_agree_on_one_whole_key(tmp_path: Path) -> None:
    """Several processes sealing their first secret at the same moment (two servers on one
    data folder, or the server and reset-admin): every one reads the same, whole key."""
    for round_ in range(3):
        data = tmp_path / f"data-{round_}"
        data.mkdir()
        at = time.time() + 1.5
        starts = [
            subprocess.Popen(  # noqa: S603 (this test's own script, run by this Python)
                [sys.executable, "-c", STARTER, str(data), str(at)],
                stdout=subprocess.PIPE,
                text=True,
            )
            for _ in range(6)
        ]
        said = {start.communicate(timeout=60)[0].strip() for start in starts}
        assert len(said) == 1, said
        key = said.pop()
        assert len(bytes.fromhex(key)) == 32
        assert secret_box.key(data, make=False).hex() == key
        assert [p.name for p in data.iterdir()] == ["secret.key"]
