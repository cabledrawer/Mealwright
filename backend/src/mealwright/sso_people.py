"""Single sign-on and the household's people (0.9.5 Pe3/M2, cabledrawer 13 Nov): "Who is this?".

A first single sign-on sign-in is linked automatically only to the person with exactly the same
username (`mealwright.sso_accounts`). Anyone else waits, with no session, until an admin says
who they are on Settings › People. cabledrawer 13 Nov: "Who is this?" offers link to a person, a
new person, or refuse. A refusal lasts until an admin links that account after all.

Everything here is for an admin of the household (the API checks `Action.PEOPLE`), and only for
accounts at the household's saved sign-in server: an account of an earlier setup is never
listed or linked. Recent changes says what was done, with no Undo of its own (`LINK_KIND`).
"""

import hashlib

from fastapi import status
from sqlalchemy import delete, select

from mealwright import api_tokens
from mealwright.api.v1.context import Kitchen
from mealwright.auth import now
from mealwright.errors import Problem, not_found
from mealwright.history import record
from mealwright.models import Change, Login, Member, Session, SsoAccount, utcnow
from mealwright.people import (
    LINK_KIND,
    admins_left,
    drop_join_links,
    free_old_usernames,
    login_of,
    mine,
)
from mealwright.roles import ADMIN, MEMBER
from mealwright.sso_accounts import USERNAME, member_name, passwords_off, settings_row
from mealwright.sso_changes import ADDED, LINKED, REFUSED, UNLINKED, for_everyone

# Proposed, for cabledrawer (the refusals aren't in the mockups).
SHARED = "A shared login isn’t one person, so it can’t be linked to single sign-on."
LINKED_ALREADY = (
    "{name} is linked to another account at your sign-in server. Unlink it on their page first."
)
NEEDS_ADMIN = (
    "{name} is an admin here, and your sign-in server’s groups don’t make this account an "
    "admin. Link it to someone else, or change the groups first."
)
NOT_LINKED = "{name} isn’t linked to an account at your sign-in server."
LAST_WAY_IN = (
    "{name} is the household’s only admin who can sign in, and only with single sign-on. "
    "Make someone else an admin first, or set a password for {name}."
)


def _refused(code: str, detail: str) -> Problem:
    return Problem(status.HTTP_409_CONFLICT, code, detail)


def saved_issuer(kitchen: Kitchen) -> str | None:
    row = settings_row(kitchen.db, kitchen.household_id)
    return row.issuer if row is not None else None


def linked_here(kitchen: Kitchen, login: Login, issuer: str | None) -> bool:
    """The login is linked to an account at the saved sign-in server."""
    return issuer is not None and login.sso_issuer == issuer and login.sso_subject is not None


def account_of(kitchen: Kitchen, login: Login, issuer: str | None) -> SsoAccount | None:
    """The account a login is linked to at the saved sign-in server, if it has signed in."""
    if not linked_here(kitchen, login, issuer):
        return None
    return kitchen.db.scalar(
        select(SsoAccount).where(
            SsoAccount.household_id == kitchen.household_id,
            SsoAccount.issuer == issuer,
            SsoAccount.subject == login.sso_subject,
        )
    )


def waiting(kitchen: Kitchen) -> list[SsoAccount]:
    """The sign-ins waiting for an admin, the newest first."""
    issuer = saved_issuer(kitchen)
    if issuer is None:
        return []
    return list(
        kitchen.db.scalars(
            select(SsoAccount)
            .where(
                SsoAccount.household_id == kitchen.household_id,
                SsoAccount.issuer == issuer,
                SsoAccount.waiting_since.is_not(None),
                SsoAccount.refused_at.is_(None),
            )
            .order_by(SsoAccount.seen_at.desc(), SsoAccount.id.desc())
        )
    )


def _linked_login(kitchen: Kitchen, account: SsoAccount) -> Login | None:
    return kitchen.db.scalar(
        select(Login).where(
            Login.sso_issuer == account.issuer, Login.sso_subject == account.subject
        )
    )


def unlinked(kitchen: Kitchen, account_id: int) -> SsoAccount:
    """This household's account at the saved sign-in server that is linked to nobody, or 404
    (another household's, an earlier setup's, or linked meanwhile)."""
    issuer = saved_issuer(kitchen)
    account = kitchen.db.get(SsoAccount, account_id)
    if (
        account is None
        or account.household_id != kitchen.household_id
        or account.issuer != issuer
        or _linked_login(kitchen, account) is not None
    ):
        raise not_found("That sign-in")
    return account


def free_username(kitchen: Kitchen, account: SsoAccount) -> str:
    """A Mealwright username for a login made for this account: its username at the sign-in
    server in lowercase when that is a username Mealwright allows, else one made from the
    account; with "-2", "-3"... when that is taken (proposed, for cabledrawer)."""
    base = account.username.strip().lower()
    if not USERNAME.match(base):
        digest = hashlib.sha256(f"{account.issuer} {account.subject}".encode()).hexdigest()
        base = f"sso-{digest[:10]}"
    free_old_usernames(kitchen.db)  # a removed person's name, after the Undo
    candidate, number = base, 2
    while kitchen.db.scalar(select(Login.id).where(Login.username == candidate)) is not None:
        ending = f"-{number}"
        candidate = base[: 50 - len(ending)] + ending
        number += 1
    return candidate


