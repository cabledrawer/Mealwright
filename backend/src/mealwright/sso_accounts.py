"""Single sign-on's accounts and sign-ins (0.9 O1): the database side of `mealwright.sso`.

- **Which login.** A login is found only by the provider's issuer and subject together
  (`sub`). On an account's first sign-in it is linked automatically only to the login whose
  username is exactly its username at the sign-in server (Pe3/M2, cabledrawer 13 Nov:
  `same_username`); nobody is ever made at a sign-in. Anyone else waits (`Waiting`, the
  `sso_account` table) until an admin links them to a person, makes them a new person, or
  refuses them ("Who is this?" on Settings → Household).
- **Which role.** On every sign-in, the groups the provider sends decide: any group mapped to
  Admin gives Admin, else any mapped to Member gives Member, else "Anyone else" (Not let in, the
  default, or Member; cabledrawer 12 Nov). The household's last admin who can sign in is
  never made a Member this way (cabledrawer 12 Nov); "can sign in" means without the sign-in
  server's say: a working password, not a live sign-in and not just being linked
  (`another_admin_gets_in`; O2 review r8, proposed, for cabledrawer).
- **Staying signed in.** A single sign-on sign-in keeps the provider's refresh token when
  it gives one, sealed (`mealwright.secret_box`). `offline_access` is asked for when the
  provider lists it; if the provider refuses the sign-in for that, it is tried once more
  without, and that sign-in keeps no refresh token. Every CHECK_EVERY a job asks the provider
  with the token: if the provider refuses it (the account was removed or disabled there, or
  the token was taken back), Mealwright signs the person out too; if the provider can't be
  reached, it tries again later. An offline token outlives a sign-out at the provider, so
  signing out there does NOT end the Mealwright sign-in: an admin removing the person in
  Mealwright (or the person signing out here) does, at once. The job doesn't read the groups
  again: the role follows the groups at each sign-in. Mealwright's own session rules (12
  hours idle, 30 days with "Remember") still apply on top. Signing out deletes the session
  row, and the token with it.

Nothing here logs a token, the client secret or a claim, only the account's user name.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple, NoReturn

from sqlalchemy import ColumnElement, and_, delete, exists, false, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from mealwright import api_tokens, own_network, sso
from mealwright.auth import SSO_UNCHECKED_FOR, now
from mealwright.events import Broadcaster
from mealwright.models import Login, Member, Session, SsoAccount, SsoSettings
from mealwright.names import cut_text, fold, tidy_one_line
from mealwright.outbound import Connection, OutboundGate, switches
from mealwright.people import admin_can_sign_in, drop_admin_links, drop_join_links
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


def sso_can_start(db: DbSession, data_dir: Path | None, household_id: int) -> bool:
    """True when a single sign-on sign-in could start right now: the Privacy switch is on, the
    setup is there and its secret opens, and the sign-in server's address passes the rule the
    outbound gate applies (`sso.issuer_can_be_reached`: Your own network, port and scheme),
    decided with no network look-up. Anything it can't tell is False (O1 review r3)."""
    try:
        row = settings_row(db, household_id)
        if row is None or not usable(row) or data_dir is None:
            return False
        if not switch_on(db, household_id):
            return False
        open_sealed(data_dir, str(row.client_secret_sealed))
        listed = own_network.load(db, household_id)
        return sso.issuer_can_be_reached(row.issuer, listed)
    except SecretUnreadable, SsoFailed:
        return False
    except SQLAlchemyError, ValueError, TypeError:
        db.rollback()
        return False


def fill_memory(gate: OutboundGate, factory: sessionmaker[DbSession]) -> None:
    """After a start the memory of the sign-in server's address is empty, which would read as
    "single sign-on can't start" and open password sign-in again. For each household with
    passwords off, the switch on and a setup, make the one gated look-up that fills it. Nothing
    a signed-out person does comes here (O1 review r4, finding 1)."""
    with factory() as db:
        rows = db.scalars(select(SsoSettings).where(SsoSettings.password_sign_in.is_(False))).all()
        for row in rows:
            if not usable(row) or not switch_on(db, row.household_id):
                continue
            listed = own_network.load(db, row.household_id)
            sso.look_up_issuer(gate, row.household_id, row.issuer, listed)


