"""Settings › People: the people of the household, their logins, and "Who's this?" (0.9 A1).

Everyone in the household can see the people; only an admin can add, change or remove them, give
one a login or switch "Who's this?" (`mealwright.roles`, Action.PEOPLE). A person gets a login
with a one-time sign-in link (24 hours) where they choose their own password (cabledrawer 12 Nov,
accepted as built); the link's token is shown once and only its SHA-256 is stored.
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import StaleDataError

from mealwright import api_tokens, people, sso_people
from mealwright.api.v1.account import USERNAME
from mealwright.api.v1.context import Here, acting_member
from mealwright.api.v1.schemas import ChangeOut
from mealwright.auth import (
    MAX_PASSWORD,
    MIN_PASSWORD,
    CurrentSession,
    Db,
    SameOrigin,
    client_address,
    hash_password,
    needs_https,
    peek_session,
    session_token,
)
from mealwright.errors import USERNAME_RULE, Problem, StoredInt, not_found
from mealwright.foods import change_out
from mealwright.history import commit, replayed
from mealwright.kitchen_changes import key_kept
from mealwright.models import Change, JoinLink, Login, Member, Session, as_utc, utcnow
from mealwright.moment import Moment
from mealwright.names import one_line
from mealwright.roles import ADMIN, Action
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
        raise ValueError(USERNAME_RULE)
    return value


class LoginOut(BaseModel):
    username: str
    role: Role
    shared: bool
    # False while the person hasn't used their sign-in link yet.
    has_password: bool
    # Signs in, by password or by single sign-on (0.9 O1): false only while a sign-in link
    # waits or has run out.
    signs_in: bool
    # An unused sign-in link that hasn't run out.
    link_pending: bool
    # When a sign-in or Reset password link last set this password (0.9.5; cabledrawer 13 Nov:
    # "Link used today 21:40", so an admin can spot a link someone else used).
    link_used_at: Moment | None
    # An unused Reset password link that hasn't run out (Pe1).
    reset_pending: bool
    # Linked to an account at the household's saved sign-in server (0.9.5 Pe3).
    sso_linked: bool = False
    # That account's username at the sign-in server, once it has signed in here.
    sso_username: str | None = None


class HouseholdPerson(BaseModel):
    id: int
    name: str
    colour: Colour | None
    portion_quarters: int
    login: LoginOut | None
    # The signed-in login's own person.
    is_me: bool
    created_at: Moment
    created_by_name: str


class WaitingSignIn(BaseModel):
    """A single sign-on sign-in that matches nobody and waits for an admin (0.9.5 Pe3/M2)."""

    id: int
    # Its username at the sign-in server, as sent.
    username: str
    # Its last sign-in here.
    signed_in_at: Moment
    # What the sign-in server's groups made it: an admin's login is offered only for "admin".
    role: Role


class PeopleOut(BaseModel):
    people: list[HouseholdPerson]
    # False for a member: they see the people and can't change them.
    can_change: bool
    # The household switch: shared logins ask "Who's this?" (off at first).
    ask_whos_this: bool
    # After a change: the change, for its Undo.
    change: ChangeOut | None = None
    # "Who is this?" (0.9.5 Pe3/M2): single sign-on sign-ins waiting for an admin, newest
    # first. Empty for a member.
    waiting: list[WaitingSignIn] = []
    # Single sign-on is set up (0.9.5 Pe3/M2): the Person page shows who is linked. False for a
    # member.
    single_sign_on: bool = False


def _person(kitchen: Here, member: Member, issuer: str | None, can_change: bool) -> HouseholdPerson:
    login = people.login_of(kitchen, member)
    # Who is linked to single sign-on is for those who can change people (B7 low).
    account = (
        sso_people.account_of(kitchen, login, issuer) if login is not None and can_change else None
    )
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
            signs_in=people.signs_in(login),
            link_pending=people.link_pending(kitchen, login),
            reset_pending=people.link_pending(kitchen, login, people.RESET),
            link_used_at=as_utc(login.link_used_at) if login.link_used_at else None,
            sso_linked=can_change and sso_people.linked_here(kitchen, login, issuer),
            sso_username=account.username if account is not None else None,
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
    issuer = sso_people.saved_issuer(kitchen)
    can_change = kitchen.may(Action.PEOPLE)
    return PeopleOut(
        people=[_person(kitchen, m, issuer, can_change) for m in members],
        can_change=can_change,
        ask_whos_this=kitchen.household.ask_whos_this,
        waiting=[
            WaitingSignIn(
                id=account.id,
                username=account.username,
                signed_in_at=as_utc(account.seen_at),
                role="admin" if account.role == ADMIN else "member",
            )
            for account in sso_people.waiting(kitchen)
        ]
        if can_change
        else [],
        single_sign_on=can_change and issuer is not None,
    )


@router.get("/people")
def list_people(kitchen: Here) -> PeopleOut:
    """Everyone in the household who hasn't been removed, in the order they were added."""
    return _people(kitchen)


