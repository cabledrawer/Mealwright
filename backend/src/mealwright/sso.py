"""Single sign-on with the household's own identity provider (OIDC; spec sections 3 and 7, 0.9 O1).

Signing in goes: Mealwright's start page → the provider's sign-in page (in the browser) → back
to Mealwright's `/auth/callback` page with a one-time code → the server swaps the code for
tokens and checks the ID token → a Mealwright sign-in.

**Every request to the provider goes through the outbound gate** under the Single sign-on
switch in Settings › Outside connections (`Connection.SINGLE_SIGN_ON`): its discovery document,
its keys (JWKS), the token endpoint (sign-in and refresh) and its userinfo endpoint. With the switch
off nothing is looked up or sent. Each address is checked like a recipe link's
(`mealwright.page_fetch`): a provider on the household's own network must be on "Your own
network" in Settings › Outside connections, this server itself and cloud metadata addresses
never work, and a port other than 80 and 443 needs listing. Plain http:// works only for a
listed place (cabledrawer 12 Nov).

Authlib is used for its protocol pieces only, never its HTTP clients: PKCE (S256), and
`authlib.jose` / `authlib.oidc.core` to check the ID token's signature against the provider's
keys, and its issuer, audience, expiry and nonce. Only public-key algorithms are accepted, so
an unsigned token (`alg: none`) or one "signed" with HS256 using the public key is refused.

Each sign-in has its own random state, nonce and PKCE verifier, good for FLOW_FOR and used
once. They are not kept in a table on the server, which strangers could fill to push other
people's sign-ins out (O1 review r1 M2): the caller seals them (`Flow.pack`) into a cookie
for the browser that started, so a sign-in can only be finished by that browser, and nobody
else's start can touch it. A sign-in server that didn't answer isn't asked again for
FAIL_FOR, so each start by someone signed out can't hold a worker for TIME_LIMIT.

Nothing here logs a token, a code, the client secret or a claim from the provider.
"""

import base64
import contextlib
import hashlib
import ipaddress
import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any, Literal
from urllib.parse import quote, urlencode, urlsplit

from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from authlib.oidc.core import CodeIDToken
from joserfc.errors import JoseError as JoserfcError

from mealwright import own_network
from mealwright.names import tidy_one_line
from mealwright.outbound import (
    Connection,
    OutboundBlocked,
    OutboundFailed,
    OutboundGate,
    OutboundResponse,
)
from mealwright.own_network import OwnNetwork

CONNECTION = Connection.SINGLE_SIGN_ON
FLOW_FOR = 10 * 60  # seconds a sign-in may take at the provider (cabledrawer 12 Nov)
MOST_USED = 10_000  # used states remembered at once (see Used)
TIME_LIMIT = 20.0  # seconds for each step's requests to the provider, all together
MOST_BYTES = 256 * 1024  # the biggest answer read from the provider
LEEWAY = 60  # seconds of clock difference allowed when checking a token's times
CACHE_FOR = 5 * 60  # seconds the discovery document and keys are reused
FAIL_FOR = 60  # seconds a sign-in server that didn't answer isn't asked again
# How often a single sign-on sign-in is checked with its refresh token (cabledrawer 12 Nov).
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

# "confirm" (D3, cabledrawer 13 Nov): an admin who signs in only with single sign-on proves it is
# still them, just now, before Delete everything (`confirm_fresh`).
type Mode = Literal["sign_in", "test", "confirm"]
type _Address = ipaddress.IPv4Address | ipaddress.IPv6Address