def passwords_off(db: DbSession, data_dir: Path | None, household_id: int) -> bool:
    """True only while an admin turned password sign-in off AND single sign-on can start. If it
    can't (the switch is off, the secret is lost, the sign-in server is off Your own network,
    an odd port, anything we can't tell), passwords work again and nobody is locked out
    (cabledrawer 12 Nov; the whole class, O1 review r3; proposed, for cabledrawer). Every place that
    enforces "passwords off" asks this."""
    try:
        row = settings_row(db, household_id)
    except SQLAlchemyError:
        db.rollback()
        return False
    if row is None or row.password_sign_in:
        return False
    return sso_can_start(db, data_dir, household_id)


def confirms_with_sso(db: DbSession, data_dir: Path | None, login: Login) -> bool:
    """D3 (cabledrawer 13 Nov): this login confirms Delete everything with a fresh single sign-on
    sign-in instead of its password, because it signs in only with single sign-on: it has no
    password, or password sign-in is off, and it is linked at the sign-in server saved now."""
    if login.password_hash is not None and not passwords_off(db, data_dir, login.household_id):
        return False
    row = settings_row(db, login.household_id)
    return (
        usable(row)
        and row is not None
        and login.sso_issuer == row.issuer
        and login.sso_subject is not None
    )


def password_sign_in_on(db: DbSession, data_dir: Path) -> bool:
    """Password sign-in works unless `passwords_off`. The reset-admin command turns the setting
    back on too."""
    try:
        row = settings_row(db)
    except SQLAlchemyError:
        db.rollback()
        return True
    if row is None:
        return True
    return not passwords_off(db, data_dir, row.household_id)


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


def admin_signs_in_with_sso(db: DbSession, row: SsoSettings) -> bool:
    """True when an admin of the household has signed in with single sign-on at the saved
    issuer (or passed the setup screen's test), so turning password sign-in off can't lock
    every admin out (cabledrawer 12 Nov)."""
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


def another_admin_gets_in(
    db: DbSession, login: Login, off: bool, *, links: bool = False, sso_on: bool = False
) -> bool:
    """True when another admin of this household can get in. Not shared logins, not removed
    people, and never because of a sign-in that is open now alone, an API token or a link not
    used yet (#205 (d), cabledrawer 12 Nov late). By default, for the refusal of a known login at
    sign-in (O2 review r5, findings 1 to 3, accepted as built): without the sign-in server's
    say, so only a password that works (password sign-in isn't `off`); being linked is not
    enough, since the same groups that refuse `login` may refuse them. With `links`, for
    answers that last (a group demotion, the hourly check's "ended"; proposed, for cabledrawer):
    a working password, or the household's one rule `admin_can_sign_in` with a sign-in that is
    open right now (a link accepted at the saved sign-in server, not marked refused, while
    single sign-on can start (`sso_on`)). A link while signed out doesn't count, so a demotion
    waits for them (#205 (c), accepted as built)."""
    has_password = and_(Login.password_hash.is_not(None), Login.password_hash != "")  # nosec B105
    password = false() if off else has_password
    if links:
        live = exists().where(Session.login_id == Login.id, Session.expires_at > now())
        way = or_(password, and_(admin_can_sign_in(db, login.household_id, off, sso_on), live))
    else:
        way = password
    query = (
        select(func.count())
        .select_from(Login)
        .join(Member, Member.id == Login.member_id)
        .where(Login.household_id == login.household_id, Login.role == ADMIN)
        .where(Login.shared.is_(False), Login.id != login.id, Member.removed_at.is_(None))
        .where(way)
    )
    return int(db.scalar(query) or 0) > 0


# cabledrawer 14 Nov (the sentence word for word).
LOCKED_OUT = "You’d be locked out: first add another admin who signs in with a password."


