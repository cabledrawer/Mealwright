"""Secrets kept encrypted on the server (0.9 O1): the key file and sealing."""

import stat
import threading
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