# What went wrong, said to the person signing in (cabledrawer 12 Nov).
MESSAGES: dict[str, str] = {
    "not_set_up": "Single sign-on isn’t set up. Ask your household’s admin.",
    "switched_off": (
        "Single sign-on is switched off in Settings › Outside connections. Ask your household’s "
        "admin."
    ),
    "own_network": (
        "Your sign-in server is on your own network. An admin adds it in Settings › Outside "
        "connections › Your own network."
    ),
    "always_blocked": "Mealwright can’t use that address for your sign-in server.",
    "not_https": (
        "Your sign-in server’s address must start with https://, unless it’s on your own "
        "network in Settings › Outside connections."
    ),
    "unreachable": "Mealwright couldn’t reach your sign-in server. Try again in a minute.",
    "bad_answer": "Your sign-in server gave an answer Mealwright couldn’t use.",
    "refused": "Your sign-in server’s answer couldn’t be checked, so you weren’t signed in.",
    "expired": "That sign-in took too long or was already used. Try again.",
    "cancelled": "Signing in was cancelled at your sign-in server.",
    "wrong_address": (
        "Open Mealwright at the address single sign-on was set up for, then try again."
    ),
    "secret_unreadable": (  # nosec B105 (words, not a secret)
        "Mealwright can’t read the saved client secret. An admin enters it again in "
        "Settings › Sign-in for everyone."
    ),
    "not_let_in": (
        "Your sign-in server doesn’t put you in a group Mealwright lets in. Ask your "
        "household’s admin."
    ),
    "no_account": "There’s no Mealwright account for you yet. Ask your household’s admin.",
    # 0.9.5 Pe3/M2 (proposed, for cabledrawer): an admin chose "Not someone I know: refuse".
    "not_known": (
        "Your household’s admin doesn’t know this account, so it can’t sign in here. Ask them "
        "if that’s a mistake."
    ),
    "removed": "That account was deleted. Ask your household’s admin.",
    "someone_else": (
        "Your account is linked to someone else at your sign-in server. Sign out there and "
        "test again."
    ),
    # Proposed, for cabledrawer (not among his 12 Nov words above; O1 review r1 H1, r2 note 8):
    "link_gone": "There’s no test waiting to be linked. Test sign-in again.",
    # D3, Delete everything confirmed with single sign-on (proposed, for cabledrawer):
    "not_fresh": (
        "Your sign-in server didn’t say you signed in just now, so Delete everything wasn’t "
        "confirmed. Try again; if it happens every time, your sign-in server may not support "
        "this."
    ),
    "not_you": (
        "That was another account at your sign-in server, not the one linked to you here. "
        "Delete everything wasn’t confirmed."
    ),
}


# What a provider says when it won't give offline_access: at its sign-in page (OAuth's
# invalid_scope), or when the code is swapped (Keycloak's not_allowed, for a user without
# its offline_access role).
OFFLINE_REFUSED = frozenset({"invalid_scope", "not_allowed"})


class SsoFailed(Exception):
    """Single sign-on didn't work; `code` is a key of MESSAGES. Never carries a token."""

    def __init__(self, code: str, *, say_nothing_of_it: bool = False) -> None:
        super().__init__(code)
        self.code = code
        # True when the failure is Mealwright's own (no free place for a look-up), not the
        # sign-in server's: it is never remembered as the server not answering.
        self.say_nothing_of_it = say_nothing_of_it
        # The sign-ins a refusal ended (their open live-update streams are ended by the caller,
        # which has the app's event hub: O2 review r4, finding 4).
        self.ended_sessions: list[int] = []

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
    # The scopes it lists (scopes_supported), or None when it lists none.
    scopes: frozenset[str] | None = None


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
    """Discovery documents and key sets, reused for CACHE_FOR (per issuer), and a failed
    discovery, for FAIL_FOR."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[tuple[str, str], tuple[float, Any]] = {}

    def get(self, kind: str, key: str) -> Any:
        with self._lock:
            found = self._items.get((kind, key))
            if found is None or found[0] < time.monotonic():
                return None
            return found[1]

    def put(self, kind: str, key: str, value: Any, keep_for: float = CACHE_FOR) -> None:
        with self._lock:
            if len(self._items) > 50:
                self._items.clear()
            self._items[(kind, key)] = (time.monotonic() + keep_for, value)

    def forget(self) -> None:
        with self._lock:
            self._items.clear()


cache = _Cache()


_seen_lock = threading.Lock()
_seen: dict[str, list[_Address]] = {}


def remember(host: str, addresses: list[_Address]) -> None:
    """The addresses a sign-in server's name last had (memory only), so "can single sign-on
    start?" can be answered without a look-up (O1 review r3)."""
    with _seen_lock:
        name = host.lower()
        _seen.pop(name, None)  # put back last, so it is the newest
        while len(_seen) >= 50:
            del _seen[next(iter(_seen))]  # the oldest goes, not everything (O1 review r4, 5c)
        _seen[name] = list(addresses)


def remembered(host: str) -> list[_Address] | None:
    with _seen_lock:
        found = _seen.get(host.lower())
        return list(found) if found is not None else None


def forget_remembered() -> None:
    with _seen_lock:
        _seen.clear()


