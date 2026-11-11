"""Settings → Household: the people of the household, their logins, and "Who's this?" (0.9 A1).

Everyone in the household can see the people; only an admin can add, change or remove them, give
one a login or switch "Who's this?" (`mealwright.roles`, Action.PEOPLE). A person gets a login
with a one-time sign-in link (24 hours) where they choose their own password (proposed, for
cabledrawer); the link's token is shown once and only its SHA-256 is stored.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import select

from mealwright import people
from mealwright.api.v1.account import USERNAME, Me, _me
from mealwright.api.v1.context import Here, acting_member
from mealwright.auth import (
    MAX_PASSWORD,
    MIN_PASSWORD,
    CurrentLogin,
    Db,
    SameOrigin,
    client_address,
    hash_password,
    needs_https,
    start_session,
)
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.history import as_utc, commit, replayed
from mealwright.models import JoinLink, Login, Member, utcnow
from mealwright.names import one_line
from mealwright.roles import ADMIN, Action, allowed
from mealwright.shopping import lock_db

log = logging.getLogger("mealwright.sign_in")

router = APIRouter(tags=["people"], dependencies=[SameOrigin])

# A sign-in link's password: 12 characters at least (the brief's rule; the first-run password's
# own minimum is used if it is ever longer).
JOIN_MIN_PASSWORD = max(12, MIN_PASSWORD)

Colour = Literal["amber", "green", "violet", "blue", "peach"]
Role = Literal["admin", "member"]
# A portion in quarters: ¼ to 2 portions.
Quarters = Annotated[int, Field(ge=1, le=8)]


def _name(value: str) -> str:
    value = one_line(value).strip()
    if not value:
        raise ValueError("Enter a name.")
    return value


def _username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME.match(value):
        raise ValueError("Use up to 50 lowercase letters, numbers, dots, dashes or underscores.")
    return value


class LoginOut(BaseModel):
    username: str
    role: Role
    shared: bool
    # False while the person hasn't used their sign-in link yet.
    has_password: bool
    # An unused sign-in link that hasn't run out.
    link_pending: bool


class HouseholdPerson(BaseModel):
    id: int
    name: str
    colour: Colour | None
    portion_quarters: int
    login: LoginOut | None
    # The signed-in login's own person.
    is_me: bool
    created_at: datetime
    created_by_name: str


class PeopleOut(BaseModel):
    people: list[HouseholdPerson]
    # False for a member: they see the people and can't change them.
    can_change: bool
    # The household switch: shared logins ask "Who's this?" (off at first).
    ask_whos_this: bool


def _person(kitchen: Here, member: Member) -> HouseholdPerson:
    login = people.login_of(kitchen, member)
    return HouseholdPerson(
        id=member.id,
        name=member.name,
        colour=member.colour if member.colour in people.COLOURS else None,  # type: ignore[arg-type]
        portion_quarters=member.portion_quarters,
        login=None
        if login is None
        else LoginOut(
            username=login.username,
            role="admin" if login.role == ADMIN else "member",
            shared=login.shared,
            has_password=bool(login.password_hash),
            link_pending=people.link_pending(kitchen, login),
        ),
        is_me=member.id == kitchen.login.member_id,
        created_at=member.created_at,
        created_by_name=member.created_by_name,
    )


def _people(kitchen: Here) -> PeopleOut:
    members = kitchen.db.scalars(
        select(Member)
        .where(Member.household_id == kitchen.household_id, Member.removed_at.is_(None))
        .order_by(Member.id)
    )
    return PeopleOut(
        people=[_person(kitchen, m) for m in members],
        can_change=allowed(kitchen.login.role, Action.PEOPLE),
        ask_whos_this=kitchen.household.ask_whos_this,
    )


@router.get("/people")
def list_people(kitchen: Here) -> PeopleOut:
    """Everyone in the household who hasn't been removed, in the order they were added."""
    return _people(kitchen)


def _start(kitchen: Here, response: Response) -> bool:
    """Admins only; the household's lock; True when this is a retry of a change already made."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    if replayed(kitchen) is not None:
        response.headers["Idempotent-Replayed"] = "true"
        return True
    return False


def _finish(kitchen: Here, response: Response) -> None:
    if commit(kitchen) is not None:
        response.headers["Idempotent-Replayed"] = "true"


class PersonIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    colour: Colour | None = None
    portion_quarters: Quarters = 4

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _name(value)


@router.post("/people", status_code=status.HTTP_201_CREATED)
def add_person(body: PersonIn, kitchen: Here, response: Response) -> PeopleOut:
    """Add a person with no login (a child, someone who never signs in). Admins only."""
    if not _start(kitchen, response):
        people.add(kitchen, body.name, body.colour, body.portion_quarters)
        _finish(kitchen, response)
    return _people(kitchen)


class PersonChange(BaseModel):
    """Only what is sent changes. `role` and `shared` are for a person with a login."""

    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    colour: Colour | None = None
    portion_quarters: Quarters | None = None
    role: Role | None = None
    shared: StrictBool | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)


@router.patch("/people/{member_id}")
def change_person(
    member_id: StoredInt, body: PersonChange, kitchen: Here, response: Response
) -> PeopleOut:
    """Change a person's name, colour, portion, role or whether their login is shared. The
    household's only admin can't be made a member. Admins only."""
    if not _start(kitchen, response):
        member = people.mine(kitchen, member_id)
        # Null means "no colour"; for the others it means "as it is".
        wanted = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None or key == "colour"
        }
        people.change(kitchen, member, wanted)
        _finish(kitchen, response)
    return _people(kitchen)


@router.delete("/people/{member_id}")
def remove_person(member_id: StoredInt, kitchen: Here, response: Response) -> PeopleOut:
    """Remove a person: their meals, tubs and history stay, Recent changes shows "Joss
    (removed)", and their login can't sign in. Undo puts them back. Admins only; nobody can
    remove themselves, and the household always keeps an admin."""
    if not _start(kitchen, response):
        people.remove(kitchen, people.mine(kitchen, member_id))
        _finish(kitchen, response)
    return _people(kitchen)


class LoginIn(BaseModel):
    username: str
    role: Role = "member"

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        return _username(value)


class LinkOut(BaseModel):
    # The path of the sign-in link, "/join/<token>": shown once, never stored.
    path: str
    expires_at: datetime


@router.post("/people/{member_id}/login", status_code=status.HTTP_201_CREATED)
def give_login(member_id: StoredInt, body: LoginIn, kitchen: Here) -> LinkOut:
    """Give a person a login: a one-time sign-in link, for 24 hours, where they choose their
    own password. Asking again makes a new link and the old one stops working. Admins only."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    member = people.mine(kitchen, member_id)
    token, link = people.give_login(kitchen, member, body.username, body.role)
    kitchen.idempotency_key = None  # a retry makes a new link: the token is never stored
    kitchen.db.commit()
    log.info("Sign-in link made for %s", body.username)
    return LinkOut(path=f"/join/{token}", expires_at=as_utc(link.expires_at))


