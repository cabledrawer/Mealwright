"""Single sign-on with the household's own identity provider (OIDC; spec sections 3 and 7, 0.9 O1).

Signing in goes: Mealwright's start page → the provider's sign-in page (in the browser) → back
to Mealwright's `/auth/callback` page with a one-time code → the server swaps the code for
tokens and checks the ID token → a Mealwright sign-in.

**Every request to the provider goes through the outbound gate** under the Single sign-on
switch in Settings → Privacy (`Connection.SINGLE_SIGN_ON`): its discovery document, its keys
(JWKS), the token endpoint (sign-in and refresh) and its userinfo endpoint. With the switch
off nothing is looked up or sent. Each address is checked like a recipe link's
(`mealwright.page_fetch`): a provider on the household's own network must be on "Your own
network" in Settings → Privacy, this server itself and cloud metadata addresses never work,
and a port other than 80 and 443 needs listing. Plain http:// works only for a listed place
(proposed, for cabledrawer).

Authlib is used for its protocol pieces only, never its HTTP clients: PKCE (S256), and
`authlib.jose` / `authlib.oidc.core` to check the ID token's signature against the provider's
keys, and its issuer, audience, expiry and nonce. Only public-key algorithms are accepted, so
an unsigned token (`alg: none`) or one "signed" with HS256 using the public key is refused.

Each sign-in has its own random state, nonce and PKCE verifier, kept in memory for
FLOW_FOR, used once, and bound to the browser that started it by a cookie of its own.

Nothing here logs a token, a code, the client secret or a claim from the provider.
"""

import base64
import hashlib
import ipaddress
import json
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal
from urllib.parse import quote, urlencode, urlsplit

from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from authlib.oidc.core import CodeIDToken

from mealwright import own_network
from mealwright.outbound import (
    Connection,
    OutboundBlocked,
    OutboundFailed,
    OutboundGate,
    OutboundResponse,
)
from mealwright.own_network import OwnNetwork

CONNECTION = Connection.SINGLE_SIGN_ON
FLOW_FOR = 10 * 60  # seconds a sign-in may take at the provider (proposed, for cabledrawer)
MOST_FLOWS = 200  # sign-ins under way at once; the oldest go first
TIME_LIMIT = 20.0  # seconds for each step's requests to the provider, all together
MOST_BYTES = 256 * 1024  # the biggest answer read from the provider
LEEWAY = 60  # seconds of clock difference allowed when checking a token's times
CACHE_FOR = 5 * 60  # seconds the discovery document and keys are reused
# How often a single sign-on sign-in is checked with its refresh token (proposed, for cabledrawer).
CHECK_EVERY = timedelta(hours=1)
RETRY_AFTER = timedelta(minutes=10)
NORMAL_PORTS = (80, 443)
# Public-key signatures only: never "none", never HS* (a shared secret).
ALGORITHMS = [
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
]
_jwt = JsonWebToken(ALGORITHMS)

type Mode = Literal["sign_in", "test"]
type _Address = ipaddress.IPv4Address | ipaddress.IPv6Address

# What went wrong, said to the person signing in (proposed, for cabledrawer).
MESSAGES: dict[str, str] = {
    "not_set_up": "Single sign-on isn’t set up. Ask your household’s admin.",
    "switched_off": (
        "Single sign-on is switched off in Settings → Privacy. Ask your household’s admin."
    ),
    "own_network": (
        "Your sign-in server is on your own network. An admin adds it in Settings → Privacy → "
        "Your own network."
    ),
    "always_blocked": "Mealwright can’t use that address for your sign-in server.",
    "not_https": (
        "Your sign-in server’s address must start with https://, unless it’s on your own "
        "network in Settings → Privacy."
    ),
    "unreachable": "Mealwright couldn’t reach your sign-in server. Try again in a minute.",
    "bad_answer": "Your sign-in server gave an answer Mealwright couldn’t use.",
    "refused": "Your sign-in server’s answer couldn’t be checked, so you weren’t signed in.",
    "expired": "That sign-in took too long or was already used. Try again.",
    "cancelled": "Signing in was cancelled at your sign-in server.",
    "wrong_address": (
        "Open Mealwright at the address single sign-on was set up for, then try again."
    ),
    "secret_unreadable": (
        "Mealwright can’t read the saved client secret. An admin enters it again in "
        "Settings → Sign-in → Single sign-on."
    ),
    "not_let_in": (
        "Your sign-in server doesn’t put you in a group Mealwright lets in. Ask your "
        "household’s admin."
    ),
    "no_account": "There’s no Mealwright account for you yet. Ask your household’s admin.",
    "clash": (
        "There’s already a Mealwright account with your name here, so it wasn’t used. Ask "
        "your household’s admin."
    ),
    "removed": "That account was removed. Ask your household’s admin.",
    "someone_else": (
        "Your account is linked to someone else at your sign-in server. Sign out there and "
        "test again."
    ),
}


