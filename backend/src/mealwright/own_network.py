"""Your own network: which addresses Mealwright may visit (spec section 7).

Recipe import (0.5), and notifications and single sign-on later (0.8), may only visit
ordinary public addresses, unless an admin has put a place on the household's own network
on the list in Settings → Privacy, under "Your own network" (spec section 6, "Recipe
import, decided for 0.5"). That stops a pasted link reaching the household's router, other
home servers or this server itself (SSRF).

- **Needs listing:** private, loopback, link-local, unique-local, shared (CGNAT,
  100.64.0.0/10), multicast, unspecified and reserved addresses, and IPv6 addresses that
  carry one of these as an IPv4 address inside them (IPv4-mapped, IPv4-compatible, NAT64,
  6to4, Teredo).
- **Always blocked, even if listed:** this server itself (`localhost` by name, 127.0.0.0/8,
  ::1, and 0.0.0.0/8 and ::, which reach this server too), link-local (169.254.0.0/16 and
  fe80::/10) and the cloud "metadata" addresses (169.254.169.254 is link-local;
  100.100.100.200 and fd00:ec2::254).

An entry is a host name, one address or a range (CIDR). A listed name opens every address
that name has (except the always-blocked ones); a listed address or range opens those
addresses, whatever name reaches them. Ports other than 80 and 443 are allowed only for
listed places (`mealwright.page_fetch`).

Nothing here makes a network connection: the addresses come from the outbound gate.
"""

import ipaddress
import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from sqlalchemy import select
from sqlalchemy.orm import Session

from mealwright.models import Login, OwnNetworkEntry

type IPAddress = IPv4Address | IPv6Address
type IPNetwork = IPv4Network | IPv6Network

# Always blocked, even if listed (spec section 7).
ALWAYS_BLOCKED: tuple[IPNetwork, ...] = (
    IPv4Network("0.0.0.0/8"),  # "this network": 0.0.0.0 reaches this server
    IPv4Network("127.0.0.0/8"),  # loopback
    IPv4Network("169.254.0.0/16"),  # link-local, with the usual metadata address 169.254.169.254
    IPv4Network("100.100.100.200/32"),  # a cloud metadata address (inside 100.64.0.0/10)
    IPv6Network("::/128"),  # unspecified: reaches this server
    IPv6Network("::1/128"),  # loopback
    IPv6Network("fe80::/10"),  # link-local
    IPv6Network("fd00:ec2::254/128"),  # a cloud metadata address
)

# IPv6 blocks that carry an IPv4 address in their last 32 bits.
_COMPATIBLE = IPv6Network("::/96")
_NAT64 = IPv6Network("64:ff9b::/96")
_MAPPED = IPv6Network("::ffff:0:0/96")

# The widest range that can be listed: 10.0.0.0/8 for IPv4, and a /32 for IPv6 (more than
# any home or small office is given). Anything wider is refused. A range that holds an
# always-blocked address is refused too, so the whole of 100.64.0.0/10 (it holds
# 100.100.100.200) or fd00::/8 (it holds fd00:ec2::254) can't be listed: list the part in
# use instead, such as 100.64.0.0/11 or fd12:3456:789a::/48.
WIDEST = {4: 8, 6: 32}

MAX_NAME = 253  # the longest host name DNS allows
_LABEL = re.compile(r"^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")

# Words the screens show (docs/dev/words.md section 18; proposed, for cabledrawer).
BAD_ENTRY = (
    "Type a name (wiki.home.example), an address (192.168.1.20) or a range (192.168.1.0/24)."
)
NEVER = (
    "That can’t be added: this server itself (localhost), link-local and cloud “metadata”"
    " addresses are always blocked."
)
TOO_WIDE = "That range is too wide. Add a smaller one, like 192.168.1.0/24."
ALREADY = "That’s already on the list."


# --- Addresses --------------------------------------------------------------------------


def plain(address: IPAddress) -> IPAddress:
    """An IPv4-mapped IPv6 address (::ffff:192.168.1.5) as the IPv4 address it is."""
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _inside(address: IPv6Address) -> list[IPv4Address]:
    """The IPv4 addresses an IPv6 address carries inside it, if any."""
    found: list[IPv4Address] = []
    if address in _COMPATIBLE or address in _NAT64:
        found.append(IPv4Address(int(address) & 0xFFFF_FFFF))
    if address.sixtofour is not None:
        found.append(address.sixtofour)
    if address.teredo is not None:
        found.extend(address.teredo)
    return found


def always_blocked(address: IPAddress) -> bool:
    """Never visited, even if listed: this server itself, link-local, cloud metadata."""
    address = plain(address)
    if any(address.version == n.version and address in n for n in ALWAYS_BLOCKED):
        return True
    return isinstance(address, IPv6Address) and any(always_blocked(a) for a in _inside(address))


