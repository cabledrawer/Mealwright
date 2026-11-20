"""Fetching a recipe page, or its main photo, safely (spec section 6, "Recipe import, decided
for 0.5", and section 7, "Recipe links on your own network").

Everything goes through the outbound gate, and nothing at all happens while the switch is
off: "Recipe import from links" (`Connection.RECIPE_IMPORT`) for the page, "Download recipe
photos" (`Connection.RECIPE_PHOTOS`) for the photo. Each hop (the link, then every redirect,
at most 5) is checked in full before anything is sent:

1. `http` or `https` only, with no user name or password in the link.
2. `localhost` (and names under it) are refused by name.
3. The name is looked up, and **every** address it has is checked: this server itself,
   link-local and cloud "metadata" addresses are always refused; any other address that
   isn't an ordinary public one (private, shared, unique-local, multicast, reserved…) is
   refused unless the household's "Your own network" list holds the name or the address
   (`mealwright.own_network`).
4. Ports 80 and 443 only, unless the list holds the name or every address.
5. The request goes to exactly the address that was checked (pinned), with the Host header
   and the TLS name still the host name, so a name can't pass the check and then be fetched
   from somewhere else (DNS rebinding).

Pages: up to 5 MB, `text/html` or `application/xhtml+xml` only. Photos: up to 15 MB, image
types only, then cleaned like an upload (`photos.clean`, which also refuses more than 50
megapixels). Each connection (each address tried) must finish within the gate's 15
seconds, and the whole fetch, redirects included, within 30; the gate cuts the connection
when time runs out. The name look-up is timed too: it waits at most the time the import
has left (spec section 6, question 40).

Log lines name only the connection ("recipe import") and the kind of problem, never the
page's address or host: a site name shows what someone was cooking (spec section 7, Logs).
"""

import codecs
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from mealwright import own_network, page_budget, photos
from mealwright.limits import MAX_PHOTO_BYTES, PHOTO_TOO_BIG
from mealwright.outbound import (
    LABELS,
    Connection,
    OutboundBlocked,
    OutboundFailed,
    OutboundGate,
    OutboundResponse,
    ResponseTooLarge,
    WrongContentType,
)
from mealwright.own_network import OwnNetwork

log = logging.getLogger(__name__)

# The page limits (spec section 6, "Recipe import, decided for 0.5").
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
# The whole fetch, redirects included, must finish within this; each connection (each
# address tried) also has the gate's own 15 seconds (decided by cabledrawer; see spec).
MAX_FETCH_SECONDS = 30
NORMAL_PORTS = frozenset({80, 443})
PAGE_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
# Characters a path or query may keep as they are; anything else is %-encoded.
_SAFE = "/%:@!$&'()*+,;=-._~?"


class Problem(StrEnum):
    """Why a fetch didn't give a page or photo; the API sends the code, the screen the
    sentence (`MESSAGES`)."""

    SWITCHED_OFF = "import_switched_off"
    PHOTO_SWITCHED_OFF = "photo_switched_off"
    BAD_LINK = "bad_link"
    ALWAYS_BLOCKED = "always_blocked"
    OWN_NETWORK = "own_network"
    ODD_PORT = "odd_port"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    CANT_REACH = "cant_reach"
    TIMEOUT = "timeout"
    SITE_ERROR = "site_error"
    # The site said no on purpose (401, 403 or 429), as some big recipe sites do to anything
    # that isn't a web browser. The request is not changed to get round it (cabledrawer's to
    # decide).
    SITE_REFUSED = "site_refused"
    NOT_A_PAGE = "not_a_page"
    PAGE_TOO_BIG = "page_too_big"
    NOT_A_PHOTO = "not_a_photo"
    PHOTO_TOO_BIG = "photo_too_big"
    TOO_MANY_PIXELS = "too_many_pixels"
    # Reading the page went over its time or memory budget (raised as
    # `page_budget.PageUnreadable`, which has the same sentence).
    CANT_READ = "cant_read"
    # Two other pages are being read and the wait ran out (`page_budget.PageBusy`).
    BUSY = "busy"