def _screen(
    host: str, literal: _Address | None, addresses: list[_Address], listed: OwnNetwork
) -> None:
    """Raise SsoFailed unless every address may be reached (always-blocked, or private and not
    on Your own network)."""
    name_listed = literal is None and listed.lists_name(host)
    for address in addresses:
        if own_network.always_blocked(address):
            raise SsoFailed("always_blocked")
        if own_network.needs_listing(address) and not (
            name_listed or listed.lists_address(address)
        ):
            raise SsoFailed("own_network")


def _route_refused(
    scheme: str, host: str, port: int, addresses: list[_Address], listed: OwnNetwork
) -> SsoFailed | None:
    """The scheme and port rule of `_send`: plain http, or a port other than the usual two,
    only to a server on Your own network."""
    on_list = listed.lists_name(host) or all(listed.lists_address(a) for a in addresses)
    if scheme != "https" and not on_list:
        return SsoFailed("not_https")
    if port not in NORMAL_PORTS and not on_list:
        return SsoFailed("own_network")
    return None


def issuer_can_be_reached(issuer: str, listed: OwnNetwork) -> bool:
    """True when a request to the sign-in server would get past `_send`'s checks, decided with
    no network look-up: from the address it last had, which this process remembers. Anything
    it can't tell (no address remembered, a bad address, localhost) is False."""
    try:
        parts = urlsplit(issuer)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not host or "%" in host or port == 0:
        return False
    try:
        literal: _Address | None = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    elif own_network.is_localhost(host):
        return False
    else:
        found = remembered(host)
        if not found:
            return False
        addresses = found
    try:
        _screen(host, literal, addresses, listed)
    except SsoFailed:
        return False
    return _route_refused(parts.scheme, host, port, addresses, listed) is None


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
        except OutboundFailed as failure:
            raise SsoFailed("unreachable", say_nothing_of_it=failure.busy) from None
        if not addresses:
            raise SsoFailed("unreachable")
    if literal is None:
        # Remembered before the check, so a name that now answers an address that isn't on
        # Your own network counts as "can't start" and passwords work (O1 review r4, L2).
        remember(host, addresses)
    _screen(host, literal, addresses, listed)
    return [own_network.plain(a) for a in addresses]


def look_up_issuer(gate: OutboundGate, household_id: int, issuer: str, listed: OwnNetwork) -> None:
    """One gated look-up of the sign-in server's name, to fill the memory `issuer_can_be_reached`
    reads (after a restart it is empty). Does nothing for an address that isn't a name, or a
    name whose remembered address already works (one that fails the screen is looked up again,
    so a wrong answer once can't keep passwords open: O1 review r5, finding 1). If the look-up
    fails, is held or is refused, the memory stays empty: "can't tell", and passwords work
    (O1 review r4, finding 1)."""
    try:
        parts = urlsplit(issuer)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return
    if parts.scheme not in {"http", "https"} or not host or "%" in host or port == 0:
        return
    try:
        ipaddress.ip_address(host)
        return  # an address needs no look-up
    except ValueError:
        pass
    if own_network.is_localhost(host) or issuer_can_be_reached(issuer, listed):
        return  # only a remembered answer that works is kept: a bad one is looked at again
    # The name is remembered first; any other failure leaves the memory empty.
    with contextlib.suppress(SsoFailed):
        _addresses(gate, household_id, host, port, listed, time.monotonic() + TIME_LIMIT)


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
    with _slot(household_id):
        return _send_one(
            gate, household_id, url, deadline=deadline, method=method, headers=headers, body=body
        )


def _send_one(
    gate: OutboundGate,
    household_id: int,
    url: str,
    *,
    deadline: float,
    method: str,
    headers: dict[str, str] | None,
    body: bytes | None,
) -> OutboundResponse:
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise SsoFailed("bad_answer") from None
    host = parts.hostname
    if parts.scheme not in {"http", "https"} or not host or "%" in host or port == 0:
        raise SsoFailed("bad_answer")
    _begin_wait()
    with gate.sessions() as db:
        listed = own_network.load(db, household_id)
    addresses = _addresses(gate, household_id, host, port, listed, deadline)
    refused = _route_refused(parts.scheme, host, port, addresses, listed)
    if refused is not None:
        raise refused
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
    except ValueError, UnicodeDecodeError, RecursionError:  # RecursionError: nested too deep
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


def _scopes(document: dict[str, Any]) -> frozenset[str] | None:
    listed = document.get("scopes_supported")
    if not isinstance(listed, list):
        return None
    return frozenset(str(scope) for scope in listed if isinstance(scope, str))


