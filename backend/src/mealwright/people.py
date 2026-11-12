"""The people of a household (0.9 A1): members, with or without a login (spec section 3)."""

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from fastapi import status
from sqlalchemy import ColumnElement, and_, delete, false, func, or_, select, update
from sqlalchemy.orm import Session as DbSession

from mealwright import api_tokens
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import Who
from mealwright.errors import Problem, not_found
from mealwright.history import as_utc, record
from mealwright.models import Change, JoinLink, Login, Member, Session, SsoSettings, utcnow
from mealwright.names import fold
from mealwright.roles import ADMIN, MEMBER


def own_members(kitchen: Kitchen, ids: list[int]) -> list[int]:
    """`ids` as given, once each is a person of this household who hasn't been removed."""
    for member_id in ids:
        member = kitchen.db.get(Member, member_id)
        if (
            member is None
            or member.household_id != kitchen.household_id
            or member.removed_at is not None
        ):
            raise not_found("That person")
    return ids


def own_member(kitchen: Kitchen, member_id: int | None) -> Member | None:
    """This household's person (removed ones too, for Undo), or None."""
    if member_id is None:
        return None
    member = kitchen.db.get(Member, member_id)
    return member if member is not None and member.household_id == kitchen.household_id else None


def eaters(kitchen: Kitchen) -> list[Member]:
    """The people who eat, in the order they were added: everyone not removed, apart from a
    shared login's own person ("Kitchen tablet" doesn't eat)."""
    shared = select(Login.member_id).where(
        Login.household_id == kitchen.household_id,
        Login.shared.is_(True),
        Login.member_id.is_not(None),
    )
    return list(
        kitchen.db.scalars(
            select(Member)
            .where(
                Member.household_id == kitchen.household_id,
                Member.removed_at.is_(None),
                Member.id.not_in(shared),
            )
            .order_by(Member.id)
        )
    )


def shown_name(member: Member) -> str:
    """A person's name as Recent changes shows it: "Joss (removed)" once removed (cabledrawer 12 Nov,
    accepted as built)."""
    return f"{member.name} (removed)" if member.removed_at is not None else member.name


def who_did(kitchen: Kitchen, change: Change) -> Who:
    """Who made a change: the person it names (on a shared login, the one picked in "Who's
    this?"), by their name now, or the login's name as it was for a change that names no one."""
    member = own_member(kitchen, change.member_id)
    name = shown_name(member) if member is not None else change.login_name
    return Who(login_id=change.login_id, name=name, member_id=change.member_id)


# --- Changing people (admins only; the routes are in `api/v1/people.py`) -------------------------

# The colours a person can have, as the design names them (cabledrawer 12 Nov).
COLOURS = ("amber", "green", "violet", "blue", "peach")
KINDS = ("person_added", "person_changed", "person_removed", "whos_this_switch")
# A sign-in link was made: only there to be read in Recent changes, with no Undo of its own.
LINK_KIND = "person_login"
JOIN_FOR = timedelta(hours=24)  # cabledrawer 12 Nov


def _refused(code: str, detail: str) -> Problem:
    return Problem(status.HTTP_409_CONFLICT, code, detail)


def _cannot_undo(detail: str) -> Problem:
    return _refused("cannot_undo", detail)


def portion_words(quarters: int) -> str:
    """4 → "1 portion", 2 → "½ portion", 6 → "1½ portions"."""
    whole, part = divmod(quarters, 4)
    fraction = {0: "", 1: "¼", 2: "½", 3: "¾"}[part]
    number = (str(whole) if whole else "") + fraction
    return f"{number} portion" if quarters <= 4 else f"{number} portions"


def login_of(kitchen: Kitchen, member: Member) -> Login | None:
    return kitchen.db.scalar(select(Login).where(Login.member_id == member.id))


def signs_in(login: Login | None) -> bool:
    """The login has a password or a single sign-on identity (0.9 O1)."""
    return login is not None and (bool(login.password_hash) or login.sso_subject is not None)