@router.delete("/people/{member_id}/login", status_code=status.HTTP_204_NO_CONTENT)
def take_back_login(member_id: StoredInt, kitchen: Here) -> None:
    """ "Profile only" again, while the person's sign-in link is unused: the link stops working.
    Admins only."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    people.take_back_login(kitchen, people.mine(kitchen, member_id))
    kitchen.db.commit()


class SwitchIn(BaseModel):
    on: StrictBool


@router.put("/people/ask-whos-this")
def switch_whos_this(body: SwitchIn, kitchen: Here, response: Response) -> PeopleOut:
    """The household switch: shared logins ask "Who's this?". Admins only."""
    if not _start(kitchen, response):
        if people.ask_whos_this(kitchen, body.on) is None:
            from mealwright.kitchen_changes import key_kept

            key_kept(kitchen)
        _finish(kitchen, response)
    return _people(kitchen)


# --- "Who's this?" on a shared login -----------------------------------------------------------


class Pickable(BaseModel):
    id: int
    name: str
    colour: Colour | None


class WhosThisOut(BaseModel):
    # True on a shared login when the household has the switch on.
    ask: bool
    # Who was picked on this device, if anyone.
    picked: int | None
    people: list[Pickable]


def _whos_this(kitchen: Here, signed_in: CurrentLogin) -> WhosThisOut:
    login = signed_in.login
    return WhosThisOut(
        ask=login.shared and kitchen.household.ask_whos_this,
        picked=kitchen.member_id if login.shared else None,
        people=[
            Pickable(
                id=m.id,
                name=m.name,
                colour=m.colour if m.colour in people.COLOURS else None,  # type: ignore[arg-type]
            )
            for m in people.eaters(kitchen)
        ],
    )


@router.get("/whos-this")
def whos_this(kitchen: Here, signed_in: CurrentLogin) -> WhosThisOut:
    return _whos_this(kitchen, signed_in)


class PickIn(BaseModel):
    # Null: "Just looking", nobody picked.
    member_id: int | None


@router.put("/whos-this")
def pick(body: PickIn, kitchen: Here, signed_in: CurrentLogin) -> WhosThisOut:
    """Pick who is using this shared login on this device: their changes are recorded as
    theirs. Only a shared login can pick, and only a person of the household."""
    if not signed_in.login.shared:
        raise Problem(
            status.HTTP_409_CONFLICT, "not_shared", "Only a shared login asks “Who’s this?”."
        )
    if body.member_id is not None and body.member_id not in {m.id for m in people.eaters(kitchen)}:
        raise not_found("That person")
    signed_in.session.member_id = body.member_id
    kitchen.db.commit()
    kitchen.member_id = acting_member(kitchen.db, signed_in.login, body.member_id)
    return _whos_this(kitchen, signed_in)


# --- The sign-in link -------------------------------------------------------------------------


class JoinOut(BaseModel):
    name: str
    username: str
    expires_at: datetime
    min_password: int


GONE = "This sign-in link has been used or has run out. Ask your household’s admin for a new one."


def _link(db: Db, token: str) -> tuple[JoinLink, Login, Member]:
    found = people.find_link(db, token) if len(token) <= 100 else None
    if found is None:
        raise Problem(status.HTTP_404_NOT_FOUND, "link_gone", GONE)  # proposed, for cabledrawer
    return found


@router.get("/join/{token}")
def join_link(token: str, db: Db) -> JoinOut:
    """What the sign-in link page shows: whose link it is. Needs no sign-in."""
    link, login, member = _link(db, token)
    return JoinOut(
        name=member.name,
        username=login.username,
        expires_at=as_utc(link.expires_at),
        min_password=JOIN_MIN_PASSWORD,
    )


class JoinIn(BaseModel):
    password: str = Field(min_length=JOIN_MIN_PASSWORD, max_length=MAX_PASSWORD)
    remember: bool = False


@router.post("/join/{token}")
def join(token: str, body: JoinIn, request: Request, response: Response, db: Db) -> Me:
    """Choose a password with a sign-in link, and be signed in. The link works once."""
    needs_https(request, request.app.state.settings)
    link, login, _member = _link(db, token)
    link.used_at = utcnow()
    login.password_hash = hash_password(body.password)
    start_session(db, response, request.app.state.settings, login, remember=body.remember)
    db.commit()
    log.info("Joined with a sign-in link: %s from %s", login.username, client_address(request))
    return _me(login)