def scope_for(provider: Provider, client: Client, offline: bool = True) -> str:
    """What to ask for. `groups` when the groups come from that claim and the provider lists
    it (or lists nothing); `offline_access` when the provider lists it (and `offline`), as
    most providers only give a refresh token for it, and the refresh token is how Mealwright
    learns the account is gone there (cabledrawer 12 Nov). A refresh token isn't needed
    to sign in: when the provider refuses a sign-in for asking, it is tried once more
    without (`offline` False; O1 review r1 L4)."""
    scopes = ["openid", "profile", "email"]
    if client.group_claim == "groups" and (provider.scopes is None or "groups" in provider.scopes):
        scopes.append("groups")
    if offline and provider.scopes is not None and "offline_access" in provider.scopes:
        scopes.append("offline_access")
    return " ".join(scopes)


# --- Waiting on the sign-in server holds a thread, so it is capped (O2 release pass, M) -----
# A signed-out stranger can start a sign-in as often as they like. While the sign-in server is
# slow or down, each start would hold a worker thread (and a database place) for up to
# TIME_LIMIT. So at most IN_FLIGHT_MOST of a household's requests wait on the sign-in server at
# once (the look-ups are capped the same way); another gets the same quick "try again" a busy
# look-up gives (`say_nothing_of_it`: it is Mealwright's own limit, never remembered as the
# server not answering). A request that waits on another's fetch of the same thing counts too.

IN_FLIGHT_MOST = 4
IN_FLIGHT_TOTAL = 8  # and all households together: threads without a database place
_in_flight: dict[int, int] = {}
_in_flight_lock = threading.Lock()
_holding = threading.local()


@contextlib.contextmanager
def _slot(household_id: int, *, front: bool = False) -> Iterator[None]:
    """One of the household's places to wait on the sign-in server. Re-entrant: a step inside
    another (a discovery inside a start) is the same request and counts once.

    The last place of a household, and the last of the total, is only for the background checks
    (`refresh`, `check_sessions`); `front` (a signed-out start or finish) never takes it, so
    strangers can't starve the checks that end a removed person's sign-ins (review R7)."""
    if getattr(_holding, "depth", 0) > 0:
        _holding.depth += 1
        try:
            yield
        finally:
            _holding.depth -= 1
        return
    reserved = 1 if front else 0
    with _in_flight_lock:
        if (
            _in_flight.get(household_id, 0) >= IN_FLIGHT_MOST - reserved
            or sum(_in_flight.values()) >= IN_FLIGHT_TOTAL - reserved
        ):
            raise SsoFailed("unreachable", say_nothing_of_it=True)
        _in_flight[household_id] = _in_flight.get(household_id, 0) + 1
    _holding.depth = 1
    try:
        yield
    finally:
        _holding.depth = 0
        with _in_flight_lock:
            _in_flight[household_id] -= 1
            if _in_flight[household_id] <= 0:
                del _in_flight[household_id]


@contextlib.contextmanager
def waiting_for(household_id: int, around: Callable[[], Any] | None = None) -> Iterator[None]:
    """A request's calls to the sign-in server, as one. Takes its place to wait first (when they
    are all taken the caller is told to try again at once, still holding what it holds), and
    `around()` (a context manager: the request giving back its database place) is entered only
    when a real wait begins: never for an answer that is already remembered. So at most
    IN_FLIGHT_MOST of a household's threads, and IN_FLIGHT_TOTAL in all, are ever without a
    place, and a thread never waits for a place while others wait for threads (O2 fix11)."""
    with _slot(household_id, front=True):
        _holding.around = around
        _holding.opened = None
        try:
            yield
        finally:
            opened = _holding.opened
            _holding.around = None
            _holding.opened = None
            if opened is not None:
                opened.__exit__(None, None, None)


def _begin_wait() -> None:
    """The real wait on the sign-in server (or on another request's fetch of it) begins: give
    the request's place back, once."""
    around = getattr(_holding, "around", None)
    if around is not None and getattr(_holding, "opened", None) is None:
        opened = around()
        opened.__enter__()
        _holding.opened = opened