def can_sign_in() -> ColumnElement[bool]:
    """A login (joined to its person) that can sign in: it has a password or a single sign-on
    identity (0.9 O1), and its person isn't removed."""
    return and_(
        or_(
            and_(
                Login.password_hash.is_not(None),
                Login.password_hash != "",  # nosec B105
            ),
            Login.sso_subject.is_not(None),
        ),
        Member.removed_at.is_(None),
    )


def admin_can_sign_in(
    db: DbSession, household_id: int, passwords_off: bool = False
) -> ColumnElement[bool]:
    """Like `can_sign_in`, for counting the admins who can get in. While password sign-in is
    turned off for single sign-on, a password is no way in: only a login linked to the saved
    sign-in server counts (O1 review r1 M3), so the last admin who can really sign in is
    never removed, made a Member or made shared."""
    setup = db.scalar(select(SsoSettings).where(SsoSettings.household_id == household_id))
    if setup is None or not passwords_off:
        # A single sign-on identity counts only at the saved sign-in server (O1 review r2, 4):
        # one made at another can't sign in now.
        has_password = and_(
            Login.password_hash.is_not(None),
            Login.password_hash != "",  # nosec B105
        )
        at_saved_server = (
            and_(Login.sso_issuer == setup.issuer, Login.sso_subject.is_not(None))
            if setup is not None
            else false()
        )
        return and_(or_(has_password, at_saved_server), Member.removed_at.is_(None))
    return and_(
        Login.sso_issuer == setup.issuer,
        Login.sso_subject.is_not(None),
        Member.removed_at.is_(None),
    )


def admins_left(kitchen: Kitchen, apart_from: int | None = None) -> int:
    """How many admins the household has who can sign in, apart from this person. An admin
    whose sign-in link isn't used yet doesn't count: they can't sign in to do admin things.
    A shared login (a kitchen tablet) doesn't count either: cabledrawer 12 Nov. With
    password sign-in off, only admins linked by single sign-on count (`admin_can_sign_in`)."""
    from mealwright.sso_accounts import passwords_off  # here: sso_accounts imports this module

    off = passwords_off(kitchen.db, kitchen.data_dir, kitchen.household_id)
    query = (
        select(func.count())
        .select_from(Login)
        .join(Member, Member.id == Login.member_id)
        .where(Login.household_id == kitchen.household_id, Login.role == ADMIN)
        .where(admin_can_sign_in(kitchen.db, kitchen.household_id, off))
        .where(Login.shared.is_(False))
    )
    if apart_from is not None:
        query = query.where(Member.id != apart_from)
    return int(kitchen.db.scalar(query) or 0)


def last_admin(member: Member) -> Problem:
    return _refused(  # cabledrawer 12 Nov
        "last_admin",
        f"{member.name} is the household’s only admin. Make someone else an admin first.",
    )


def check_name(kitchen: Kitchen, name: str, apart_from: int | None = None) -> None:
    """Two people of the household can't have the same name: "Who's this?" and Recent changes
    tell them apart by it (cabledrawer 12 Nov)."""
    for other in kitchen.db.scalars(
        select(Member).where(
            Member.household_id == kitchen.household_id, Member.removed_at.is_(None)
        )
    ):
        if other.id != apart_from and fold(other.name) == fold(name):
            raise _refused("name_taken", f"There’s already someone called {other.name}.")


def mine(kitchen: Kitchen, member_id: int) -> Member:
    """This household's person who hasn't been removed, or 404."""
    member = own_member(kitchen, member_id)
    if member is None or member.removed_at is not None:
        raise not_found("That person")
    return member


def _state(kitchen: Kitchen, member: Member) -> dict[str, Any]:
    login = login_of(kitchen, member)
    return {
        "name": member.name,
        "colour": member.colour,
        "portion_quarters": member.portion_quarters,
        "role": login.role if login is not None else None,
        "shared": login.shared if login is not None else None,
    }