class SsoFailed(Exception):
    """Single sign-on didn't work; `code` is a key of MESSAGES. Never carries a token."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    @property
    def message(self) -> str:
        return MESSAGES.get(self.code, MESSAGES["bad_answer"])


# --- The provider ------------------------------------------------------------------------


@dataclass(frozen=True)
class Provider:
    """What the provider's discovery document says, checked."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    # The client secret goes in the Authorization header unless the provider takes only
    # client_secret_post.
    basic_auth: bool = True


@dataclass(frozen=True)
class Client:
    """The household's saved setup, with the secret opened (never stored like this)."""

    household_id: int
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    group_claim: str = "groups"


def tidy_issuer(text: str) -> str | None:
    """The issuer as saved: an http(s) address with a host, no user name, password, query or
    fragment, and no trailing slash. None if it isn't one."""
    text = text.strip()
    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 (raises on a bad port)
    except ValueError:
        return None
    host = parts.hostname
    if (
        parts.scheme not in {"http", "https"}
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "%" in host
        or any(c.isspace() for c in text)
    ):
        return None
    return text.rstrip("/")


class _Cache:
    """Discovery documents and key sets, reused for CACHE_FOR (per issuer)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[tuple[str, str], tuple[float, Any]] = {}

    def get(self, kind: str, key: str) -> Any:
        with self._lock:
            found = self._items.get((kind, key))
            if found is None or found[0] < time.monotonic():
                return None
            return found[1]

    def put(self, kind: str, key: str, value: Any) -> None:
        with self._lock:
            if len(self._items) > 50:
                self._items.clear()
            self._items[(kind, key)] = (time.monotonic() + CACHE_FOR, value)

    def forget(self) -> None:
        with self._lock:
            self._items.clear()


cache = _Cache()


def _addresses(
    gate: OutboundGate,
    household_id: int,
    host: str,
    port: int,
    listed: OwnNetwork,
    deadline: float,
) -> list[_Address]:
    """Every address `host` has, each one checked (like `page_fetch._checked_addresses`)."""
    try:
        literal: _Address | None = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        if own_network.is_localhost(host):
            raise SsoFailed("always_blocked")
        try:
            addresses = gate.look_up(household_id, CONNECTION, host, port, deadline=deadline)
        except OutboundBlocked:
            raise SsoFailed("switched_off") from None
        except OutboundFailed:
            raise SsoFailed("unreachable") from None
        if not addresses:
            raise SsoFailed("unreachable")
    name_listed = literal is None and listed.lists_name(host)
    for address in addresses:
        if own_network.always_blocked(address):
            raise SsoFailed("always_blocked")
        if own_network.needs_listing(address) and not (
            name_listed or listed.lists_address(address)
        ):
            raise SsoFailed("own_network")
    return [own_network.plain(a) for a in addresses]


def _send(
    gate: OutboundGate,
    household_id: int,
    url: str,
    *,
    deadline: float,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> OutboundResponse:
    """One request to the provider, through the gate, after checking where it goes."""
    check_now(gate, household_id)  # nothing at all leaves while it's off
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise SsoFailed("bad_answer") from None
    host = parts.hostname
    if parts.scheme not in {"http", "https"} or not host or "%" in host or port == 0:
        raise SsoFailed("bad_answer")
    with gate.sessions() as db:
        listed = own_network.load(db, household_id)
    addresses = _addresses(gate, household_id, host, port, listed, deadline)
    on_list = listed.lists_name(host) or all(listed.lists_address(a) for a in addresses)
    if parts.scheme != "https" and not on_list:
        raise SsoFailed("not_https")
    if port not in NORMAL_PORTS and not on_list:
        raise SsoFailed("own_network")
    for address in addresses:
        try:
            return gate.get_pinned(
                household_id,
                CONNECTION,
                url,
                address,
                max_bytes=MOST_BYTES,
                accept=lambda kind: "json" in kind,
                deadline=deadline,
                method=method,
                headers={"Accept": "application/json", **(headers or {})},
                body=body,
            )
        except OutboundBlocked as problem:
            if gate.is_allowed(household_id, CONNECTION):
                raise SsoFailed("bad_answer") from problem  # too big, or not JSON
            raise SsoFailed("switched_off") from None
        except OutboundFailed as problem:
            if problem.kind != "unreachable":
                raise SsoFailed("unreachable") from None
    raise SsoFailed("unreachable")


def _json(response: OutboundResponse) -> dict[str, Any]:
    try:
        found = json.loads(response.body)
    except ValueError, UnicodeDecodeError:
        raise SsoFailed("bad_answer") from None
    if not isinstance(found, dict):
        raise SsoFailed("bad_answer")
    return found


def _endpoint(document: dict[str, Any], name: str, required: bool = True) -> str | None:
    value = document.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or tidy_issuer(value.split("?")[0]) is None:
        raise SsoFailed("bad_answer")
    return value


def discover(gate: OutboundGate, household_id: int, issuer: str, deadline: float) -> Provider:
    """The provider's endpoints, from `<issuer>/.well-known/openid-configuration`. Its
    issuer must be exactly the one saved (OIDC Discovery 4.3)."""
    found = cache.get("discovery", issuer)
    if isinstance(found, Provider):
        check_now(gate, household_id)
        return found
    response = _send(
        gate, household_id, f"{issuer}/.well-known/openid-configuration", deadline=deadline
    )
    if response.status != 200:
        raise SsoFailed("unreachable" if response.status >= 500 else "bad_answer")
    document = _json(response)
    if document.get("issuer") != issuer and document.get("issuer") != issuer + "/":
        raise SsoFailed("bad_answer")
    methods = document.get("token_endpoint_auth_methods_supported")
    basic = not (
        isinstance(methods, list)
        and "client_secret_basic" not in methods
        and "client_secret_post" in methods
    )
    provider = Provider(
        issuer=str(document["issuer"]),
        authorization_endpoint=str(_endpoint(document, "authorization_endpoint")),
        token_endpoint=str(_endpoint(document, "token_endpoint")),
        jwks_uri=str(_endpoint(document, "jwks_uri")),
        userinfo_endpoint=_endpoint(document, "userinfo_endpoint", required=False),
        basic_auth=basic,
    )
    cache.put("discovery", issuer, provider)
    return provider


def _keys(
    gate: OutboundGate, household_id: int, provider: Provider, deadline: float, fresh: bool
) -> Any:
    found = None if fresh else cache.get("jwks", provider.jwks_uri)
    if found is not None:
        return found
    response = _send(gate, household_id, provider.jwks_uri, deadline=deadline)
    if response.status != 200:
        raise SsoFailed("unreachable" if response.status >= 500 else "bad_answer")
    try:
        keys = JsonWebKey.import_key_set(_json(response))
    except JoseError, ValueError, TypeError, KeyError:
        raise SsoFailed("bad_answer") from None
    cache.put("jwks", provider.jwks_uri, keys)
    return keys


# --- Checking the ID token -------------------------------------------------------------------


def check_id_token(
    token: str, keys: Any, issuer: str, client_id: str, nonce: str, now: float | None = None
) -> dict[str, Any]:
    """The ID token's claims, once its signature (public-key algorithms only), issuer,
    audience, expiry, issue time, nonce and subject are right. Raises SsoFailed("refused")."""
    try:
        claims = _jwt.decode(
            token,
            keys,
            claims_cls=CodeIDToken,
            claims_options={
                "iss": {"essential": True, "values": [issuer, issuer + "/"]},
                "aud": {"essential": True, "value": client_id},
                "sub": {"essential": True},
                "exp": {"essential": True},
                "iat": {"essential": True},
                "nonce": {"essential": True},
            },
            claims_params={"nonce": nonce, "client_id": client_id},
        )
        claims.validate(now=int(now if now is not None else time.time()), leeway=LEEWAY)
    except JoseError, ValueError, TypeError, KeyError:
        raise SsoFailed("refused") from None
    found = dict(claims)
    subject = found.get("sub")
    # The nonce is checked again here: it must be there and be this sign-in's own.
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or not secrets.compare_digest(str(found.get("nonce", "")), nonce)
    ):
        raise SsoFailed("refused")
    return found


def groups_in(claims: dict[str, Any], claim: str) -> list[str]:
    """The groups a claim lists: a list of names, or one name. Anything else counts as none."""
    value = claims.get(claim)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [g for g in value if isinstance(g, str) and g][:200]


# --- One sign-in ---------------------------------------------------------------------------


@dataclass
class Flow:
    """A sign-in under way: what the callback must match. Kept in memory only."""

    household_id: int
    mode: Mode
    nonce: str
    verifier: str
    binding: str  # the SHA-256 of the browser's own cookie value
    issuer: str
    client_id: str
    redirect_uri: str
    remember: bool = False
    login_id: int | None = None  # a test: the admin who started it
    expires: float = field(default_factory=lambda: time.monotonic() + FLOW_FOR)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Flows:
    """The sign-ins under way, by state. Each is taken once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flows: OrderedDict[str, Flow] = OrderedDict()

    def add(self, flow: Flow) -> str:
        state = secrets.token_urlsafe(32)
        with self._lock:
            at = time.monotonic()
            for old in [k for k, f in self._flows.items() if f.expires <= at]:
                del self._flows[old]
            while len(self._flows) >= MOST_FLOWS:
                self._flows.popitem(last=False)
            self._flows[_hash(state)] = flow
        return state

    def take(self, state: str, binding: str | None) -> Flow:
        """The flow `state` started, from the browser that started it, and only once.
        Raises SsoFailed("expired")."""
        with self._lock:
            flow = self._flows.pop(_hash(state), None)
        if (
            flow is None
            or flow.expires <= time.monotonic()
            or not binding
            or not secrets.compare_digest(flow.binding, _hash(binding))
        ):
            raise SsoFailed("expired")
        return flow

    def __len__(self) -> int:
        return len(self._flows)


