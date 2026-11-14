"""A fake identity provider for single sign-on tests (0.9 O1), served on a fake network.

Name look-ups and connections are faked in memory, as in test_page_fetch.py: nothing here goes
online. The provider has its own RSA key, a discovery document, a key set (JWKS), a token
endpoint (authorization code with PKCE, and refresh) and a userinfo endpoint. Tests change what
it answers to try bad tokens.
"""

import base64
import contextlib
import json
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from authlib.jose import JsonWebKey, JsonWebToken
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from mealwright import outbound

ISSUER = "https://id.example.org"
ADDRESS = "93.184.216.40"  # public, so no listing is needed
CLIENT_ID = "mealwright"
CLIENT_SECRET = "s3cret-client-secret-for-tests"
KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "k1"})
OTHER_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "k1"})


def sign(claims: dict[str, Any], key: Any = KEY, alg: str = "RS256", kid: str = "k1") -> str:
    """An ID token: `claims` signed with `key`."""
    header = {"alg": alg, "kid": kid}
    token = JsonWebToken([alg]).encode(header, claims, key)
    return token.decode() if isinstance(token, bytes) else str(token)


def unsigned(claims: dict[str, Any]) -> str:
    """A token with `alg: none` and no signature."""

    def part(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}."


def public_jwks() -> dict[str, Any]:
    return {"keys": [KEY.as_dict(is_private=False)]}