# Words the screens show (docs/dev/words.md section 18). "Importing from links is switched
# off", "This link isn't a web page.", "Photo not downloaded" and the photo limits are the
# spec's own; the rest are proposed, for cabledrawer.
MESSAGES = {
    Problem.SWITCHED_OFF: "Importing from links is switched off",
    Problem.PHOTO_SWITCHED_OFF: "Photo not downloaded",
    Problem.BAD_LINK: "That doesn’t look like a web link. Check it, or paste the recipe’s text.",
    Problem.ALWAYS_BLOCKED: (
        "Mealwright never opens links to this server itself or to cloud “metadata” addresses."
    ),
    Problem.OWN_NETWORK: (
        "That link is on your own network. An admin can allow it in Settings › Outside connections,"
        " under “Your own network”."
    ),
    Problem.ODD_PORT: (
        "That link uses an unusual port. An admin can allow it in Settings › Outside connections,"
        " under “Your own network”."
    ),
    Problem.TOO_MANY_REDIRECTS: "That link sends you on too many times. Try the recipe’s own link.",
    Problem.CANT_REACH: "Couldn’t reach that site. Check the link, or try again later.",
    Problem.TIMEOUT: "That site took too long to answer. Try again later.",
    Problem.SITE_ERROR: "That site didn’t send the page. Check the link, or try again later.",
    Problem.SITE_REFUSED: (
        "That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead."
    ),
    Problem.NOT_A_PAGE: "This link isn’t a web page.",
    Problem.PAGE_TOO_BIG: "That page is bigger than 5 MB.",
    Problem.NOT_A_PHOTO: photos.NOT_A_PHOTO,
    Problem.PHOTO_TOO_BIG: PHOTO_TOO_BIG,
    Problem.TOO_MANY_PIXELS: photos.TOO_MANY_PIXELS,
    Problem.CANT_READ: page_budget.CANT_READ,
    Problem.BUSY: page_budget.BUSY,
}

# What a log line says about each problem (no address, no host).
_LOGGED = {
    Problem.BAD_LINK: "not an http or https link",
    Problem.ALWAYS_BLOCKED: "this server, link-local or metadata address",
    Problem.OWN_NETWORK: "address on the own network that isn't listed",
    Problem.ODD_PORT: "unusual port that isn't listed",
    Problem.TOO_MANY_REDIRECTS: "too many redirects",
    Problem.NOT_A_PAGE: "not a web page",
    Problem.PAGE_TOO_BIG: "page bigger than 5 MB",
    Problem.NOT_A_PHOTO: "not a photo",
    Problem.PHOTO_TOO_BIG: "photo bigger than 15 MB",
}


class FetchRefused(Exception):
    """A page or photo wasn't fetched. `problem` is the code; `message` the sentence."""

    def __init__(self, problem: Problem) -> None:
        super().__init__(MESSAGES[problem])
        self.problem = problem
        self.message = MESSAGES[problem]


@dataclass(frozen=True)
class FetchedPage:
    url: str  # where the page was in the end, after any redirects
    html: str


type _Address = IPv4Address | IPv6Address


@dataclass(frozen=True)
class _Kinds:
    """What one kind of fetch accepts, and what its refusals are called."""

    connection: Connection
    switched_off: Problem
    max_bytes: int
    too_big: Problem
    wrong_type: Problem
    accept: Callable[[str], bool]


_PAGE = _Kinds(
    Connection.RECIPE_IMPORT,
    Problem.SWITCHED_OFF,
    MAX_PAGE_BYTES,
    Problem.PAGE_TOO_BIG,
    Problem.NOT_A_PAGE,
    lambda kind: kind in PAGE_TYPES,
)
_PHOTO = _Kinds(
    Connection.RECIPE_PHOTOS,
    Problem.PHOTO_SWITCHED_OFF,
    MAX_PHOTO_BYTES,
    Problem.PHOTO_TOO_BIG,
    Problem.NOT_A_PHOTO,
    # Which image it really is comes from the file itself (photos.clean), not this label.
    lambda kind: kind.startswith("image/"),
)


_SAID_NO = frozenset({401, 403, 429})


def _status_problem(status: int, kinds: _Kinds) -> Problem:
    """Why a reply that wasn't a page (or photo) is refused. A page the site wouldn't give
    says so, with the way on (paste the text); a photo, or any other error, is "didn't send"."""
    return Problem.SITE_REFUSED if status in _SAID_NO and kinds is _PAGE else Problem.SITE_ERROR


def tidy_link(url: str) -> str:
    """The link as it's requested and compared (see `_tidy`). Raises FetchRefused (BAD_LINK)."""
    return _tidy(url)