def _start(kitchen: Here, response: Response) -> Change | None:
    """Admins only; the household's lock. A retry of a change already made: that change."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    earlier = replayed(kitchen)
    if earlier is not None:
        response.headers["Idempotent-Replayed"] = "true"
    return earlier


def _finish(kitchen: Here, response: Response, made: Change | None) -> PeopleOut:
    """Commit, and answer with everyone and the change made (for its Undo)."""
    earlier = commit(kitchen)
    if earlier is not None:  # lost the race to the same change: answer as for a retry
        response.headers["Idempotent-Replayed"] = "true"
        made = earlier
    return _out(kitchen, made)


def _out(kitchen: Here, made: Change | None) -> PeopleOut:
    out = _people(kitchen)
    if made is not None and made.kind in people.KINDS:  # not a kept key ("setting_kept")
        out.change = change_out(kitchen, made)
    return out


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
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    return _finish(
        kitchen, response, people.add(kitchen, body.name, body.colour, body.portion_quarters)
    )


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


@router.patch("/people/{person_id}")
def change_person(
    person_id: StoredInt, body: PersonChange, kitchen: Here, response: Response
) -> PeopleOut:
    """Change a person's name, colour, portion, role or whether their login is shared. The
    household's only admin can't be made a member. Admins only."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    member = people.mine(kitchen, person_id)
    # Null means "no colour"; for the others it means "as it is".
    wanted = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if value is not None or key == "colour"
    }
    made = people.change(kitchen, member, wanted)
    if made is None:
        key_kept(kitchen)
    return _finish(kitchen, response, made)


@router.delete("/people/{person_id}")
def remove_person(
    person_id: StoredInt, kitchen: Here, response: Response, request: Request
) -> PeopleOut:
    """Remove a person: their meals, tubs and history stay, Recent changes shows "Joss
    (removed)", and their login can't sign in. Undo puts them back. Admins only; nobody can
    remove themselves, and the household always keeps an admin."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    member = people.mine(kitchen, person_id)
    # Their sign-ins end with them: so do their open live-update streams (O2 review r4, finding 4).
    ended = list(
        kitchen.db.scalars(
            select(Session.id)
            .join(Login, Login.id == Session.login_id)
            .where(Login.member_id == member.id)
        )
    )
    out = _finish(kitchen, response, people.remove(kitchen, member))
    for session_id in ended:
        request.app.state.events.end_session(session_id)
    return out


class LoginIn(BaseModel):
    username: str
    role: Role = "member"

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        return _username(value)


class LinkOut(BaseModel):
    # The path of the link, "/join#<token>" or "/reset#<token>": shown once, never stored. The
    # secret follows a `#`, so opening the link never sends it to the server (cabledrawer 13 Nov).
    path: str
    expires_at: Moment


@router.post("/people/{person_id}/login", status_code=status.HTTP_201_CREATED)
def give_login(person_id: StoredInt, body: LoginIn, kitchen: Here) -> LinkOut:
    """Give a person a login: a one-time sign-in link, for 24 hours, where they choose their
    own password. Asking again makes a new link and the old one stops working. Admins only."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    member = people.mine(kitchen, person_id)
    token, link = people.give_login(kitchen, member, body.username, body.role)
    kitchen.idempotency_key = None  # a retry makes a new link: the token is never stored
    kitchen.db.commit()
    log.info("Sign-in link made for %s by %s", body.username, kitchen.login.username)
    return LinkOut(path=f"/join#{token}", expires_at=as_utc(link.expires_at))