@dataclass
class Seen:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FakeProvider:
    issuer: str = ISSUER
    host: str = "id.example.org"
    address: str = ADDRESS
    port: int = 443
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    refresh_tokens: set[str] = field(default_factory=set)
    seen: list[Seen] = field(default_factory=list)
    lookups: list[str] = field(default_factory=list)
    connections: list[tuple[str, int]] = field(default_factory=list)
    # Change these to make the provider misbehave.
    discovery_extra: dict[str, Any] = field(default_factory=dict)
    jwks: dict[str, Any] = field(default_factory=public_jwks)
    userinfo: dict[str, Any] | None = None
    token_override: Callable[[dict[str, Any]], tuple[int, dict[str, Any]]] | None = None
    secret_post_only: bool = False
    # Gives no refresh token at all (a server that gives one only for offline_access, unasked).
    no_refresh_token: bool = False
    # Asked for max_age, says nothing of when the person signed in (no `auth_time`).
    no_auth_time: bool = False
    # Lists offline_access but refuses a sign-in that asks for it: "authorize" sends the
    # browser back with error=invalid_scope; "token" refuses the code (as Keycloak does for
    # a user without its offline_access role).
    refuse_offline: str | None = None
    scopes_asked: list[str] = field(default_factory=list)
    made: int = 0  # codes given so far

    @property
    def base(self) -> str:
        return self.issuer

    def discovery(self) -> dict[str, Any]:
        document = {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "userinfo_endpoint": f"{self.issuer}/userinfo",
            "id_token_signing_alg_values_supported": ["RS256"],
        }
        if self.secret_post_only:
            document["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
        if self.refuse_offline:
            document["scopes_supported"] = ["openid", "profile", "email", "offline_access"]
        return {**document, **self.discovery_extra}

    # --- The browser's part: what the provider's sign-in page would do --------------------

    def sign_in(
        self,
        authorize_url: str,
        sub: str = "user-1",
        extra: dict[str, Any] | None = None,
        id_token: Callable[[dict[str, Any]], str] | None = None,
    ) -> tuple[str, str]:
        """Sign in at the provider: (code, state) for the callback."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(authorize_url).query).items()}
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": sub,
            "aud": query["client_id"],
            "exp": now + 300,
            "iat": now,
            "nonce": query["nonce"],
            "preferred_username": "ayla",
            "name": "Ayla",
            "email": "ayla@example.org",
            "groups": ["mealwright-users"],
            # Asked how fresh the sign-in is (max_age): when it was, as OIDC Core 2 says.
            **({"auth_time": now} if "max_age" in query and not self.no_auth_time else {}),
            **(extra or {}),
        }
        self.scopes_asked.append(query["scope"])
        self.made += 1
        code = f"code-{self.made}"
        self.codes[code] = {
            "offline": "offline_access" in query["scope"].split(),
            "claims": claims,
            "challenge": query["code_challenge"],
            "redirect_uri": query["redirect_uri"],
            "id_token": id_token,
        }
        return code, query["state"]

    # --- The server's part -----------------------------------------------------------------

    def _client_ok(self, headers: dict[str, str], form: dict[str, str]) -> bool:
        if self.secret_post_only:
            return form.get("client_id") == CLIENT_ID and form.get("client_secret") == CLIENT_SECRET
        auth = headers.get("authorization", "")
        if not auth.startswith("Basic "):
            return False
        pair = base64.b64decode(auth[6:]).decode()
        return pair == f"{CLIENT_ID}:{CLIENT_SECRET}"

    def token(self, headers: dict[str, str], form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        if self.token_override is not None:
            return self.token_override(form)
        if not self._client_ok(headers, form):
            return 401, {"error": "invalid_client"}
        if form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") not in self.refresh_tokens:
                return 400, {"error": "invalid_grant"}
            return 200, {"access_token": "at-2", "token_type": "Bearer", "expires_in": 300}
        issued = self.codes.pop(form.get("code", ""), None)
        if issued is None or issued["redirect_uri"] != form.get("redirect_uri"):
            return 400, {"error": "invalid_grant"}
        if issued["offline"] and self.refuse_offline == "token":
            return 400, {
                "error": "not_allowed",
                "error_description": "Offline tokens not allowed for the user or client",
            }
        if create_s256_code_challenge(form.get("code_verifier", "")) != issued["challenge"]:
            return 400, {"error": "invalid_grant"}
        make = issued["id_token"] or sign
        answer = {
            "access_token": "at-1",
            "token_type": "Bearer",
            "id_token": make(issued["claims"]),
            "expires_in": 300,
        }
        if not self.no_refresh_token:
            refresh = f"rt-{len(self.refresh_tokens) + 1}"
            self.refresh_tokens.add(refresh)
            answer["refresh_token"] = refresh
        return 200, answer

    def answer(self, seen: Seen) -> tuple[int, dict[str, Any]]:
        path = urlsplit(seen.path).path
        if (
            seen.method == "GET"
            and path == urlsplit(self.issuer).path + "/.well-known/openid-configuration"
        ):
            return 200, self.discovery()
        if seen.method == "GET" and path.endswith("/jwks"):
            return 200, self.jwks
        if seen.method == "GET" and path.endswith("/userinfo"):
            if self.userinfo is None:
                return 404, {"error": "not_found"}
            return 200, self.userinfo
        if seen.method == "POST" and path.endswith("/token"):
            form = {k: v[0] for k, v in parse_qs(seen.body.decode()).items()}
            return self.token(seen.headers, form)
        return 404, {"error": "not_found"}

    # --- The fake network ------------------------------------------------------------------

    def lookup(self, host: str, port: int) -> list[str]:
        self.lookups.append(host)
        if host != self.host:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [self.address]

    def open_socket(self, address: str, port: int, timeout: float | None) -> socket.socket:
        self.connections.append((address, port))
        if (address, port) != (self.address, self.port):
            raise ConnectionRefusedError(111, "Connection refused")
        client, server = socket.socketpair()
        threading.Thread(target=self._serve, args=(server,), daemon=True).start()
        client.settimeout(timeout)
        return client

    def _serve(self, server: socket.socket) -> None:
        with server:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = server.recv(65536)
                if not chunk:
                    return
                data += chunk
            head, _, body = data.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            headers = {
                k.strip().lower(): v.strip() for k, v in (h.split(":", 1) for h in lines[1:])
            }
            length = int(headers.get("content-length", "0"))
            while len(body) < length:
                chunk = server.recv(65536)
                if not chunk:
                    break
                body += chunk
            method, path, _ = lines[0].split(" ", 2)
            seen = Seen(method, path, headers, body)
            self.seen.append(seen)
            status, reply = self.answer(seen)
            payload = json.dumps(reply).encode()
            out = [
                f"HTTP/1.1 {status} Whatever",
                "Content-Type: application/json",
                f"Content-Length: {len(payload)}",
                "Connection: close",
                "",
                "",
            ]
            with contextlib.suppress(OSError):  # the client stopped reading
                server.sendall("\r\n".join(out).encode("latin-1") + payload)

    def install(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(outbound, "_lookup", self.lookup)
        monkeypatch.setattr(outbound, "_open_socket", self.open_socket)


class FakeTLS:
    """Stands in for the TLS context."""

    def __init__(self) -> None:
        self.names: list[str | None] = []

    def wrap_socket(
        self, sock: socket.socket, server_hostname: str | None = None, **_options: object
    ) -> Any:
        self.names.append(server_hostname)
        return sock