def would_lock_out(db: DbSession, data_dir: Path | None, login: Login) -> bool:
    """True when ending single sign-on here (its Privacy switch off, taking away what lets
    Mealwright reach the sign-in server, or saving another sign-in server) would lock this admin
    out: they are an admin whose only way in is a single sign-on link (no password of their
    own), and no other admin has a password. Only a working password counts, theirs or another
    admin's, because every link ends with single sign-on and ending it turns password sign-in
    back on (cabledrawer 14 Nov: "first add another admin who signs in with a password"; so are the
    own-network entry, the saved issuer or client ID and "only a password counts"). It is
    `another_admin_gets_in` with passwords counted and links not: the household's one rule."""
    if login.role != ADMIN or login.shared or login.password_hash or login.sso_subject is None:
        return False
    off = passwords_off(db, data_dir, login.household_id)
    if not (off or sso_can_start(db, data_dir, login.household_id)):
        return False  # it can't start now: nothing to end
    return not another_admin_gets_in(db, login, False, links=False, sso_on=False)


def _hourly_keeps(db: DbSession, login: Login, row: SsoSettings, data_dir: Path) -> bool | None:
    """For the hourly check's "ended" answer: None to end the sign-in as before; else True or
    False (passwords are off) to keep it, as the refusal path does for the household's last way
    in who would be locked out: no other admin has a password that works, or an accepted,
    unrefused single sign-on link and a sign-in open now, and passwords are off or this admin has
    none (`_last_admin_keeps` says "sign-ins"). An admin with a password while passwords work is
    not locked out, so it ends as before."""
    if _last_admin_keeps(db, login, row, data_dir, links=True) != "sign-ins":
        return None
    return passwords_off(db, data_dir, row.household_id)


def _last_admin_keeps(
    db: DbSession, login: Login, row: SsoSettings, data_dir: Path, *, links: bool = False
) -> str:
    """What a refused login keeps (proposed, for cabledrawer; O2 review r2 to r5). An admin with no
    other admin who can get in (`another_admin_gets_in`; with `links` an accepted link counts
    too) is the household's last way in. "all": they can still sign in with a password while
    password sign-in really works (the stored setting is on, or single sign-on can't start):
    they stay an admin and keep their tokens and sign-ins. "sign-ins": any other last way in
    (passwords off, or no password of their own): their tokens stop (nobody could sign in to
    delete one) but their sign-ins stay, so they can still reach Settings; a refusal can't lock
    the household out. "": anyone else: tokens and sign-ins both end."""
    if login.role != ADMIN:
        return ""
    off = passwords_off(db, data_dir, row.household_id)
    sso_on = off or sso_can_start(db, data_dir, row.household_id)
    if another_admin_gets_in(db, login, off, links=links, sso_on=sso_on):
        return ""
    return "all" if login.password_hash and not off else "sign-ins"


def _refused_known(
    db: DbSession, login: Login, row: SsoSettings, code: str, data_dir: Path
) -> NoReturn:
    """A known login the groups (or the removal) no longer let in: its API tokens are stopped
    and every device it is signed in on is signed out (so a refused admin can't go on, or make
    a new token, from an old session), and that is committed before the refusal is raised (the
    caller rolls back on a refusal). The household's last admin who can sign in keeps what
    `_last_admin_keeps` says (O2 review r2 finding 1, r3 findings 1 and 2, r4 findings 1 and 4;
    proposed, for cabledrawer). Every refusal of a known login is here: `removed`, and `not_let_in`
    (in no mapped group, or the groups no longer name a role). The ids of the sessions ended
    are on the raised `SsoFailed`, so their live-update streams end at once."""
    keeps = _last_admin_keeps(db, login, row, data_dir)
    ended: list[int] = []
    if keeps != "all":
        api_tokens.stop_for(db, login.id)
        if keeps == "":
            ended = list(db.scalars(select(Session.id).where(Session.login_id == login.id)))
            db.execute(delete(Session).where(Session.login_id == login.id))
        else:
            api_tokens.mark_refused(db, login)  # kept signed in: no new tokens (fix13)
        if login.role == ADMIN:  # refused, as if made a member: no link to an admin
            drop_admin_links(db, login.household_id)  # outlives it (16b S-M1 d, S2-M1)
        db.commit()
        log.info(
            "Single sign-on: login %d refused (%s); %s",
            login.id,
            code,
            "their API tokens stopped; their sign-ins kept, as the last admin who can sign in"
            if keeps
            else "their sign-ins and API tokens stopped",
        )
    failure = SsoFailed(code)
    failure.ended_sessions = ended
    raise failure