def fetch_page(
    gate: OutboundGate, household_id: int, url: str, *, seconds: float | None = None
) -> FetchedPage:
    """The recipe page at `url`, as text. Raises FetchRefused. `seconds`: the time the whole
    fetch may take, if less than `MAX_FETCH_SECONDS` (the import has 30 seconds in all)."""
    final_url, response = _fetch(gate, household_id, url, _PAGE, seconds)
    return FetchedPage(url=final_url, html=_decode(response))


def download_photo(
    gate: OutboundGate, household_id: int, url: str, *, seconds: float | None = None
) -> photos.Cleaned:
    """The recipe's main photo, shrunk and cleaned like an upload. It isn't stored here.
    Raises FetchRefused ("Photo not downloaded" while the photo switch is off). `seconds`:
    as for `fetch_page`."""
    _, response = _fetch(gate, household_id, url, _PHOTO, seconds)
    try:
        return photos.clean(response.body)
    except photos.NotAPhoto:
        raise FetchRefused(Problem.NOT_A_PHOTO) from None
    except photos.TooManyPixels:
        raise FetchRefused(Problem.TOO_MANY_PIXELS) from None


# --- One fetch, hop by hop ------------------------------------------------------------------


def _fetch(
    gate: OutboundGate,
    household_id: int,
    url: str,
    kinds: _Kinds,
    seconds: float | None = None,
) -> tuple[str, OutboundResponse]:
    label = LABELS[kinds.connection]
    # The switch first: while it's off, nothing is looked up, read or sent.
    try:
        gate.check_switch(household_id, kinds.connection)
    except OutboundBlocked:
        raise FetchRefused(kinds.switched_off) from None
    deadline = time.monotonic() + (
        MAX_FETCH_SECONDS if seconds is None else min(MAX_FETCH_SECONDS, seconds)
    )
    with gate.sessions() as db:
        listed = own_network.load(db, household_id)
    try:
        for hop in range(MAX_REDIRECTS + 1):
            url = _tidy(url)
            response = _one_hop(gate, household_id, url, kinds, listed, deadline)
            if response.status not in _REDIRECTS:
                if not 200 <= response.status < 300:
                    raise FetchRefused(_status_problem(response.status, kinds))
                return url, response
            location = _header(response, "Location")
            if not location:
                raise FetchRefused(Problem.SITE_ERROR)
            if hop == MAX_REDIRECTS:
                raise FetchRefused(Problem.TOO_MANY_REDIRECTS)
            try:
                url = urljoin(url, location.strip())
            except ValueError:
                # An address Python can't take apart (a broken [IPv6] literal, characters
                # that are invalid once normalised): a bad link, never an uncaught error.
                raise FetchRefused(Problem.BAD_LINK) from None
    except FetchRefused as refused:
        if refused.problem in _LOGGED:
            # The connection's label and the kind of problem only, never the address.
            log.warning("Blocked outgoing connection: %s, %s", label, _LOGGED[refused.problem])
        raise
    raise AssertionError("unreachable")  # pragma: no cover


def _one_hop(
    gate: OutboundGate,
    household_id: int,
    url: str,
    kinds: _Kinds,
    listed: OwnNetwork,
    deadline: float,
) -> OutboundResponse:
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    if time.monotonic() >= deadline:
        raise FetchRefused(Problem.TIMEOUT)
    addresses = _checked_addresses(gate, household_id, kinds, host, port, listed, deadline)
    if port not in NORMAL_PORTS and not (
        listed.lists_name(host) or all(listed.lists_address(a) for a in addresses)
    ):
        raise FetchRefused(Problem.ODD_PORT)
    for address in addresses:
        try:
            return gate.get_pinned(
                household_id,
                kinds.connection,
                url,
                address,
                max_bytes=kinds.max_bytes,
                accept=kinds.accept,
                deadline=deadline,
            )
        except ResponseTooLarge:
            raise FetchRefused(kinds.too_big) from None
        except WrongContentType:
            raise FetchRefused(kinds.wrong_type) from None
        except OutboundBlocked:
            raise FetchRefused(kinds.switched_off) from None  # switched off meanwhile
        except OutboundFailed as problem:
            if problem.kind != "unreachable":
                raise FetchRefused(
                    Problem.TIMEOUT if problem.kind == "timeout" else Problem.CANT_REACH
                ) from None
            # Unreachable: try the name's next address (each one was checked above).
    raise FetchRefused(Problem.CANT_REACH)


