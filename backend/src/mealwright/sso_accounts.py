"""Single sign-on's accounts and sign-ins (0.9 O1): the database side of `mealwright.sso`.

- **Which login.** A login is found only by the provider's issuer and subject together
  (`sub`), never by a user name or email address, so a provider can't take over an existing
  password account by naming it. A new person gets an account on first sign-in when the admin
  allows that; if their user name is taken already, they're refused with a clear message
  (proposed, for cabledrawer).
- **Which role.** On every sign-in, the groups the provider sends decide: any group mapped to
  Admin gives Admin, else any mapped to Member gives Member, else "Anyone else" (Not let in, the
  default, or Member; proposed, for cabledrawer). The household's last admin who can sign in is
  never made a Member this way (proposed, for cabledrawer).
- **Staying signed in.** A single sign-on sign-in keeps the provider's refresh token, sealed
  (`mealwright.secret_box`). Every CHECK_EVERY a job asks the provider with it: if the provider
  says the sign-in is over (the person was removed or signed out there), Mealwright signs them
  out too; if the provider can't be reached, it tries again later. Mealwright's own session
  rules (12 hours idle, 30 days with "Remember") still apply on top. Signing out deletes the
  session row, and the token with it.

Nothing here logs a token, the client secret or a claim, only the account's user name.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from mealwright import sso
from mealwright.auth import now
from mealwright.models import Login, Member, Session, SsoSettings
from mealwright.outbound import Connection, OutboundGate, switches
from mealwright.people import admin_can_sign_in
from mealwright.roles import ADMIN, MEMBER
from mealwright.secret_box import SecretUnreadable, open_sealed, seal
from mealwright.sso import Client, Identity, SsoFailed

log = logging.getLogger("mealwright.sign_in")

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")


def settings_row(db: DbSession, household_id: int | None = None) -> SsoSettings | None:
    """The household's single sign-on setup. With no household given, the install's (one
    household per install, spec section 3)."""
    query = select(SsoSettings)
    if household_id is not None:
        query = query.where(SsoSettings.household_id == household_id)
    return db.scalar(query.order_by(SsoSettings.household_id).limit(1))


def usable(row: SsoSettings | None) -> bool:
    return row is not None and bool(row.client_secret_sealed)


def switch_on(db: DbSession, household_id: int) -> bool:
    return switches(db, household_id)[Connection.SINGLE_SIGN_ON]


def password_sign_in_on(db: DbSession, data_dir: Path) -> bool:
    """Password sign-in works unless an admin turned it off with single sign-on set up,
    switched on, and its saved secret readable. With the switch off, passwords work again,
    so nobody is locked out (proposed, for cabledrawer). The same when single sign-on can't
    work at all (O1 review r1 M3): the saved client secret can't be opened (the key file
    `secret.key` is lost or isn't Mealwright's), or the setup can't be read. The reset-admin
    command turns it back on too."""
    try:
        row = settings_row(db)
        if row is None or row.password_sign_in or not usable(row):
            return True
        if not switch_on(db, row.household_id):
            return True
        open_sealed(data_dir, str(row.client_secret_sealed))
    except SecretUnreadable:
        return True
    except SQLAlchemyError, ValueError, TypeError:
        db.rollback()
        return True
    return False


def same_secret(row: SsoSettings, data_dir: Path, typed: str) -> bool:
    """True when `typed` is the client secret already saved (typed again, not changed)."""
    if not row.client_secret_sealed:
        return False
    try:
        saved = open_sealed(data_dir, row.client_secret_sealed)
    except SecretUnreadable:
        return False
    return secrets.compare_digest(saved.encode(), typed.encode())


def client(row: SsoSettings, data_dir: Path) -> Client:
    """The setup with its secret opened. Raises SsoFailed."""
    if not row.client_secret_sealed:
        raise SsoFailed("not_set_up")
    try:
        secret = open_sealed(data_dir, row.client_secret_sealed)
    except SecretUnreadable:
        raise SsoFailed("secret_unreadable") from None
    return Client(
        household_id=row.household_id,
        issuer=row.issuer,
        client_id=row.client_id,
        client_secret=secret,
        redirect_uri=row.redirect_uri,
        group_claim=row.group_claim,
    )


def role_for(row: SsoSettings, groups: list[str]) -> str | None:
    """Admin, Member, or None (not let in)."""
    mapped = {
        entry["role"]
        for entry in row.group_roles or []
        if isinstance(entry, dict) and entry.get("group") in groups
    }
    if ADMIN in mapped:
        return ADMIN
    if MEMBER in mapped:
        return MEMBER
    return MEMBER if row.anyone_else == MEMBER else None


def other_admins(db: DbSession, login: Login) -> int:
    """Admins of this household who can sign in, apart from `login` (not shared ones). With
    password sign-in off, only admins linked by single sign-on count (O1 review r1 M3)."""
    query = (
        select(func.count())
        .select_from(Login)
        .join(Member, Member.id == Login.member_id)
        .where(Login.household_id == login.household_id, Login.role == ADMIN)
        .where(admin_can_sign_in(db, login.household_id))
        .where(Login.shared.is_(False), Login.id != login.id)
    )
    return int(db.scalar(query) or 0)


def admin_signs_in_with_sso(db: DbSession, row: SsoSettings) -> bool:
    """True when an admin of the household has signed in with single sign-on at the saved
    issuer (or passed the setup screen's test), so turning password sign-in off can't lock
    every admin out (proposed, for cabledrawer)."""
    query = (
        select(func.count())
        .select_from(Login)
        .join(Member, Member.id == Login.member_id)
        .where(Login.household_id == row.household_id, Login.role == ADMIN)
        .where(Login.shared.is_(False), Member.removed_at.is_(None))
        .where(Login.sso_issuer == row.issuer, Login.sso_subject.is_not(None))
    )
    return bool(db.scalar(query))


def _removed(db: DbSession, login: Login) -> bool:
    member = db.get(Member, login.member_id) if login.member_id is not None else None
    return member is not None and member.removed_at is not None


def new_username(identity: Identity) -> str:
    """From the provider's user name, else the email address's first part, else made from the
    subject. Lowercase, as every Mealwright user name is."""
    for raw in (identity.username, (identity.email or "").split("@")[0]):
        value = (raw or "").strip().lower()
        if USERNAME.match(value):
            return value
    digest = hashlib.sha256(f"{identity.issuer} {identity.subject}".encode()).hexdigest()
    return f"sso-{digest[:10]}"


def find_login(db: DbSession, identity: Identity) -> Login | None:
    return db.scalar(
        select(Login).where(
            Login.sso_issuer == identity.issuer, Login.sso_subject == identity.subject
        )
    )


def login_for(db: DbSession, row: SsoSettings, identity: Identity) -> Login:
    """The login this identity signs in as, made on first sign-in if allowed, with its role
    from the groups. Raises SsoFailed. Flushes, doesn't commit."""
    role = role_for(row, identity.groups)
    login = find_login(db, identity)
    if login is None:
        if role is None:
            raise SsoFailed("not_let_in")
        if not row.make_accounts:
            raise SsoFailed("no_account")
        username = new_username(identity)
        if db.scalar(select(Login.id).where(Login.username == username)) is not None:
            raise SsoFailed("clash")
        login = Login(
            household_id=row.household_id,
            username=username,
            name=(identity.name or username)[:100],
            password_hash=None,
            role=role,
            sso_issuer=identity.issuer,
            sso_subject=identity.subject,
        )
        db.add(login)
        db.flush()
        log.info("Single sign-on: account %s made on first sign-in", login.username)
        return login
    if login.household_id != row.household_id or _removed(db, login):
        raise SsoFailed("removed")
    if role is None:
        raise SsoFailed("not_let_in")
    if login.role != role:
        if login.role == ADMIN and other_admins(db, login) == 0:
            log.warning(
                "Single sign-on: %s stays an admin, as the household's last one", login.username
            )
        else:
            log.info("Single sign-on: %s is now %s, from the groups", login.username, role)
            login.role = role
    return login


type Link = Literal["can", "linked", "no"]


def _someone_else(db: DbSession, login: Login, issuer: str, subject: str) -> None:
    """Raise SsoFailed("someone_else") when this identity is another login's, or `login` is
    linked to another identity at this issuer."""
    other = db.scalar(select(Login).where(Login.sso_issuer == issuer, Login.sso_subject == subject))
    if other is not None and other.id != login.id:
        raise SsoFailed("someone_else")
    if (
        login.sso_issuer == issuer
        and login.sso_subject is not None
        and login.sso_subject != subject
    ):
        raise SsoFailed("someone_else")


def outcome_of_test(
    db: DbSession, row: SsoSettings, login: Login, identity: Identity
) -> tuple[str | None, Link]:
    """The setup screen's test, signed in as `login` (an admin): the role the groups would
    give (None: not let in), and whether this identity can be linked to that login. A test
    links nothing and changes no role (O1 review r1 H1). Only an identity the groups make an
    Admin can be linked, and only by the admin's own confirmation afterwards (`link`): a
    Member at the sign-in server who happens to be signed in there in the admin's browser
    must never become the admin. Raises SsoFailed."""
    role = role_for(row, identity.groups)
    _someone_else(db, login, identity.issuer, identity.subject)
    if login.sso_issuer == identity.issuer and login.sso_subject == identity.subject:
        return role, "linked"
    return role, "can" if role == ADMIN else "no"


def link(db: DbSession, row: SsoSettings, login: Login, issuer: str, subject: str) -> None:
    """Link `login` (an admin) to the identity their test found, once they have confirmed
    it. Checked again now: the setup's issuer is still the test's, and nobody else has the
    identity. Raises SsoFailed. Flushes, doesn't commit."""
    if row.issuer != issuer or login.role != ADMIN or login.household_id != row.household_id:
        raise SsoFailed("link_gone")
    _someone_else(db, login, issuer, subject)
    login.sso_issuer, login.sso_subject = issuer, subject
    db.flush()
    log.info("Single sign-on: %s linked after the setup test, confirmed", login.username)


def keep(db: DbSession, data_dir: Path, session: Session, identity: Identity) -> None:
    """Mark a new session as single sign-on's, with its refresh token sealed."""
    session.sso = True
    if identity.refresh_token:
        session.sso_refresh_sealed = seal(data_dir, identity.refresh_token)
        session.sso_check_at = now() + sso.CHECK_EVERY


def _due(at: datetime) -> ColumnElement[bool]:
    return and_(
        Session.sso.is_(True),
        Session.sso_refresh_sealed.is_not(None),
        Session.sso_check_at <= at,
        Session.expires_at > at,
    )


def check_sessions(gate: OutboundGate, factory: sessionmaker[DbSession], data_dir: Path) -> int:
    """The job: ask the provider about each single sign-on sign-in that's due. Gives how many
    were signed out."""
    ended = 0
    at = now()
    with factory() as db:
        due = db.scalars(select(Session).where(_due(at)).limit(200)).all()
        for session in due:
            row = settings_row(db, session.household_id)
            if row is None or not usable(row):
                session.sso_check_at = None  # nothing to ask any more
                continue
            try:
                setup = client(row, data_dir)
                token = open_sealed(data_dir, str(session.sso_refresh_sealed))
            except SsoFailed, SecretUnreadable:
                session.sso_check_at = at + sso.RETRY_AFTER
                continue
            result, new = sso.refresh(gate, setup, token)
            if result == "ended":
                login = db.get(Login, session.login_id)
                db.delete(session)
                ended += 1
                log.info(
                    "Single sign-on: %s signed out, as the sign-in server ended the sign-in",
                    login.username if login else "someone",
                )
            elif result == "ok":
                if new:
                    session.sso_refresh_sealed = seal(data_dir, new)
                session.sso_check_at = at + sso.CHECK_EVERY
            else:
                session.sso_check_at = at + sso.RETRY_AFTER
        db.commit()
    return ended