def add(kitchen: Kitchen, name: str, colour: str | None, portion_quarters: int) -> Change:
    check_name(kitchen, name)
    member = Member(
        household_id=kitchen.household_id,
        name=name,
        colour=colour,
        portion_quarters=portion_quarters,
        created_at=utcnow(),
        created_by_name=kitchen.login.name,
    )
    kitchen.db.add(member)
    kitchen.db.flush()
    return record(
        kitchen,
        "person_added",
        f"Added {name} to the household",  # cabledrawer 12 Nov
        None,
        {"person": {"id": member.id, "new": _state(kitchen, member)}},
    )


def change(kitchen: Kitchen, member: Member, wanted: dict[str, Any]) -> Change | None:
    """Change what's in `wanted` (name, colour, portion_quarters, role, shared). Role and shared
    need a login. Nothing is recorded when nothing changed."""
    login = login_of(kitchen, member)
    if ("role" in wanted or "shared" in wanted) and login is None:
        raise _refused("no_login", f"{member.name} doesn’t sign in.")  # cabledrawer 12 Nov
    old = _state(kitchen, member)
    if "name" in wanted and wanted["name"] != member.name:
        check_name(kitchen, wanted["name"], member.id)
    steps_down = wanted.get("role") == MEMBER and old["role"] == ADMIN
    goes_shared = wanted.get("shared") is True and not old["shared"] and old["role"] == ADMIN
    if (steps_down or goes_shared) and admins_left(kitchen, member.id) == 0:
        raise last_admin(member)
    _apply(kitchen, member, login, wanted)
    new = _state(kitchen, member)
    if new == old:
        return None
    return record(
        kitchen,
        "person_changed",
        _change_words(old, new),
        None,
        {"person": {"id": member.id, "old": old, "new": new}},
    )


def _apply(kitchen: Kitchen, member: Member, login: Login | None, wanted: dict[str, Any]) -> None:
    for key in ("name", "colour", "portion_quarters"):
        if key in wanted:
            setattr(member, key, wanted[key])
    if login is not None:
        login.name = member.name  # the login's name follows its person's
        if wanted.get("role") is not None:
            login.role = wanted["role"]
            if login.role != ADMIN:  # only admins have API tokens (PR O2)
                api_tokens.stop_for(kitchen.db, login.id)
                api_tokens.clear_refused(kitchen.db, login)
        if wanted.get("shared") is not None:
            login.shared = wanted["shared"]
    kitchen.db.flush()


def _change_words(old: dict[str, Any], new: dict[str, Any]) -> str:
    """cabledrawer 12 Nov: "Changed Joss: ½ portion (was 1 portion)"."""
    parts: list[str] = []
    if old["name"] != new["name"]:
        parts.append(f"renamed from {old['name']}")
    if old["colour"] != new["colour"]:
        parts.append(f"colour {new['colour'] or 'none'}")
    if old["portion_quarters"] != new["portion_quarters"]:
        parts.append(
            f"{portion_words(new['portion_quarters'])} "
            f"(was {portion_words(old['portion_quarters'])})"
        )
    if old["role"] != new["role"]:
        parts.append(f"{'an admin' if new['role'] == ADMIN else 'a member'} now")
    if old["shared"] != new["shared"]:
        parts.append("a shared login" if new["shared"] else "not a shared login")
    return f"Changed {new['name']}: {', '.join(parts)}"


def remove(kitchen: Kitchen, member: Member) -> Change:
    """Mark the person removed: their meals, tubs and history stay. Their login can't sign in
    any more, and every device they're signed in on is signed out."""
    if member.id == kitchen.login.member_id:
        raise _refused(  # cabledrawer 12 Nov
            "remove_yourself", "You can’t remove yourself. Ask another admin."
        )
    login = login_of(kitchen, member)
    if login is not None and login.role == ADMIN and admins_left(kitchen, member.id) == 0:
        raise last_admin(member)
    member.removed_at = utcnow()
    if login is not None:
        kitchen.db.execute(delete(Session).where(Session.login_id == login.id))
        kitchen.db.execute(delete(JoinLink).where(JoinLink.login_id == login.id))
        api_tokens.stop_for(kitchen.db, login.id)  # for good: Undo doesn't bring them back
        api_tokens.clear_refused(kitchen.db, login)
    # Nobody is "Who's this?"-picked as them any more.
    kitchen.db.execute(
        update(Session)
        .where(Session.household_id == kitchen.household_id, Session.member_id == member.id)
        .values(member_id=None, picked_at=None)
    )
    kitchen.db.flush()
    return record(
        kitchen,
        "person_removed",
        f"Removed {member.name} from the household",  # cabledrawer 12 Nov
        None,
        {"person": {"id": member.id}},
    )