@router.post("/people/{person_id}/reset-password", status_code=status.HTTP_201_CREATED)
def reset_password(person_id: StoredInt, kitchen: Here) -> LinkOut:
    """Reset password: a one-time link, for 24 hours, where the person chooses a new password;
    their recipes, plans and history stay as they are. Asking again makes a new link and the old
    one stops working, as does any unused sign-in link. Not for your own password. Admins
    only."""
    # Pe1, cabledrawer 13 Nov.
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    member = people.mine(kitchen, person_id)
    token, link = people.give_reset_link(kitchen, member)
    login = people.login_of(kitchen, member)
    kitchen.idempotency_key = None  # a retry makes a new link: the token is never stored
    kitchen.db.commit()
    # A sign-in line names the person by username, never by name (D4, BE24).
    log.info(
        "Reset link made for %s by %s", login.username if login else "?", kitchen.login.username
    )
    return LinkOut(path=f"/reset#{token}", expires_at=as_utc(link.expires_at))


@router.delete("/people/{person_id}/login", status_code=status.HTTP_204_NO_CONTENT)
def take_back_login(person_id: StoredInt, kitchen: Here) -> None:
    """ "Profile only" again, while the person's sign-in link is unused: the link stops working.
    Admins only."""
    kitchen.admin_only(Action.PEOPLE)
    lock_db(kitchen.db, kitchen.household)
    people.take_back_login(kitchen, people.mine(kitchen, person_id))
    kitchen.db.commit()


class SsoLinkIn(BaseModel):
    # The person to link the account to; null: "A new person".
    member_id: StoredInt | None


@router.post("/people/sso-accounts/{account_id}/link")
def link_sso_account(
    account_id: StoredInt, body: SsoLinkIn, kitchen: Here, response: Response
) -> PeopleOut:
    """ "Who is this?": link a single sign-on account that is linked to nobody to a person of
    the household, or to a new person (`member_id` null). The person signs in with single
    sign-on again to get in. Admins only."""
    # 0.9.5 Pe3/M2, cabledrawer 13 Nov. Not in the docstring: that is the public API description.
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    account = sso_people.unlinked(kitchen, account_id)
    if body.member_id is None:
        made = sso_people.new_person(kitchen, account)
    else:
        made = sso_people.link_to(kitchen, account, body.member_id)
    log.info("Single sign-on: %s linked by %s", account.username, kitchen.login.username)
    return _finish(kitchen, response, made)


@router.post("/people/sso-accounts/{account_id}/refuse")
def refuse_sso_account(account_id: StoredInt, kitchen: Here, response: Response) -> PeopleOut:
    """ "Not someone I know: refuse": the single sign-on account can't sign in until an admin
    links it after all. Admins only."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    account = sso_people.unlinked(kitchen, account_id)
    made = sso_people.refuse(kitchen, account)
    log.info("Single sign-on: %s refused by %s", account.username, kitchen.login.username)
    return _finish(kitchen, response, made)


@router.delete("/people/{person_id}/sso")
def unlink_sso(
    person_id: StoredInt, request: Request, kitchen: Here, response: Response
) -> PeopleOut:
    """Unlink a person from their account at the sign-in server (0.9.5 Pe3/M2, Person page). The
    account waits for an admin at its next sign-in, and the person's single sign-on sign-ins end.
    Never the household's last admin who can sign in, when single sign-on is their only way in
    (#205 b/d). Admins only."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    ended = list(
        kitchen.db.scalars(
            select(Session.id)
            .join(Login, Login.id == Session.login_id)
            .where(
                Login.member_id == person_id,
                Login.household_id == kitchen.household_id,
                Session.sso.is_(True),
            )
        )
    )
    unlinked = people.login_of(kitchen, people.mine(kitchen, person_id))
    made = sso_people.unlink(kitchen, person_id)
    log.info(
        "Single sign-on: %s unlinked by %s",
        unlinked.username if unlinked else "?",
        kitchen.login.username,
    )
    answer = _finish(kitchen, response, made)
    for session_id in ended:  # their open live-update streams end with their sign-ins
        request.app.state.events.end_session(session_id)
    return answer