class _Flight:
    """One fetch under way; the others who need the same thing wait for its outcome."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.failure: SsoFailed | None = None


_flights: dict[tuple[str, str], _Flight] = {}
_flights_lock = threading.Lock()


def _shared(kind: str, key: str, deadline: float, fetch: Callable[[], Any]) -> Any:
    """`fetch()` once at a time for this `kind` and `key`: the others wait (no longer than
    `deadline`) and share its answer or its failure, so a flood makes one connection."""
    with _flights_lock:
        flight = _flights.get((kind, key))
        leader = flight is None
        if flight is None:
            flight = _flights[(kind, key)] = _Flight()
    if leader:
        crashed: Exception | None = None
        try:
            flight.result = fetch()
        except SsoFailed as failure:
            flight.failure = failure
        except Exception as error:
            # Something unforeseen: the others are told to try again (never remembered).
            flight.failure = SsoFailed("unreachable", say_nothing_of_it=True)
            crashed = error
        finally:
            with _flights_lock:
                _flights.pop((kind, key), None)
            flight.done.set()
        if crashed is not None:
            raise crashed
    else:
        _begin_wait()
        if not flight.done.wait(max(deadline - time.monotonic(), 0.0)):
            raise SsoFailed("unreachable", say_nothing_of_it=True)
    if flight.failure is not None:
        raise SsoFailed(
            flight.failure.code, say_nothing_of_it=flight.failure.say_nothing_of_it
        ) from None
    return flight.result


# Failures that mean the sign-in server didn't answer, or not usefully: the slow ones.
_NO_ANSWER = ("unreachable", "bad_answer")


def discover(
    gate: OutboundGate, household_id: int, issuer: str, deadline: float, fresh: bool = False
) -> Provider:
    """The provider's endpoints, from `<issuer>/.well-known/openid-configuration`. Its
    issuer must be exactly the one saved (OIDC Discovery 4.3). When it didn't answer, it
    isn't asked again for FAIL_FOR: the same failure is given at once, unless `fresh` (the
    admin's own test, who may just have mended it)."""
    found = cache.get("discovery", issuer)
    if isinstance(found, Provider):
        check_now(gate, household_id)
        return found
    failed = None if fresh else cache.get("no_discovery", issuer)
    if isinstance(failed, str):
        check_now(gate, household_id)
        raise SsoFailed(failed)
    try:
        with _slot(household_id):
            provider: Provider = _shared(
                "discovery",
                issuer,
                deadline,
                lambda: _discover(gate, household_id, issuer, deadline),
            )
    except SsoFailed as failure:
        if failure.code in _NO_ANSWER and not failure.say_nothing_of_it:
            cache.put("no_discovery", issuer, failure.code, FAIL_FOR)
        raise
    cache.put("discovery", issuer, provider)
    return provider


def _discover(gate: OutboundGate, household_id: int, issuer: str, deadline: float) -> Provider:
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
    return Provider(
        issuer=str(document["issuer"]),
        authorization_endpoint=str(_endpoint(document, "authorization_endpoint")),
        token_endpoint=str(_endpoint(document, "token_endpoint")),
        jwks_uri=str(_endpoint(document, "jwks_uri")),
        userinfo_endpoint=_endpoint(document, "userinfo_endpoint", required=False),
        basic_auth=basic,
        scopes=_scopes(document),
    )


def _keys(
    gate: OutboundGate, household_id: int, provider: Provider, deadline: float, fresh: bool
) -> Any:
    found = None if fresh else cache.get("jwks", provider.jwks_uri)
    if found is not None:
        return found
    with _slot(household_id):
        return _shared(
            "jwks",
            provider.jwks_uri,
            deadline,
            lambda: _fetch_keys(gate, household_id, provider, deadline),
        )


def _fetch_keys(gate: OutboundGate, household_id: int, provider: Provider, deadline: float) -> Any:
    response = _send(gate, household_id, provider.jwks_uri, deadline=deadline)
    if response.status != 200:
        raise SsoFailed("unreachable" if response.status >= 500 else "bad_answer")
    try:
        keys = JsonWebKey.import_key_set(_json(response))
    except JoseError, JoserfcError, ValueError, TypeError, KeyError:
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
    except JoseError, JoserfcError, ValueError, TypeError, KeyError:
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