@dataclass(frozen=True)
class Started:
    url: str  # the provider's sign-in page, for the browser
    state: str
    binding: str  # the browser's cookie value


def start(
    gate: OutboundGate,
    flows: Flows,
    client: Client,
    *,
    mode: Mode,
    remember: bool = False,
    login_id: int | None = None,
) -> Started:
    """Begin a sign-in: the provider's address to send the browser to."""
    deadline = time.monotonic() + TIME_LIMIT
    provider = discover(gate, client.household_id, client.issuer, deadline)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    binding = secrets.token_urlsafe(32)
    state = flows.add(
        Flow(
            household_id=client.household_id,
            mode=mode,
            nonce=nonce,
            verifier=verifier,
            binding=_hash(binding),
            issuer=client.issuer,
            client_id=client.client_id,
            redirect_uri=client.redirect_uri,
            remember=remember,
            login_id=login_id,
        )
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": client.redirect_uri,
            "scope": "openid profile email groups"
            if client.group_claim == "groups"
            else "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        },
        quote_via=quote,
    )
    joiner = "&" if "?" in provider.authorization_endpoint else "?"
    return Started(
        url=f"{provider.authorization_endpoint}{joiner}{query}", state=state, binding=binding
    )


@dataclass(frozen=True)
class Identity:
    """Who the provider says signed in, checked."""

    issuer: str
    subject: str
    username: str | None
    email: str | None
    name: str | None
    groups: list[str]
    refresh_token: str | None