def _checked_addresses(
    gate: OutboundGate,
    household_id: int,
    kinds: _Kinds,
    host: str,
    port: int,
    listed: OwnNetwork,
    deadline: float,
) -> list[_Address]:
    """Every address `host` has, after checking each one. Raises FetchRefused. The name
    look-up waits at most until `deadline` (the import's own time limit)."""
    try:
        literal: _Address | None = ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        if own_network.is_localhost(host):
            raise FetchRefused(Problem.ALWAYS_BLOCKED)
        try:
            addresses = gate.look_up(household_id, kinds.connection, host, port, deadline=deadline)
        except OutboundBlocked:
            raise FetchRefused(kinds.switched_off) from None  # switched off meanwhile
        except OutboundFailed as problem:
            raise FetchRefused(
                Problem.TIMEOUT if problem.kind == "timeout" else Problem.CANT_REACH
            ) from None
        if not addresses:
            raise FetchRefused(Problem.CANT_REACH)
    name_listed = literal is None and listed.lists_name(host)
    for address in addresses:
        if own_network.always_blocked(address):
            raise FetchRefused(Problem.ALWAYS_BLOCKED)
        if own_network.needs_listing(address) and not (
            name_listed or listed.lists_address(address)
        ):
            raise FetchRefused(Problem.OWN_NETWORK)
    return [own_network.plain(a) for a in addresses]


def _tidy(url: str) -> str:
    """The link as it's requested: http or https, the host in its ASCII form, no user name
    or password, no fragment, and the path and query %-encoded. Raises FetchRefused."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise FetchRefused(Problem.BAD_LINK) from None
    host = parts.hostname
    if (
        parts.scheme not in {"http", "https"}
        or not host
        or parts.username is not None
        or parts.password is not None
        or "%" in host  # an IPv6 zone ("fe80::1%eth0") or an encoded name
        or port == 0
    ):
        raise FetchRefused(Problem.BAD_LINK)
    try:
        literal = ip_address(host)
    except ValueError:
        name = own_network.name_key(host)
        if name is None:
            raise FetchRefused(Problem.BAD_LINK) from None
        netloc = name
    else:
        netloc = f"[{literal}]" if literal.version == 6 else str(literal)
    if port is not None:
        netloc += f":{port}"
    path = quote(parts.path or "/", safe=_SAFE)
    query = quote(parts.query, safe=_SAFE)
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def _header(response: OutboundResponse, name: str) -> str:
    return next((v for k, v in response.headers.items() if k.lower() == name.lower()), "")


# --- The page's text --------------------------------------------------------------------------

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)


def _decode(response: OutboundResponse) -> str:
    """The page's bytes as text: the charset the site names (in the header, else in the
    page's first 4 KB), else UTF-8. Bytes that don't fit are replaced, never refused."""
    body = response.body
    if body.startswith(codecs.BOM_UTF8):
        return body[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace")
    content_type = _header(response, "Content-Type")
    named = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9_.:-]+)", content_type, re.I)
    found = named.group(1) if named else None
    if found is None:
        meta = _META_CHARSET.search(body[:4096])
        found = meta.group(1).decode("ascii") if meta else None
    encoding = _text_codec(found) if found else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError, UnicodeError, ValueError:  # pragma: no cover (text codecs replace)
        return body.decode("utf-8", errors="replace")


# Codecs Python calls text encodings that still aren't a page's character set: they turn
# the bytes into something else (or can't replace a bad byte), so they're read as UTF-8.
_NOT_A_CHARSET = frozenset(
    {
        "idna",
        "punycode",
        "raw-unicode-escape",
        "unicode-escape",
        "undefined",
        "utf-7",
    }
)


def _text_codec(name: str) -> str:
    """The codec for a charset the site named: a real text encoding only. Anything else
    (zlib, base64, rot13, uu, idna, an unknown name) is read as UTF-8."""
    try:
        info = codecs.lookup(name)
    except LookupError:
        return "utf-8"
    if not getattr(info, "_is_text_encoding", True) or info.name in _NOT_A_CHARSET:
        return "utf-8"
    if info.name in {"utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"}:
        return "utf-8"  # a page that says so in ASCII is ASCII-compatible
    return info.name