def member_name(db: DbSession, household_id: int, name: str | None, username: str) -> str:
    """The name of a new person made at first sign-in. Tidied as a typed name is, and, when
    someone of the household already has that name (Settings → Household refuses two the same),
    "<name> (<username>)" (whole-0.9 S4)."""
    tidy = cut_text(tidy_one_line(name or ""), 100) or username
    taken = {
        fold(other)
        for other in db.scalars(
            select(Member.name).where(
                Member.household_id == household_id, Member.removed_at.is_(None)
            )
        )
    }
    if fold(tidy) not in taken:
        return tidy
    suffix = f" ({username})"
    number = 1
    while True:
        # A number too when "<name> (<username>)" is taken as well (proposed, for cabledrawer).
        ending = suffix if number == 1 else f"{suffix} {number}"
        candidate = cut_text(tidy, 100 - len(ending)).rstrip() + ending
        if fold(candidate) not in taken:
            return candidate
        number += 1


def same_username(identity: Identity) -> str | None:
    """The sign-in server's username as Mealwright compares it (Pe3/M2, cabledrawer 13 Nov: linked
    automatically only when it is exactly the person's Mealwright username): the
    `preferred_username` claim with spaces around it taken off, nothing else changed. No change
    of case (every Mealwright username is lowercase, so "Lorna" never matches "lorna"), never
    the email address, the name or the subject. None when the server sends none."""
    value = (identity.username or "").strip()
    return value or None


def never_signed_in(login: Login) -> bool:
    """A login nobody has used: no password, no single sign-on link now, no sign-in link used
    and never signed in (which also covers one unlinked since). The sign-in server's username is
    only its own word for who someone is (a stranger's account named " lorna " would take over
    Lorna's login), so an exact match links automatically only for a login with nothing to
    take over; any other waits in "Who is this?" for an admin."""
    return (
        not login.password_hash
        and login.sso_subject is None
        and login.last_sign_in_at is None
        and login.link_used_at is None
    )


def _match(db: DbSession, row: SsoSettings, identity: Identity, role: str) -> Login | None:
    """The login of this household this identity is linked to automatically on its first
    sign-in, or None (it waits for an admin). Only an exact username match (`same_username`)
    of a login that can take the link: not shared (a kitchen tablet is nobody's), its person
    not removed, and one that has never signed in any way (`never_signed_in`: a security pass
    finding, decided by cabledrawer 14 Nov). An admin's login only
    when the groups make the newcomer an Admin too, as the setup test's link (proposed, for
    cabledrawer): a same-named account at the sign-in server that the groups make a Member never
    takes over an admin."""
    username = same_username(identity)
    if username is None:
        return None
    login = db.scalar(
        select(Login).where(Login.household_id == row.household_id, Login.username == username)
    )
    if login is None or login.shared or _removed(db, login):
        return None
    if not never_signed_in(login):
        return None
    if login.role == ADMIN and role != ADMIN:
        return None
    return login


# At most this many sign-ins wait for an admin in a household: an older one stops waiting (it
# waits again at its next sign-in), so a sign-in server can't fill the list (proposed, for
# cabledrawer).
MOST_WAITING = 20


class Waiting(Exception):
    """An account the groups let in that is linked to nobody: it waits for an admin ("Who is
    this?"). Its row is flushed; the caller commits it and starts no session."""

    def __init__(self, account: SsoAccount) -> None:
        super().__init__("waiting")
        self.account = account


def shown_username(identity: Identity) -> str:
    """The username an admin sees for this account: the sign-in server's own, as sent, else
    Mealwright's made-up one."""
    return cut_text(same_username(identity) or new_username(identity), 255)