class SwitchIn(BaseModel):
    on: StrictBool


@router.put("/people/ask-whos-this")
def switch_whos_this(body: SwitchIn, kitchen: Here, response: Response) -> PeopleOut:
    """The household switch: shared logins ask "Who's this?". Admins only."""
    earlier = _start(kitchen, response)
    if earlier is not None:
        return _out(kitchen, earlier)
    made = people.ask_whos_this(kitchen, body.on)
    if made is None:
        key_kept(kitchen)
    return _finish(kitchen, response, made)


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


def _whos_this(kitchen: Here, signed_in: CurrentSession) -> WhosThisOut:
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
def whos_this(kitchen: Here, signed_in: CurrentSession) -> WhosThisOut:
    return _whos_this(kitchen, signed_in)


class PickIn(BaseModel):
    # Null: "Just looking", nobody picked.
    member_id: StoredInt | None


@router.put("/whos-this")
def pick(body: PickIn, kitchen: Here, signed_in: CurrentSession) -> WhosThisOut:
    """Pick who is using this shared login on this device: their changes are recorded as
    theirs. Only a shared login can pick, and only a person of the household."""
    if not signed_in.login.shared:
        raise Problem(
            status.HTTP_409_CONFLICT, "not_shared", "Only a shared login asks “Who’s this?”."
        )
    if body.member_id is not None and body.member_id not in {m.id for m in people.eaters(kitchen)}:
        raise not_found("That person")
    signed_in.session.member_id = body.member_id
    signed_in.session.picked_at = utcnow() if body.member_id is not None else None
    kitchen.db.commit()
    kitchen.member_id = acting_member(
        kitchen.db, signed_in.login, kitchen.household, signed_in.session
    )
    return _whos_this(kitchen, signed_in)


# --- The sign-in link -------------------------------------------------------------------------
#
# The link is "/join#<secret>" (link hardening, cabledrawer 13 Nov): what follows a `#` never leaves
# the browser, so the secret is never in a request line, a reverse proxy's access log or a
# Referer. The page reads it, clears it from the address bar, and posts it in the body, both to
# look at the link and to use it. Neither answer names anyone before the password is set: only
# the answer to choosing a password gives the username, to sign in with.


class LinkSecretIn(BaseModel):
    # Checked by `_link`: one longer than any real secret is simply "used or run out".
    token: Annotated[str, Field(max_length=1000)]


class JoinOut(BaseModel):
    # "join": a sign-in link, choosing a first password; "reset": a Reset password link.
    kind: Literal["join", "reset"]
    expires_at: Moment
    min_password: int


LINK_GONE = (
    "This sign-in link has been used or has run out. Ask your household’s admin for a new one."
)


def _link_gone() -> Problem:
    """An unknown, used or run-out link: one answer for all three (cabledrawer 12 Nov), so a guess
    never learns which links exist. A 404 with its own code, as the sign-in page words it its
    own way (0.9.5-beta.3, D2; proposed, for cabledrawer)."""
    return Problem(status.HTTP_404_NOT_FOUND, "link_gone", LINK_GONE)


# Pe2 (cabledrawer 13 Nov): a link opened where someone is already signed in simply refuses, with
# no names and no sign-out, and the link stays unused. The words are words.md section 81's.
SIGNED_IN_HERE = (
    "Someone is already signed in on this device. Sign-in links only work where nobody is "
    "signed in."
)