@dataclass(frozen=True)
class Flow:
    """A sign-in under way: what the callback must match. Not kept on the server: sealed
    into the cookie of the browser that started it (`pack`), and read back from it."""

    household_id: int
    mode: Mode
    state: str
    nonce: str
    verifier: str
    issuer: str
    client_id: str
    redirect_uri: str
    remember: bool = False
    login_id: int | None = None  # a test: the admin who started it
    started: float = field(default_factory=time.time)  # the clock's time, in seconds
    offline: bool = False  # offline_access was asked for
    # The second try, after the provider refused the first for offline_access: it isn't
    # asked for, no refresh token is kept, and there is no third try.
    retried: bool = False
    # For a confirm (D3, B8 / R6 (a)): what it is for, sealed here so the confirmation that
    # comes back is for exactly the action this browser's trip began (cabledrawer 18 Nov, Q2):
    # "delete_everything", "backup_now", or "keep" with its number. None for any other mode.
    action: str | None = None
    keep: int | None = None

    def pack(self) -> str:
        """As text, for the caller to seal into the browser's cookie."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def unpack(cls, text: str) -> Flow:
        """What `pack` gave. Raises SsoFailed("expired") for anything else."""
        try:
            found = json.loads(text)
            # A confirm sealed before the action was part of it (an upgrade in the middle of a
            # confirm) says nothing of what it was for: it is refused, never read as Delete
            # everything. The person starts again.
            if found.get("mode") == "confirm" and "action" not in found:
                raise SsoFailed("expired")
            flow = cls(**found)
        except ValueError, TypeError, AttributeError:
            raise SsoFailed("expired") from None
        texts = (flow.state, flow.nonce, flow.verifier, flow.issuer, flow.client_id)
        if (
            flow.mode not in ("sign_in", "test", "confirm")
            or not all(isinstance(value, str) and value for value in texts)
            or not isinstance(flow.redirect_uri, str)
            or not isinstance(flow.household_id, int)
            or not isinstance(flow.remember, bool)
            or not isinstance(flow.offline, bool)
            or not isinstance(flow.retried, bool)
            or not (flow.login_id is None or isinstance(flow.login_id, int))
            or not isinstance(flow.started, int | float)
            or not _action_fits(flow)
        ):
            raise SsoFailed("expired")
        return flow


CONFIRM_ACTIONS = ("delete_everything", "backup_now", "keep")


def _action_fits(flow: Flow) -> bool:
    """A confirm names one of the actions (Keep its number, 1 to 30); any other mode names none."""
    if flow.mode != "confirm":
        return flow.action is None and flow.keep is None
    if flow.action not in CONFIRM_ACTIONS:
        return False
    if flow.action == "keep":
        return (
            isinstance(flow.keep, int) and not isinstance(flow.keep, bool) and 1 <= flow.keep <= 30
        )
    return flow.keep is None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Used:
    """The states already used, remembered until they would have run out anyway, so each
    works once. Only a state from a cookie this server sealed gets in here, and at most
    MOST_USED are remembered: when full, the oldest is forgotten. That can never stop
    anyone's sign-in (unlike a table of sign-ins under way); a forgotten state could at
    most be tried a second time by the browser that holds its cookie, where the sign-in
    server's one-time code still refuses it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._used: OrderedDict[str, float] = OrderedDict()

    def once(self, state: str, until: float) -> bool:
        """True the first time `state` is given, False after."""
        key = _hash(state)
        with self._lock:
            at = time.time()
            for old in [k for k, expires in self._used.items() if expires <= at]:
                del self._used[old]
            if key in self._used:
                return False
            while len(self._used) >= MOST_USED:
                self._used.popitem(last=False)
            self._used[key] = until
        return True

    def __len__(self) -> int:
        return len(self._used)


def take(used: Used, packed: str | None, state: str) -> Flow:
    """The sign-in `state` started, from what the browser's own cookie held (opened by the
    caller), and only once. Raises SsoFailed("expired")."""
    if not packed:
        raise SsoFailed("expired")
    flow = Flow.unpack(packed)
    if not secrets.compare_digest(flow.state.encode(), state.encode()):
        raise SsoFailed("expired")  # another sign-in's state: this one isn't used up by it
    age = time.time() - flow.started
    if age > FLOW_FOR or age < -LEEWAY or not used.once(flow.state, flow.started + FLOW_FOR):
        raise SsoFailed("expired")
    return flow


@dataclass(frozen=True)
class Started:
    url: str  # the provider's sign-in page, for the browser
    flow: Flow  # for the caller to seal into the browser's cookie