def seen(db: DbSession, row: SsoSettings, identity: Identity, role: str) -> SsoAccount:
    """This household's row for the account, made or brought up to date with what the sign-in
    server sent now. Flushes."""
    account = db.scalar(
        select(SsoAccount).where(
            SsoAccount.household_id == row.household_id,
            SsoAccount.issuer == identity.issuer,
            SsoAccount.subject == identity.subject,
        )
    )
    if account is None:
        account = SsoAccount(
            household_id=row.household_id, issuer=identity.issuer, subject=identity.subject
        )
        db.add(account)
    account.username = shown_username(identity)
    account.name = cut_text(tidy_one_line(identity.name or ""), 100) or None
    account.role = role
    account.seen_at = now()
    db.flush()
    return account


def _wait(db: DbSession, account: SsoAccount) -> NoReturn:
    """Put the account on the household's "Who is this?" list, keeping the list short."""
    if account.waiting_since is None:
        account.waiting_since = now()
    db.flush()
    older = db.scalars(
        select(SsoAccount)
        .where(
            SsoAccount.household_id == account.household_id,
            SsoAccount.waiting_since.is_not(None),
        )
        .order_by(SsoAccount.seen_at.desc(), SsoAccount.id.desc())
        .offset(MOST_WAITING)
    )
    for stale in older:
        stale.waiting_since = None
    db.flush()
    log.info("Single sign-on: %s waits for an admin", account.username)
    raise Waiting(account)


def login_for(db: DbSession, row: SsoSettings, identity: Identity, data_dir: Path) -> Login:
    """The login this identity signs in as, with its role from the groups. On its first
    sign-in it is linked automatically only to the login with exactly its username (`_match`),
    and never once an admin refused or unlinked it; nobody is ever made here. Raises SsoFailed,
    or Waiting for an account linked to nobody. Flushes, doesn't commit."""
    role = role_for(row, identity.groups)
    login = find_login(db, identity)
    if login is None:
        if role is None:
            raise SsoFailed("not_let_in")
        account = seen(db, row, identity, role)
        if account.refused_at is not None:
            raise SsoFailed("not_known")
        if account.unlinked_at is None:
            login = _match(db, row, identity, role)
        if login is None:
            _wait(db, account)
        login.sso_issuer, login.sso_subject = identity.issuer, identity.subject
        drop_join_links(db, login)  # an unused sign-in link must not work again after Unlink
        account.waiting_since = None
        db.flush()
        log.info("Single sign-on: %s linked on first sign-in, same username", login.username)
    if login.household_id != row.household_id or _removed(db, login):
        _refused_known(db, login, row, "removed", data_dir)
    if role is None:
        _refused_known(db, login, row, "not_let_in", data_dir)
    if role == ADMIN:  # accepted again as an admin by the groups: the mark ends (not before the
        api_tokens.clear_refused(db, login)  # role is decided; fix13 review)
        if _kept.get(login.household_id, (0, ""))[0] == login.id:
            del _kept[login.household_id]  # and so does the warning
    if login.role != role:
        off = passwords_off(db, data_dir, row.household_id)
        sso_on = off or sso_can_start(db, data_dir, row.household_id)
        if login.role == ADMIN and not another_admin_gets_in(
            db, login, off, links=True, sso_on=sso_on
        ):
            log.warning(
                "Single sign-on: %s stays an admin, as the household's last one", login.username
            )
        else:
            log.info("Single sign-on: %s is now %s, from the groups", login.username, role)
            if login.role == ADMIN:  # only admins have API tokens (O2 review r1, finding 3)
                api_tokens.stop_for(db, login.id)
                # No link to an admin outlives an admin's being one (16b security pass
                # S-M1 d and S2-M1; proposed, for cabledrawer).
                drop_admin_links(db, login.household_id)
            login.role = role
            api_tokens.clear_refused(db, login)  # a Member makes no tokens: the mark ends
    seen(db, row, identity, role)
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
    """Mark a new session as single sign-on's, with its refresh token sealed; with none, it
    lasts a day at most (S8)."""
    session.sso = True
    if identity.refresh_token:
        session.sso_refresh_sealed = seal(data_dir, identity.refresh_token)
        session.sso_check_at = now() + sso.CHECK_EVERY
    else:
        # Nothing to check it with: a day at most, "Remember" or not (S8, cabledrawer 13 Nov).
        session.expires_at = min(session.expires_at, session.created_at + SSO_UNCHECKED_FOR)