def _nobody_signed_in(request: Request, db: Db) -> None:
    """Refuse (409 `signed_in_here`) while the request carries a live session cookie. Checked
    before the link is even looked up, so the link stays as it was."""
    if peek_session(db, session_token(request)) is not None:
        raise Problem(status.HTTP_409_CONFLICT, "signed_in_here", SIGNED_IN_HERE)


def _link(db: Db, token: str) -> tuple[JoinLink, Login, Member]:
    found = people.find_link(db, token) if len(token) <= 100 else None
    if found is None:
        raise _link_gone()
    return found


@router.post("/join/look")
def join_link(body: LinkSecretIn, request: Request, db: Db) -> JoinOut:
    """What the sign-in link page needs before the password is chosen: whether the link still
    works, and until when. No name or username. Needs no sign-in, and is refused where someone
    is signed in."""
    # No names before the password is set: cabledrawer 13 Nov.
    _nobody_signed_in(request, db)
    link, _login, _member = _link(db, body.token)
    return JoinOut(
        kind="reset" if link.kind == people.RESET else "join",
        expires_at=as_utc(link.expires_at),
        min_password=JOIN_MIN_PASSWORD,
    )


class JoinIn(LinkSecretIn):
    password: str = Field(min_length=JOIN_MIN_PASSWORD, max_length=MAX_PASSWORD)


class JoinDone(BaseModel):
    # The username to sign in with: named only now the password is set (cabledrawer 13 Nov).
    username: str


@router.post("/join")
def join(body: JoinIn, request: Request, db: Db) -> JoinDone:
    """Choose a password with a sign-in or Reset password link. The link works once. Refused
    where someone is signed in."""
    # The person then signs in on the sign-in page like anyone else, so a phone holding
    # someone else's waiting changes warns first there (cabledrawer 12 Nov).
    needs_https(request, request.app.state.settings)
    _nobody_signed_in(request, db)
    link, login, _member = _link(db, body.token)
    link_id = link.id
    # Claim the link first, so of two requests at once only one sets a password.
    if not people.claim_link(db, link):
        raise _link_gone()
    ended: list[int] = []
    try:
        login.password_hash = hash_password(body.password)
        login.link_used_at = utcnow()
        if link.kind == people.RESET:
            # Like a password changed in Settings: the Person page's "Set" date, and the
            # username's pause doesn't keep them out of it. And like reset-admin, the login is
            # signed out everywhere and its API tokens stop (proposed, for cabledrawer): someone who
            # used a link meant for this person loses the login when they reset again.
            login.password_changed_at = login.link_used_at
            # Their open live-update streams end too, as when a person is removed (S-L3).
            ended = list(db.scalars(select(Session.id).where(Session.login_id == login.id)))
            db.execute(delete(Session).where(Session.login_id == login.id))
            api_tokens.stop_for(db, login.id)
        # The hash is slow: the link may have been cancelled meanwhile (a new link, a password
        # change, an admin made a member...). Checked again after the writes, which hold the
        # database's write lock until the commit, so nothing can cancel it in between; a link
        # gone sets no password (16b security pass S-L2).
        # The login itself may have gone too ("Profile only"): then the write matches no row,
        # and the link has gone with it (16b security re-check note).
        try:
            db.flush()
        except StaleDataError:
            still = None
        else:
            still = db.scalar(select(JoinLink.id).where(JoinLink.id == link_id).with_for_update())
        if still is None:
            db.rollback()
        else:
            db.commit()
    except Exception:
        people.give_back_link(db, link)
        raise
    if still is None:
        raise _link_gone()
    for session_id in ended:
        request.app.state.events.end_session(session_id)
    how = (
        "Password reset with a reset link"
        if link.kind == people.RESET
        else "Joined with a sign-in link"
    )
    log.info("%s: %s from %s", how, login.username, client_address(request))
    return JoinDone(username=login.username)