def start(
    gate: OutboundGate,
    client: Client,
    *,
    mode: Mode,
    remember: bool = False,
    login_id: int | None = None,
    retried: bool = False,
    ask_login: bool = False,
    action: str | None = None,
    keep: int | None = None,
) -> Started:
    """Begin a sign-in: the provider's address to send the browser to, and the sign-in's
    own state, nonce and verifier for the browser's cookie. Nothing is kept here.
    `retried`: the second try, without offline_access. `ask_login`: the sign-in server asks
    for the login again, whoever is signed in there (after an explicit Sign out, S7)."""
    deadline = time.monotonic() + TIME_LIMIT
    provider = discover(gate, client.household_id, client.issuer, deadline, fresh=mode == "test")
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    scope = scope_for(provider, client, offline=not retried)
    flow = Flow(
        household_id=client.household_id,
        mode=mode,
        state=state,
        nonce=nonce,
        verifier=verifier,
        issuer=client.issuer,
        client_id=client.client_id,
        redirect_uri=client.redirect_uri,
        remember=remember,
        login_id=login_id,
        offline="offline_access" in scope.split(),
        retried=retried,
        action=action,
        keep=keep,
    )
    asked = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": client.redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": create_s256_code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if mode != "sign_in" or ask_login:
        # A test asks the sign-in server to ask who this is, whoever is signed in there
        # already: the admin sees which account they are testing (O1 review r1 H1).
        asked["prompt"] = "login"
    if mode == "confirm":
        # And the sign-in must be a new one: max_age=0 makes the sign-in server put when the
        # person signed in there (`auth_time`) in the ID token (OIDC Core 3.1.2.1), and
        # `confirm_fresh` checks it is after this started.
        asked["max_age"] = "0"
    query = urlencode(asked, quote_via=quote)
    joiner = "&" if "?" in provider.authorization_endpoint else "?"
    return Started(url=f"{provider.authorization_endpoint}{joiner}{query}", flow=flow)


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
    # When the person signed in at the sign-in server (seconds since 1970), if it said.
    auth_time: int | None = None
    # The username as the sign-in server sent it, with only the outer spaces trimmed: what the
    # automatic link compares (`username` is tidied for display, storing and logs). None where
    # not given (then `username` is all there is).
    raw_username: str | None = None


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


def may_retry(flow: Flow, error: str | None = None) -> bool:
    """Whether a sign-in the provider refused may be tried once more without
    offline_access: it was asked for, this isn't that second try already, and (with `error`,
    what the provider sent the browser back with) the refusal was about the scope."""
    return flow.offline and not flow.retried and (error is None or error in OFFLINE_REFUSED)


def finish(gate: OutboundGate, flow: Flow, client: Client, code: str) -> Identity:
    """Swap the code for tokens and check the ID token. The flow was already taken. Raises
    SsoFailed; "offline_refused" when the provider refused the code for offline_access and
    the sign-in may be tried once more without it (`may_retry`)."""
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
    if status == 400 and answer.get("error") in OFFLINE_REFUSED and may_retry(flow):
        raise SsoFailed("offline_refused")
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
    # The second try, without offline_access, keeps no refresh token even if one came.
    refresh = None if flow.retried else answer.get("refresh_token")

    def text(name: str) -> str | None:
        value = claims.get(name)
        return value.strip()[:200] if isinstance(value, str) and value.strip() else None

    return Identity(
        issuer=client.issuer,
        subject=str(claims["sub"]),
        # Everything the sign-in server says about a person is tidied to one line here, once:
        # a line break in a username forged a log line and reached "Who is this?" and Recent
        # changes (security pass, fix round 1).
        username=tidy_one_line(text("preferred_username") or "") or None,
        raw_username=text("preferred_username"),
        email=tidy_one_line(text("email") or "") or None,
        name=tidy_one_line(text("name") or "") or None,
        groups=groups_in(claims, client.group_claim),
        refresh_token=refresh if isinstance(refresh, str) and refresh else None,
        auth_time=_whole_seconds(claims.get("auth_time")),
    )


def _whole_seconds(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def confirm_fresh(flow: Flow, identity: Identity) -> None:
    """D3: a confirmation counts only when the sign-in server says the person signed in there
    after it started (`auth_time`, asked for with max_age=0; LEEWAY for the two clocks). A
    sign-in server that doesn't say when is refused: there is no other way to tell a fresh
    sign-in from one it remembered. Raises SsoFailed("not_fresh")."""
    at = identity.auth_time
    if at is None or at < flow.started - LEEWAY or at > time.time() + LEEWAY:
        raise SsoFailed("not_fresh")


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
