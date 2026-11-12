"""Secrets kept encrypted on the server (spec section 7, "Secrets encrypted on the server"; 0.9 O1).

The single sign-on client secret, and each sign-in's refresh token from the identity provider,
are stored in the database only in encrypted form: AES-256-GCM, written as a compact JWE
(`dir` + `A256GCM`, `authlib.jose`). The key is 32 random bytes in a file of its own,
`<data>/secret.key`, made the first time a secret is stored, readable only by Mealwright
(0600). It is never in the database, so a copy of the database alone (a backup sent somewhere,
a file shared by mistake) holds no secret anyone can read.

If the key file is lost, the stored secrets can't be read: an admin types the client secret
again, and single sign-on sessions sign in again. Nothing here logs a secret or its key.
"""

import base64
import contextlib
import os
import secrets
import threading
from pathlib import Path

from authlib.jose import JsonWebEncryption
from authlib.jose.errors import JoseError
from cryptography.exceptions import InvalidTag

KEY_FILE = "secret.key"
_KEY_BYTES = 32  # AES-256
_HEADER = {"alg": "dir", "enc": "A256GCM"}
_jwe = JsonWebEncryption(algorithms=["dir", "A256GCM"])
_lock = threading.Lock()


class SecretUnreadable(Exception):
    """A stored secret can't be read: the key file is missing or another one, or the stored
    text was changed. Carries no part of the secret or the key."""


def _key_path(data_dir: Path) -> Path:
    return data_dir / KEY_FILE


def _read_key(path: Path) -> bytes:
    text = path.read_bytes().strip()
    try:
        key = base64.urlsafe_b64decode(text)
    except ValueError:
        raise SecretUnreadable("the key file isn't one Mealwright wrote") from None
    if len(key) != _KEY_BYTES:
        raise SecretUnreadable("the key file isn't one Mealwright wrote")
    return key


def key(data_dir: Path, make: bool = True) -> bytes:
    """The key, made (0600) on first use when `make` is True. Two processes making it at once
    can't both win, and neither ever sees it empty or half-written (O1 review r1 L5): each
    writes its key whole to a temporary file of its own in the same folder, then links it
    into place, which fails if the key file is already there; the loser reads the winner's.
    (Where the folder can't make links, the whole file is moved into place instead.)"""
    path = _key_path(data_dir)
    with _lock:
        if path.exists():
            return _read_key(path)
        if not make:
            raise SecretUnreadable("there's no key file")
        data_dir.mkdir(parents=True, exist_ok=True)
        new = secrets.token_bytes(_KEY_BYTES)
        temporary = data_dir / f".{KEY_FILE}.{os.getpid()}.{secrets.token_hex(8)}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                os.fchmod(out.fileno(), 0o600)  # whatever the umask
                out.write(base64.urlsafe_b64encode(new) + b"\n")
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, path)  # all or nothing; never over one that's there
            except FileExistsError:
                return _read_key(path)
            except OSError:
                # A data folder that can't make links (some network shares): move the whole
                # file into place instead, unless a key file has appeared meanwhile.
                if path.exists():
                    return _read_key(path)
                os.rename(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
        _sync_folder(data_dir)
        return new


def _sync_folder(folder: Path) -> None:
    """Make the new name last through a power cut, where the system can."""
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def seal(data_dir: Path, plain: str) -> str:
    """`plain`, encrypted: what the database stores."""
    sealed = _jwe.serialize_compact(_HEADER, plain.encode(), key(data_dir))
    return sealed.decode("ascii") if isinstance(sealed, bytes) else str(sealed)


def open_sealed(data_dir: Path, sealed: str) -> str:
    """What `seal` stored, as it was. Raises SecretUnreadable."""
    try:
        found = _jwe.deserialize_compact(sealed.encode("ascii"), key(data_dir, make=False))
        header = found["header"]
        if header.get("alg") != "dir" or header.get("enc") != "A256GCM":
            raise SecretUnreadable("not sealed the way Mealwright seals")
        payload: bytes = found["payload"]
        return payload.decode()
    except SecretUnreadable:
        raise
    except JoseError, InvalidTag, ValueError, KeyError, UnicodeError:
        raise SecretUnreadable("the stored secret can't be read with this key") from None