def _due(at: datetime) -> ColumnElement[bool]:
    return and_(
        Session.sso.is_(True),
        Session.sso_refresh_sealed.is_not(None),
        Session.sso_check_at <= at,
        Session.expires_at > at,
    )


# The warning the hourly check leaves for a household's admins when the sign-in server no longer
# accepts the only admin who can get in, and their sign-in was kept (cabledrawer 12 Nov): the
# household's number to (login number, name). In memory only: the kept sign-in is asked again
# every few minutes, so a restart brings it back at the next check.
_kept: dict[int, tuple[int, str, bool]] = {}  # household: (login number, name, passwords off)


def forget_kept(household_id: int) -> None:
    """Drop the kept-sign-in warning of a household that was deleted."""
    _kept.pop(household_id, None)


def kept_warning(db: DbSession, data_dir: Path | None, household_id: int) -> str | None:
    """The sentence Settings shows an admin while it applies: the sign-in server no longer
    accepts the only admin who can get in, and Mealwright kept their sign-in. Gone once a
    refresh works again, when they have no sign-in left (they signed out), or when it no longer
    applies: passwords are back on and they have a password (words: cabledrawer 12 Nov; the ending
    for passwords already on is proposed, for cabledrawer)."""
    found = _kept.get(household_id)
    if found is None:
        return None
    login_id, name, was_off = found
    live = db.scalar(
        select(func.count())
        .select_from(Session)
        .where(Session.login_id == login_id, Session.expires_at > now())
    )
    if not live or (was_off and not passwords_off(db, data_dir, household_id)):
        _kept.pop(household_id, None)
        return None
    ending = "turn password sign-in back on" if passwords_off(db, data_dir, household_id) else ""
    sentence = (
        f"The sign-in server no longer accepts {name}. Mealwright kept them signed in "
        "because they're the only admin who can get in. Fix it at the sign-in server"
    )
    return f"{sentence}, or {ending}." if ending else f"{sentence}."


class _Asked(NamedTuple):
    client: Client
    token: str
    sealed: str  # the sealed refresh token the session held when it was asked
    issuer: str
    client_id: str


def _prepare(
    factory: sessionmaker[DbSession], data_dir: Path, session_id: int, at: datetime
) -> _Asked | None:
    """What to ask the sign-in server for one due sign-in, or None when there is nothing to ask.
    Its own short transaction, ended before the question goes out. It also gives back what the
    answer must still match when it comes (the sealed token read, the issuer and the client)."""
    with factory() as db:
        session = db.get(Session, session_id)
        if session is None or not db.scalar(
            select(Session.id).where(_due(at), Session.id == session_id)
        ):
            return None
        row = settings_row(db, session.household_id)
        if row is None or not usable(row):
            session.sso_check_at = None  # nothing to ask any more
            db.commit()
            return None
        owner = db.get(Login, session.login_id)
        if owner is None or owner.sso_issuer != row.issuer:
            # Signed in at another sign-in server than the saved one (the admin moved to
            # a new one): its token isn't this server's to be asked about (O1 review r3,
            # L5). Not asked, not ended, and so no API token is stopped by it.
            session.sso_refresh_sealed = None
            session.sso_check_at = at  # the day runs from the drop (auth.last_moment)
            db.commit()
            return None
        try:
            setup = client(row, data_dir)
            token = open_sealed(data_dir, str(session.sso_refresh_sealed))
        except SsoFailed, SecretUnreadable:
            session.sso_check_at = at + sso.RETRY_AFTER
            db.commit()
            return None
        return _Asked(setup, token, str(session.sso_refresh_sealed), row.issuer, row.client_id)