def _client_auth(
    provider: Provider, client: Client, form: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if provider.basic_auth:
        pair = f"{quote(client.client_id, safe='')}:{quote(client.client_secret, safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
    else:
        form = {**form, "client_id": client.client_id, "client_secret": client.client_secret}
    return headers, form


def _token_request(
    gate: OutboundGate, provider: Provider, client: Client, form: dict[str, str], deadline: float
) -> tuple[int, dict[str, Any]]:
    headers, form = _client_auth(provider, client, form)
    response = _send(
        gate,
        client.household_id,
        provider.token_endpoint,
        deadline=deadline,
        method="POST",
        headers=headers,
        body=urlencode(form).encode(),
    )
    if response.status >= 500:
        raise SsoFailed("unreachable")
    return response.status, _json(response)


def finish(gate: OutboundGate, flow: Flow, client: Client, code: str) -> Identity:
    """Swap the code for tokens and check the ID token. The flow was already taken."""
    if client.issuer != flow.issuer or client.client_id != flow.client_id:
        raise SsoFailed("expired")  # the setup changed while this sign-in was under way
    deadline = time.monotonic() + TIME_LIMIT
    provider = discover(gate, client.household_id, client.issuer, deadline)
    status, answer = _token_request(
        gate,
        provider,
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": flow.redirect_uri,
            "code_verifier": flow.verifier,
        },
        deadline,
    )
    id_token = answer.get("id_token")
    if status != 200 or not isinstance(id_token, str):
        raise SsoFailed("refused")
    try:
        claims = check_id_token(
            id_token,
            _keys(gate, client.household_id, provider, deadline, fresh=False),
            client.issuer,
            client.client_id,
            flow.nonce,
        )
    except SsoFailed:
        # The provider may have new keys: fetch them once more, then decide.
        claims = check_id_token(
            id_token,
            _keys(gate, client.household_id, provider, deadline, fresh=True),
            client.issuer,
            client.client_id,
            flow.nonce,
        )
    if client.group_claim not in claims and provider.userinfo_endpoint:
        access = answer.get("access_token")
        if isinstance(access, str) and access:
            claims = _with_userinfo(gate, provider, client, access, claims, deadline)
    refresh = answer.get("refresh_token")

    def text(name: str) -> str | None:
        value = claims.get(name)
        return value.strip()[:200] if isinstance(value, str) and value.strip() else None

    return Identity(
        issuer=client.issuer,
        subject=str(claims["sub"]),
        username=text("preferred_username"),
        email=text("email"),
        name=text("name"),
        groups=groups_in(claims, client.group_claim),
        refresh_token=refresh if isinstance(refresh, str) and refresh else None,
    )