def needs_listing(address: IPAddress) -> bool:
    """Not an ordinary public address: visited only if it's on the household's list."""
    address = plain(address)
    if not address.is_global or address.is_multicast or address.is_reserved:
        return True
    if address.is_private or address.is_loopback or address.is_link_local:
        return True
    if isinstance(address, IPv6Address):
        return address.is_site_local or any(needs_listing(a) for a in _inside(address))
    return False


def name_key(host: str) -> str | None:
    """A host name as the list keeps it: lower case, no final dot, international names in
    their ASCII (punycode) form. None if it isn't a valid host name."""
    name = host.strip().lower().removesuffix(".")
    try:
        name = name.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if not name or len(name) > MAX_NAME:
        return None
    labels = name.split(".")
    if not all(_LABEL.match(label) for label in labels):
        return None
    if labels[-1].isdigit():
        return None  # "192.168.1" or "2130706433": an address, not a name
    return name


def is_localhost(host: str) -> bool:
    """`localhost`, or a name under it (RFC 6761: always this machine)."""
    name = host.strip().lower().removesuffix(".")
    return name == "localhost" or name.endswith(".localhost")


# --- The list ------------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnNetwork:
    """One household's list, read once for a fetch."""

    names: frozenset[str] = frozenset()
    networks: tuple[IPNetwork, ...] = ()

    def lists_name(self, host: str) -> bool:
        key = name_key(host)
        return key is not None and key in self.names

    def lists_address(self, address: IPAddress) -> bool:
        address = plain(address)
        return any(address.version == n.version and address in n for n in self.networks)


def load(db: Session, household_id: int) -> OwnNetwork:
    names: set[str] = set()
    networks: list[IPNetwork] = []
    for entry in entries(db, household_id):
        if entry.kind == "name":
            names.add(entry.value)
        else:
            networks.append(ipaddress.ip_network(entry.value))
    return OwnNetwork(frozenset(names), tuple(networks))


def entries(db: Session, household_id: int) -> list[OwnNetworkEntry]:
    """The household's list, oldest first."""
    return list(
        db.scalars(
            select(OwnNetworkEntry)
            .where(OwnNetworkEntry.household_id == household_id)
            .order_by(OwnNetworkEntry.id)
        )
    )


def tidy(text: str) -> tuple[str, str]:
    """What an entry is ("name", "address" or "range") and its tidied text. Raises
    ValueError with the sentence to show."""
    text = text.strip()
    if not text or len(text) > MAX_NAME or "%" in text or any(c.isspace() for c in text):
        raise ValueError(BAD_ENTRY)
    if "/" in text:
        return "range", str(_range(text))
    try:
        address = plain(ipaddress.ip_address(text))
    except ValueError:
        pass
    else:
        if always_blocked(address):
            raise ValueError(NEVER)
        return "address", str(address)
    if is_localhost(text):
        raise ValueError(NEVER)
    name = name_key(text)
    if name is None:
        raise ValueError(BAD_ENTRY)
    return "name", name


def _range(text: str) -> IPNetwork:
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ValueError(BAD_ENTRY) from None
    if any(network.version == n.version and network.overlaps(n) for n in ALWAYS_BLOCKED):
        raise ValueError(NEVER)
    if network.prefixlen < WIDEST[network.version]:
        raise ValueError(TOO_WIDE)
    if isinstance(network, IPv6Network) and (
        network.overlaps(_MAPPED) or network.overlaps(_COMPATIBLE) or network.overlaps(_NAT64)
    ):
        # Write IPv4 ranges as IPv4: "192.168.1.0/24", not "::ffff:192.168.1.0/120".
        raise ValueError(BAD_ENTRY)
    return network


def add(
    db: Session, household_id: int, text: str, added_by: Login | None = None
) -> OwnNetworkEntry:
    """Add a name, an address or a range to the household's list. Raises ValueError with
    the sentence to show. The caller commits."""
    kind, value = tidy(text)
    taken = db.scalar(
        select(OwnNetworkEntry.id).where(
            OwnNetworkEntry.household_id == household_id, OwnNetworkEntry.value == value
        )
    )
    if taken is not None:
        raise ValueError(ALREADY)
    entry = OwnNetworkEntry(
        household_id=household_id,
        kind=kind,
        value=value,
        added_by_login_id=added_by.id if added_by is not None else None,
        added_by_name=added_by.name if added_by is not None else "",
    )
    db.add(entry)
    db.flush()
    return entry


def remove(db: Session, household_id: int, entry_id: int) -> bool:
    """Take one entry off the household's list. False if the household has no such entry.
    The caller commits."""
    entry = db.get(OwnNetworkEntry, entry_id)
    if entry is None or entry.household_id != household_id:
        return False
    db.delete(entry)
    return True