def _apply(
    factory: sessionmaker[DbSession],
    data_dir: Path,
    session_id: int,
    at: datetime,
    result: sso.Refreshed,
    new: str | None,
    asked: _Asked,
) -> bool:
    """Write what the sign-in server answered for one sign-in, and commit it. True when that
    sign-in ended. The answer is dropped when things changed while the server was being asked:
    the session holds another sealed token (or none), the issuer or client changed, or the
    setup is no longer usable (an answer for the old setup must not end sign-ins, stop API
    tokens or seal a token for it: whole-0.9 fix A review, finding 1)."""
    with factory() as db:
        session = db.get(Session, session_id)
        if session is None:
            return False  # signed out meanwhile
        row = settings_row(db, session.household_id)
        owner = db.get(Login, session.login_id)
        if row is None or owner is None or not usable(row):
            return False
        if (
            session.sso_refresh_sealed != asked.sealed
            or row.issuer != asked.issuer
            or row.client_id != asked.client_id
        ):
            return False
        keep = _hourly_keeps(db, owner, row, data_dir) if result == "ended" else None
        ended = False
        # The in-memory warning changes only once the save has worked: if Delete everything
        # removed the household meanwhile, the save fails and nothing about the old admin
        # stays under a household number the next setup reuses (release security pass, L2).
        warning: tuple[int, str, bool] | None = None
        drop_warning = False
        if keep is not None:
            # Nobody else can get in and they have no password that works (passwords are
            # off, or they have none): ending this sign-in would leave only reset-admin.
            # Its tokens stop, the sign-in stays, a warning is left (cabledrawer 12 Nov;
            # proposed, for cabledrawer), and it is asked again later.
            api_tokens.stop_for(db, session.login_id)
            api_tokens.mark_refused(db, owner)
            session.sso_check_at = at + sso.RETRY_AFTER
            warning = (owner.id, owner.name, keep)
            log.info(
                "Single sign-on: the only admin's sign-in kept (login %d); the sign-in "
                "server no longer accepts it; its API tokens stopped",
                owner.id,
            )
        elif result == "ended":
            # The tokens of an admin signed out there stop, even if they are signed in
            # somewhere else too (safest; proposed, for cabledrawer). The log says so, by the
            # login's number only, never a name (O2 review r2, finding 3).
            api_tokens.stop_for(db, session.login_id)
            db.delete(session)
            ended = True
            log.info(
                "Single sign-on: login %d signed out, as the sign-in server ended the "
                "sign-in; its API tokens stopped",
                session.login_id,
            )
        elif result == "ok":
            # A working refresh doesn't end the mark (groups aren't asked on a refresh), so
            # the warning stays with it (fix13 review; proposed, for cabledrawer).
            if owner.sso_refused_at is None and (
                _kept.get(session.household_id, (0, ""))[0] == owner.id
            ):
                drop_warning = True
            if new:
                session.sso_refresh_sealed = seal(data_dir, new)
            session.sso_check_at = at + sso.CHECK_EVERY
        else:
            session.sso_check_at = at + sso.RETRY_AFTER
        household_id = session.household_id
        db.commit()
        if warning is not None:
            _kept[household_id] = warning
        elif drop_warning:
            _kept.pop(household_id, None)
        return ended


def check_sessions(
    gate: OutboundGate,
    factory: sessionmaker[DbSession],
    data_dir: Path,
    events: Broadcaster,
) -> int:
    """The job: ask the provider about each single sign-on sign-in that's due. Gives how many
    were signed out; their open live-update streams end now (`events`: O2 review r4, finding 4)."""
    ended = 0
    ended_ids: list[int] = []
    at = now()
    with factory() as db:
        due_ids = list(db.scalars(select(Session.id).where(_due(at)).limit(200)))
    # One sign-in at a time, and no database transaction open while the sign-in server is asked
    # (a slow server must not make other saves wait; a stop half-way keeps what was learnt:
    # whole-0.9 review, S1 and S2).
    for session_id in due_ids:
        asked = _prepare(factory, data_dir, session_id, at)
        if asked is None:
            continue
        result, new = sso.refresh(gate, asked.client, asked.token)
        if _apply(factory, data_dir, session_id, at, result, new, asked):
            ended_ids.append(session_id)
            ended += 1
    for session_id in ended_ids:
        events.end_session(session_id)
    return ended