def _with_userinfo(
    gate: OutboundGate,
    provider: Provider,
    client: Client,
    access: str,
    claims: dict[str, Any],
    deadline: float,
) -> dict[str, Any]:
    """The groups claim from the userinfo endpoint, when the ID token hasn't got it. Only
    for the same subject (OIDC Core 5.3.2); anything wrong there just means no groups."""
    try:
        response = _send(
            gate,
            client.household_id,
            str(provider.userinfo_endpoint),
            deadline=deadline,
            headers={"Authorization": f"Bearer {access}"},
        )
        if response.status != 200:
            return claims
        info = _json(response)
    except SsoFailed as problem:
        if problem.code == "switched_off":
            raise
        return claims
    if info.get("sub") != claims.get("sub") or client.group_claim not in info:
        return claims
    return {**claims, client.group_claim: info[client.group_claim]}


type Refreshed = Literal["ok", "ended", "later"]


def refresh(gate: OutboundGate, client: Client, token: str) -> tuple[Refreshed, str | None]:
    """Use a refresh token: ("ok", the new refresh token or None to keep the old one), or
    ("ended", None) when the provider says the sign-in is over, or ("later", None) when it
    can't be asked just now."""
    deadline = time.monotonic() + TIME_LIMIT
    try:
        provider = discover(gate, client.household_id, client.issuer, deadline)
        status, answer = _token_request(
            gate,
            provider,
            client,
            {"grant_type": "refresh_token", "refresh_token": token},
            deadline,
        )
    except SsoFailed, OutboundBlocked:
        return "later", None
    if status == 200 and isinstance(answer.get("access_token"), str):
        new = answer.get("refresh_token")
        return "ok", new if isinstance(new, str) and new else None
    if status in (400, 401) and answer.get("error") in ("invalid_grant", "unauthorized_client"):
        return "ended", None
    return "later", None


def check_now(gate: OutboundGate, household_id: int) -> None:
    """Raise SsoFailed("switched_off") unless the Single sign-on switch is on."""
    try:
        gate.check_switch(household_id, CONNECTION)
    except OutboundBlocked:
        raise SsoFailed("switched_off") from None