def ask_whos_this(kitchen: Kitchen, on: bool) -> Change | None:
    household = kitchen.household
    if household.ask_whos_this == on:
        return None
    household.ask_whos_this = on
    kitchen.db.flush()
    return record(
        kitchen,
        "whos_this_switch",
        f"Switched Ask “Who’s this?” {'on' if on else 'off'}",  # cabledrawer 12 Nov
        None,
        {"whos_this": {"old": not on, "new": on}},
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def give_login(kitchen: Kitchen, member: Member, username: str, role: str) -> tuple[str, JoinLink]:
    """Give a person a login with no password yet, and a one-time sign-in link (24 hours) where
    they choose one (cabledrawer 12 Nov). A new link replaces any unused one. Returns the
    link's token (shown once, never stored) and the link."""
    login = login_of(kitchen, member)
    if signs_in(login):
        raise _refused(  # cabledrawer 12 Nov
            "signs_in_already", f"{member.name} already signs in."
        )
    taken = kitchen.db.scalar(select(Login).where(Login.username == username))
    if taken is not None and taken is not login:
        raise _refused("username_taken", "That username is taken. Try another.")
    if login is None:
        login = Login(
            household_id=kitchen.household_id,
            username=username,
            name=member.name,
            password_hash=None,
            role=role,
            member_id=member.id,
            created_at=utcnow(),
        )
        kitchen.db.add(login)
    else:
        if role == MEMBER and login.role == ADMIN and admins_left(kitchen, member.id) == 0:
            raise last_admin(member)  # pragma: no cover (the admin doing it signs in)
        login.username, login.role = username, role
    kitchen.db.flush()
    # Every link of this login goes, even one a join has claimed and is still hashing for.
    kitchen.db.execute(delete(JoinLink).where(JoinLink.login_id == login.id))
    token = secrets.token_urlsafe(32)
    made = utcnow()
    link = JoinLink(
        household_id=kitchen.household_id,
        login_id=login.id,
        token_hash=_token_hash(token),
        created_at=made,
        expires_at=made + JOIN_FOR,
    )
    kitchen.db.add(link)
    kitchen.db.flush()
    record(
        kitchen,
        LINK_KIND,
        f"Made a sign-in link for {member.name}",  # cabledrawer 12 Nov
        None,
        None,
    )
    return token, link


def take_back_login(kitchen: Kitchen, member: Member) -> None:
    """ "Profile only" for a person whose sign-in link hasn't been used yet: the login and its
    link go. Someone who already signs in is removed instead (cabledrawer 12 Nov)."""
    login = login_of(kitchen, member)
    if login is None:
        return
    if signs_in(login):
        raise _refused(
            "signs_in_already",
            f"{member.name} already signs in. To stop that, remove {member.name}.",
        )
    kitchen.db.delete(login)
    kitchen.db.flush()


def link_pending(kitchen: Kitchen, login: Login) -> bool:
    return (
        kitchen.db.scalar(
            select(JoinLink.id).where(
                JoinLink.login_id == login.id,
                JoinLink.used_at.is_(None),
                JoinLink.expires_at > utcnow(),
            )
        )
        is not None
    )


def find_link(db: DbSession, token: str) -> tuple[JoinLink, Login, Member] | None:
    """The unused, unexpired link with this token, its login and its person (not removed)."""
    link = db.scalar(select(JoinLink).where(JoinLink.token_hash == _token_hash(token)))
    if link is None or link.used_at is not None or as_utc(link.expires_at) <= utcnow():
        return None
    login = db.get(Login, link.login_id)
    if login is None or signs_in(login) or login.member_id is None:
        return None
    member = db.get(Member, login.member_id)
    if member is None or member.removed_at is not None:
        return None
    return link, login, member


def claim_link(db: DbSession, link: JoinLink) -> bool:
    """Mark the link used, in one step that only one request can win: True for the request
    that did, False for any other (it was used, or ran out, in the meantime). Committed."""
    now = utcnow()
    claimed = db.execute(
        update(JoinLink)
        .where(JoinLink.id == link.id, JoinLink.used_at.is_(None), JoinLink.expires_at > now)
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return bool(getattr(claimed, "rowcount", 0) == 1)


def give_back_link(db: DbSession, link: JoinLink) -> None:
    """Undo `claim_link` when the password couldn't be set: the link works again, but only if
    it still exists and no newer link was made for that login in the meantime."""
    link_id, login_id = link.id, link.login_id
    db.rollback()
    newer = select(JoinLink.id).where(JoinLink.login_id == login_id, JoinLink.id > link_id)
    db.execute(
        update(JoinLink)
        .where(JoinLink.id == link_id, ~newer.exists())
        .values(used_at=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def removed(db: DbSession, login: Login) -> bool:
    """True when this login's person has been removed: it can't sign in."""
    member = db.get(Member, login.member_id) if login.member_id is not None else None
    return member is not None and member.removed_at is not None


# --- Undo -----------------------------------------------------------------------------------


def undo(kitchen: Kitchen, change: Change) -> None:
    """Put one of these changes back, or refuse (409 `cannot_undo`) and change nothing."""
    data = change.undo_data or {}
    if change.kind == "whos_this_switch":
        household = kitchen.household
        if household.ask_whos_this != data["whos_this"]["new"]:
            raise _cannot_undo("That can’t be undone: Ask “Who’s this?” has been switched again.")
        household.ask_whos_this = data["whos_this"]["old"]
        kitchen.db.flush()
        return
    member = own_member(kitchen, data["person"]["id"])
    if member is None:
        raise _cannot_undo("That can’t be undone: the person is gone.")  # pragma: no cover
    if change.kind == "person_added":
        if member.removed_at is not None:
            raise _cannot_undo(f"That can’t be undone: {member.name} has been removed already.")
        if login_of(kitchen, member) is not None:
            raise _cannot_undo(  # cabledrawer 12 Nov
                f"That can’t be undone: {member.name} has a login now. Remove them instead."
            )
        member.removed_at = utcnow()
        kitchen.db.flush()
    elif change.kind == "person_removed":
        if member.removed_at is None:  # pragma: no cover (only this Undo brings them back)
            raise _cannot_undo(f"That can’t be undone: {member.name} is back already.")
        try:
            check_name(kitchen, member.name, member.id)
        except Problem:
            raise _cannot_undo(
                f"That can’t be undone: there’s someone else called {member.name} now."
            ) from None
        member.removed_at = None
        kitchen.db.flush()
    elif change.kind == "person_changed":
        _undo_change(kitchen, member, data["person"])


def _undo_change(kitchen: Kitchen, member: Member, data: dict[str, Any]) -> None:
    if member.removed_at is not None:
        raise _cannot_undo(f"That can’t be undone: {member.name} has been removed.")
    old, new, now = data["old"], data["new"], _state(kitchen, member)
    changed = [key for key in old if old[key] != new[key]]
    if any(now[key] != new[key] for key in changed):
        raise _cannot_undo(f"That can’t be undone: {member.name} has been changed again.")
    wanted = {key: old[key] for key in changed}
    if "name" in wanted:
        try:
            check_name(kitchen, wanted["name"], member.id)
        except Problem:
            raise _cannot_undo(
                f"That can’t be undone: there’s someone else called {wanted['name']} now."
            ) from None
    goes_shared = wanted.get("shared") is True and now["role"] == ADMIN
    if (wanted.get("role") == MEMBER or goes_shared) and admins_left(kitchen, member.id) == 0:
        raise _cannot_undo(  # cabledrawer 12 Nov
            f"That can’t be undone: {member.name} is the household’s only admin now."
        )
    _apply(kitchen, member, login_of(kitchen, member), wanted)