def _done(kitchen: Kitchen, account: SsoAccount, login: Login) -> None:
    login.sso_issuer, login.sso_subject = account.issuer, account.subject
    drop_join_links(kitchen.db, login)  # an unused sign-in link must not work again after Unlink
    account.waiting_since = None
    account.refused_at = None
    account.unlinked_at = None
    kitchen.db.flush()


def link_to(kitchen: Kitchen, account: SsoAccount, member_id: int) -> Change:
    """Link the account to a person of the household. A person with no login gets one, with no
    password, made a Member or an Admin as the groups made the account at its last sign-in; its
    role follows the groups at each sign-in from then on, as every single sign-on login's does."""
    member = mine(kitchen, member_id)
    login = login_of(kitchen, member)
    if login is not None:
        if login.shared:
            raise _refused("shared_login", SHARED)
        if linked_here(kitchen, login, account.issuer):
            raise _refused("linked_already", LINKED_ALREADY.format(name=member.name))
        if login.role == ADMIN and account.role != ADMIN:
            # As at a first sign-in (`sso_accounts._match`): an account the groups make a
            # Member never takes over an admin.
            raise _refused("needs_admin", NEEDS_ADMIN.format(name=member.name))
    else:
        login = Login(
            household_id=kitchen.household_id,
            username=free_username(kitchen, account),
            name=member.name,
            password_hash=None,
            role=ADMIN if account.role == ADMIN else MEMBER,
            member_id=member.id,
            created_at=utcnow(),
        )
        kitchen.db.add(login)
    _done(kitchen, account, login)
    return record(
        kitchen,
        LINK_KIND,
        f"Linked {member.name} to {account.username} at your sign-in server",  # proposed
        None,
        for_everyone(LINKED.format(name=member.name)),
    )


def new_person(kitchen: Kitchen, account: SsoAccount) -> Change:
    """Make a new person for the account, named as the sign-in server names them, with a login
    linked to it."""
    username = free_username(kitchen, account)
    member = Member(
        household_id=kitchen.household_id,
        name=member_name(kitchen.db, kitchen.household_id, account.name, username),
        portion_quarters=4,
        created_at=utcnow(),
        created_by_name=kitchen.login.name,
    )
    kitchen.db.add(member)
    kitchen.db.flush()
    login = Login(
        household_id=kitchen.household_id,
        username=username,
        name=member.name,
        password_hash=None,
        role=ADMIN if account.role == ADMIN else MEMBER,
        member_id=member.id,
        created_at=utcnow(),
    )
    kitchen.db.add(login)
    _done(kitchen, account, login)
    return record(
        kitchen,
        LINK_KIND,
        f"Added {member.name}, linked to {account.username} at your sign-in server",  # proposed
        None,
        for_everyone(ADDED.format(name=member.name)),
    )


def refuse(kitchen: Kitchen, account: SsoAccount) -> Change:
    """ "Not someone I know: refuse": the account can't sign in until an admin links it."""
    account.refused_at = now()
    account.waiting_since = None
    kitchen.db.flush()
    return record(
        kitchen,
        LINK_KIND,
        f"Refused {account.username} at your sign-in server",  # proposed, for cabledrawer
        None,
        for_everyone(REFUSED),
    )


def unlink(kitchen: Kitchen, member_id: int) -> Change:
    """Unlink a person's login from its account at the saved sign-in server (0.9.5 Pe3/M2,
    Person page). The account is never linked automatically again: at its next sign-in it waits
    for an admin ("Who is this?"). The person's sign-ins made with single sign-on end. The last
    admin who can sign in is never unlinked when single sign-on is their only way in (#205 b/d:
    only a working password or an accepted link counts, never a live sign-in alone)."""
    member = mine(kitchen, member_id)
    login = login_of(kitchen, member)
    issuer = saved_issuer(kitchen)
    if login is None or issuer is None or login.sso_subject is None:
        raise _refused("not_linked", NOT_LINKED.format(name=member.name))
    if not linked_here(kitchen, login, issuer):
        raise _refused("not_linked", NOT_LINKED.format(name=member.name))
    if login.role == ADMIN and not login.shared:
        off = passwords_off(kitchen.db, kitchen.data_dir, kitchen.household_id)
        keeps_a_way_in = bool(login.password_hash) and not off
        if not keeps_a_way_in and admins_left(kitchen, apart_from=member.id) == 0:
            raise _refused("last_admin", LAST_WAY_IN.format(name=member.name))
    account = account_of(kitchen, login, issuer)
    if account is None:
        # Linked before 0.9.5 kept its accounts, or by the setup test: kept from now on, so it
        # is never linked automatically again.
        account = SsoAccount(
            household_id=kitchen.household_id,
            issuer=issuer,
            subject=login.sso_subject,
            username=login.username,
            name=member.name,
            role=login.role,
            seen_at=now(),
        )
        kitchen.db.add(account)
    account.unlinked_at = now()
    account.waiting_since = None
    login.sso_issuer = None
    login.sso_subject = None
    kitchen.db.execute(delete(Session).where(Session.login_id == login.id, Session.sso.is_(True)))
    # A token is a sign-in too (review R8): the sign-in server's say-so made it, so it ends, for
    # good (a later promotion doesn't bring it back).
    api_tokens.stop_for(kitchen.db, login.id)
    api_tokens.clear_refused(kitchen.db, login)
    kitchen.db.flush()
    return record(
        kitchen,
        LINK_KIND,
        f"Unlinked {member.name} from {account.username} at your sign-in server",  # proposed
        None,
        for_everyone(UNLINKED.format(name=member.name)),
    )
