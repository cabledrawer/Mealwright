"""Single sign-on (0.9 O1): its setup (admins only), and signing in with it.

The sign-in goes start → the sign-in server → the callback → a session:

1. `GET /sso/start` (a link the browser follows) asks the sign-in server's discovery document
   through the outbound gate, seals the sign-in's state, nonce and PKCE verifier into a
   cookie for this browser (HttpOnly, 10 minutes; `mealwright.secret_box`), and sends the
   browser to the sign-in server. Nothing is kept on the server, so following the link
   changes nothing here, and strangers' starts can't push anyone's sign-in out (O1 review r1
   M2).
2. The sign-in server sends the browser back to the redirect address the admin saved: the web
   app's `/auth/callback` page. That page posts what came back to `POST /sso/finish`, which
   takes the state once, with the cookie of the browser that started it, swaps the code
   for tokens and checks the ID token (`mealwright.sso`). The account is found by issuer and
   subject, made on first sign-in if allowed, and its role follows the groups
   (`mealwright.sso_accounts`).
3. A session starts like a password sign-in's, with the refresh token sealed.

`POST /sso/test` starts the same for the setup screen's "Test sign-in", signed in as an admin.
It is a POST from this site only (a link or a form on another site starts nothing), and it
asks the sign-in server to ask who this is (`prompt=login`). The test links nothing: its
result is kept in memory for the setup screen, with who the sign-in server said it was. Only
when the groups make that identity an Admin can the admin link it to their own login, and
only by confirming it there: `POST /sso/link` ("Link tess to …?"; O1 review r1 H1).

The client secret is sealed (`mealwright.secret_box`) before it is stored, and no answer ever
holds it: the setup says only whether one is saved. Nothing here logs a token, a code, the
secret or an address.
"""

import logging
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from mealwright import sso, sso_accounts
from mealwright.api.v1.account import Me, _device, _me
from mealwright.api.v1.context import Here
from mealwright.auth import (
    Db,
    SameOrigin,
    client_address,
    find_session,
    needs_https,
    session_token,
    start_session,
)
from mealwright.config import Settings
from mealwright.errors import Problem
from mealwright.models import SsoSettings, utcnow
from mealwright.outbound import OutboundGate
from mealwright.own_network import is_localhost
from mealwright.roles import ADMIN, MEMBER, Action
from mealwright.secret_box import SecretUnreadable, open_sealed, seal

log = logging.getLogger("mealwright.sign_in")

router = APIRouter(tags=["single sign-on"], dependencies=[SameOrigin])

COOKIE = "__Host-mealwright_sso"
PLAIN_COOKIE = "mealwright_sso"
CALLBACK = "/auth/callback"
MOST_GROUPS = 50

# Proposed, for cabledrawer.
PASSWORDS_NEEDED = (
    "Password sign-in can only be turned off while an admin can sign in with single "
    "sign-on. Test sign-in first, and keep the Single sign-on switch on."
)
PASSWORDS_BACK_ON = (
    "Saved. Password sign-in is on again, because the single sign-on setup changed. "
    "Test sign-in, then turn it off again."
)
BAD_REDIRECT = (
    "The address to give your sign-in server must be this Mealwright’s own address, "
    "ending in /auth/callback. Open Mealwright at that address and save again."
)
BAD_ISSUER = "Enter the issuer address, starting with https://."
NO_SECRET = "Enter the client secret."  # noqa: S105 (words, not a secret)


@dataclass(frozen=True)
class WaitingLink:
    """A test's identity the admin who ran it may link to their login, once they confirm.
    Kept in memory only, for as long as a sign-in may take."""

    login_id: int
    issuer: str
    subject: str
    expires: float


def _cookie(settings: Settings) -> str:
    return PLAIN_COOKIE if settings.allow_plain_http else COOKIE


def _gate(request: Request) -> OutboundGate:
    gate: OutboundGate = request.app.state.outbound
    return gate


def _row(db: Db) -> SsoSettings | None:
    return sso_accounts.settings_row(db)


def _same_host(request: Request, redirect_uri: str) -> bool:
    """The saved redirect address is on the host this browser is using. The Host header is
    the browser's own, or a trusted proxy's X-Forwarded-Host (`mealwright.forwarded`); it is
    only compared, never used to build the address."""
    host = request.headers.get("host", "").lower()
    return bool(host) and urlsplit(redirect_uri).netloc.lower() == host


# --- What the sign-in page shows --------------------------------------------------------------


class SignInOptions(BaseModel):
    password: bool
    # The single sign-on button's name ("Authentik"), or None for no button.
    sso_button: str | None


@router.get("/sign-in-options")
def sign_in_options(request: Request, db: Db) -> SignInOptions:
    """Public: what the sign-in page offers. The button shows once single sign-on is set up
    and its Privacy switch is on."""
    row = _row(db)
    button = None
    if sso_accounts.usable(row) and row and sso_accounts.switch_on(db, row.household_id):
        button = row.button_name
    data_dir = request.app.state.settings.data_dir
    return SignInOptions(password=sso_accounts.password_sign_in_on(db, data_dir), sso_button=button)


# --- Signing in -----------------------------------------------------------------------------


def _go(to: str, code: str | None = None) -> RedirectResponse:
    where = f"{to}?sso={quote(code)}" if code else to
    return RedirectResponse(where, status_code=status.HTTP_303_SEE_OTHER)


def _begin(
    request: Request,
    db: Db,
    *,
    mode: sso.Mode,
    remember: bool = False,
    login_id: int | None = None,
    retried: bool = False,
) -> sso.Started:
    """Begin a sign-in or a test: where to send the browser. Raises SsoFailed."""
    row = _row(db)
    if row is None or not sso_accounts.usable(row):
        raise sso.SsoFailed("not_set_up")
    if not _same_host(request, row.redirect_uri):
        raise sso.SsoFailed("wrong_address")
    try:
        client = sso_accounts.client(row, request.app.state.settings.data_dir)
        return sso.start(
            _gate(request),
            client,
            mode=mode,
            remember=remember,
            login_id=login_id,
            retried=retried,
        )
    except sso.SsoFailed as failure:
        log.warning("Single sign-on couldn’t start: %s", failure.code)
        raise


def _bind(response: Response, settings: Settings, started: sso.Started) -> None:
    """Give the sign-in to this browser, sealed in a cookie of its own: only this server
    can read or make one, and only this browser can finish with it."""
    response.set_cookie(
        _cookie(settings),
        seal(settings.data_dir, started.flow.pack()),
        max_age=sso.FLOW_FOR,
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",  # sent when the sign-in server sends the browser back
        path="/",
    )


@router.get("/sso/start", response_class=RedirectResponse, status_code=303)
def start(request: Request, db: Db, remember: bool = False) -> RedirectResponse:
    """Public: begin signing in with single sign-on (a link, not a fetch). Answers with a
    redirect to the sign-in server, or to `/sign-in?sso=<code>` when it can't. A link is safe
    here: following it changes nothing for someone signed in."""
    try:
        started = _begin(request, db, mode="sign_in", remember=remember)
    except sso.SsoFailed as failure:
        return _go("/sign-in", failure.code)
    response = RedirectResponse(started.url, status_code=status.HTTP_303_SEE_OTHER)
    _bind(response, request.app.state.settings, started)
    return response


class TestStarted(BaseModel):
    # The sign-in server's page, for the setup screen to open in a new tab.
    url: str


@router.post("/sso/test")
def test(request: Request, response: Response, kitchen: Here) -> TestStarted:
    """Admins only: begin the setup screen's "Test sign-in". A POST, so only this site's own
    page can start one (the router refuses another site's). A refusal is a 400 with a `code`
    and a sentence to show."""
    kitchen.admin_only(Action.SIGN_IN)
    settings: Settings = request.app.state.settings
    needs_https(request, settings)
    try:
        started = _begin(request, kitchen.db, mode="test", login_id=kitchen.login.id)
    except sso.SsoFailed as failure:
        raise _refused(failure) from None
    _bind(response, settings, started)
    return TestStarted(url=started.url)


class FinishIn(BaseModel):
    state: str = Field(max_length=200)
    code: str | None = Field(default=None, max_length=4000)
    # What the sign-in server said instead of a code ("access_denied"): never shown as is.
    error: str | None = Field(default=None, max_length=200)


class TestResult(BaseModel):
    passed: bool
    # Who the sign-in server said it was: the user name Mealwright would use, and its own
    # name and email address for them, to show beside "Link … to …?".
    username: str | None = None
    name: str | None = None
    email: str | None = None
    groups: list[str] = []
    role: Literal["admin", "member"] | None = None
    # "can": the groups make them an Admin, and the admin who tested may link them to their
    # own login by confirming (POST /sso/link). "linked": they already are. Else "no".
    link: Literal["can", "linked", "no"] = "no"
    # Why it didn't pass, in plain words.
    message: str | None = None
    code: str | None = None


class FinishOut(BaseModel):
    # "again": the sign-in server refused this sign-in for asking to stay signed in while
    # away (offline_access); the callback page sends the browser to `url`, to try once
    # more without.
    done: Literal["signed_in", "tested", "again"]
    me: Me | None = None
    test: TestResult | None = None
    url: str | None = None


def _refused(failure: sso.SsoFailed) -> Problem:
    return Problem(status.HTTP_400_BAD_REQUEST, failure.code, failure.message)


def _tested(
    request: Request, household_id: int, result: TestResult, waiting: WaitingLink | None = None
) -> FinishOut:
    request.app.state.sso_tests[household_id] = result
    if waiting is None:
        request.app.state.sso_links.pop(household_id, None)
    else:
        request.app.state.sso_links[household_id] = waiting
    return FinishOut(done="tested", test=result)


def _waiting(request: Request, kitchen: Here) -> WaitingLink | None:
    """The link waiting for this admin's confirmation, if there is one still."""
    found: WaitingLink | None = request.app.state.sso_links.get(kitchen.household_id)
    if found is None or found.login_id != kitchen.login.id or found.expires <= time.monotonic():
        return None
    return found


def _fingerprint(row: SsoSettings) -> tuple[object, ...]:
    """The setup as an Admin would have to have proven it: who gets in, and the secret."""
    return (*_who_gets_in(row), row.client_secret_sealed)


def _proven(request: Request, row: SsoSettings) -> None:
    """An Admin passed Test sign-in, or signed in with single sign-on, under this setup."""
    request.app.state.sso_proven[row.household_id] = _fingerprint(row)


def _forget_test(request: Request, household_id: int) -> None:
    request.app.state.sso_tests.pop(household_id, None)
    request.app.state.sso_links.pop(household_id, None)


@router.post("/sso/finish")
def finish(body: FinishIn, request: Request, response: Response, db: Db) -> FinishOut:
    """Public: the callback page posts what the sign-in server sent back. Signs in (or, for a
    test, keeps the result for the setup screen) and answers what happened. A refusal is a
    400 with a `code` and a sentence to show."""
    settings: Settings = request.app.state.settings
    needs_https(request, settings)
    sealed = request.cookies.get(_cookie(settings))
    response.delete_cookie(
        _cookie(settings), httponly=True, secure=not settings.allow_plain_http, path="/"
    )
    try:
        try:
            packed = open_sealed(settings.data_dir, sealed) if sealed else None
        except SecretUnreadable:
            packed = None  # not a cookie this server sealed
        flow = sso.take(request.app.state.sso_used, packed, body.state)
    except sso.SsoFailed as failure:
        raise _refused(failure) from None
    try:
        if body.error and sso.may_retry(flow, body.error):
            return _again(request, response, db, flow)
        if body.error or not body.code:
            raise sso.SsoFailed("cancelled")
        row = sso_accounts.settings_row(db, flow.household_id)
        if row is None or not sso_accounts.usable(row):
            raise sso.SsoFailed("not_set_up")
        if row.redirect_uri != flow.redirect_uri:
            raise sso.SsoFailed("expired")  # the setup changed while this was under way
        client = sso_accounts.client(row, settings.data_dir)
        identity = sso.finish(_gate(request), flow, client, body.code)
        if flow.mode == "test":
            return _finish_test(request, db, row, flow.login_id, identity)
        login = sso_accounts.login_for(db, row, identity)
    except sso.SsoFailed as failure:
        db.rollback()
        if failure.code == "offline_refused":
            try:
                return _again(request, response, db, flow)
            except sso.SsoFailed as second:
                failure = second
        log.warning("Single sign-on refused (%s) from %s", failure.code, client_address(request))
        if flow.mode == "test":
            _tested(
                request,
                flow.household_id,
                TestResult(passed=False, message=failure.message, code=failure.code),
            )
        raise _refused(failure) from None
    session = start_session(
        db, response, settings, login, remember=flow.remember, device=_device(request)
    )
    sso_accounts.keep(db, settings.data_dir, session, identity)
    db.commit()
    if login.role == ADMIN:
        _proven(request, row)
    log.info("Signed in with single sign-on: %s from %s", login.username, client_address(request))
    return FinishOut(done="signed_in", me=_me(login))


def _again(request: Request, response: Response, db: Db, flow: sso.Flow) -> FinishOut:
    """The sign-in server refused the sign-in for offline_access: begin it once more without
    (the same kind, for the same browser), and say where to send the browser. That second
    sign-in keeps no refresh token (O1 review r1 L4). Raises SsoFailed."""
    started = _begin(
        request,
        db,
        mode=flow.mode,
        remember=flow.remember,
        login_id=flow.login_id,
        retried=True,
    )
    _bind(response, request.app.state.settings, started)
    log.info("Single sign-on: trying once more without offline_access")
    return FinishOut(done="again", url=started.url)


def _finish_test(
    request: Request,
    db: Db,
    row: SsoSettings,
    login_id: int | None,
    identity: sso.Identity,
) -> FinishOut:
    signed_in = find_session(db, session_token(request))
    if signed_in is None or signed_in.login.id != login_id or signed_in.login.role != ADMIN:
        raise sso.SsoFailed("expired")  # signed out, or someone else, since it started
    login = signed_in.login
    role, link = sso_accounts.outcome_of_test(db, row, login, identity)
    if role == ADMIN:
        _proven(request, row)
    result = TestResult(
        passed=role is not None,
        username=identity.username or sso_accounts.new_username(identity),
        name=identity.name,
        email=identity.email,
        groups=identity.groups[:MOST_GROUPS],
        role="admin" if role == ADMIN else "member" if role == MEMBER else None,
        link=link,
        message=None if role is not None else sso.MESSAGES["not_let_in"],
        code=None if role is not None else "not_let_in",
    )
    waiting = None
    if link == "can":
        waiting = WaitingLink(
            login_id=login.id,
            issuer=identity.issuer,
            subject=identity.subject,
            expires=time.monotonic() + sso.FLOW_FOR,
        )
    log.info("Single sign-on test by %s: %s", login.username, "passed" if role else "not let in")
    return _tested(request, row.household_id, result, waiting)


# --- The setup (admins only) ------------------------------------------------------------------


class GroupRole(BaseModel):
    group: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "member"]


class SsoSetupOut(BaseModel):
    issuer: str
    client_id: str
    # Whether a client secret is saved. The secret itself is never sent back.
    secret_set: bool
    button_name: str
    # The saved address to give the sign-in server; None before the first save.
    redirect_uri: str | None
    group_claim: str
    group_roles: list[GroupRole]
    anyone_else: Literal["none", "member"]
    make_accounts: bool
    password_sign_in: bool
    # Whether an admin can sign in with single sign-on (so passwords may be turned off).
    admin_linked: bool
    switch_on: bool
    test: TestResult | None
    # A save turned password sign-in back on (it was off, and the save changed something
    # that decides who gets in): `notice` says so, to show.
    passwords_back_on: bool = False
    notice: str | None = None


class SsoSetupIn(BaseModel):
    issuer: str = Field(max_length=500)
    client_id: str = Field(min_length=1, max_length=255)
    # Blank keeps the saved secret.
    client_secret: str = Field(default="", max_length=2000)
    button_name: str = Field(min_length=1, max_length=40)
    redirect_uri: str = Field(max_length=500)
    group_claim: str = Field(default="groups", min_length=1, max_length=100)
    group_roles: list[GroupRole] = Field(default=[], max_length=MOST_GROUPS)
    anyone_else: Literal["none", "member"] = "none"
    make_accounts: bool = True
    password_sign_in: bool = True


def _setup(request: Request, kitchen: Here, row: SsoSettings | None) -> SsoSetupOut:
    switch = sso_accounts.switch_on(kitchen.db, kitchen.household_id)
    test: TestResult | None = request.app.state.sso_tests.get(kitchen.household_id)
    if test is not None and test.link == "can" and _waiting(request, kitchen) is None:
        # Only the admin who tested can link, and only for a while.
        test = test.model_copy(update={"link": "no"})
    if row is None:
        return SsoSetupOut(
            issuer="",
            client_id="",
            secret_set=False,
            button_name="",
            redirect_uri=None,
            group_claim="groups",
            group_roles=[],
            anyone_else="none",
            make_accounts=True,
            password_sign_in=True,
            admin_linked=False,
            switch_on=switch,
            test=test,
        )
    return SsoSetupOut(
        issuer=row.issuer,
        client_id=row.client_id,
        secret_set=bool(row.client_secret_sealed),
        button_name=row.button_name,
        redirect_uri=row.redirect_uri,
        group_claim=row.group_claim,
        group_roles=[GroupRole.model_validate(g) for g in row.group_roles or []],
        anyone_else="member" if row.anyone_else == MEMBER else "none",
        make_accounts=row.make_accounts,
        password_sign_in=row.password_sign_in,
        admin_linked=sso_accounts.admin_signs_in_with_sso(kitchen.db, row),
        switch_on=switch,
        test=test,
    )


@router.get("/sso/settings")
def get_setup(request: Request, kitchen: Here) -> SsoSetupOut:
    """Admins only. The single sign-on setup, without the secret."""
    kitchen.admin_only(Action.SIGN_IN)
    return _setup(request, kitchen, sso_accounts.settings_row(kitchen.db, kitchen.household_id))


def _bad(code: str, sentence: str) -> Problem:
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, code, sentence)


def _check_redirect(request: Request, value: str) -> str:
    """This Mealwright's own callback address, as the admin's browser sees it."""
    value = value.strip()
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        raise _bad("bad_redirect", BAD_REDIRECT) from None
    settings: Settings = request.app.state.settings
    plain_ok = settings.allow_plain_http or is_localhost(host) or host in {"127.0.0.1", "[::1]"}
    if (
        (parts.scheme != "https" and not (parts.scheme == "http" and plain_ok))
        or parts.path != CALLBACK
        or parts.query
        or parts.fragment
        or parts.username is not None
        or not _same_host(request, value)
    ):
        raise _bad("bad_redirect", BAD_REDIRECT)
    return value


def _passwords_off_allowed(request: Request, kitchen: Here, row: SsoSettings) -> None:
    try:
        sso_accounts.client(row, request.app.state.settings.data_dir)  # the secret opens
    except sso.SsoFailed:
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED) from None
    if not (
        sso_accounts.switch_on(kitchen.db, kitchen.household_id)
        and sso_accounts.admin_signs_in_with_sso(kitchen.db, row)
    ):
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)
    if request.app.state.sso_proven.get(row.household_id) != _fingerprint(row):
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)


def _who_gets_in(row: SsoSettings) -> tuple[object, ...]:
    """Everything in the setup that decides whether an admin can still sign in with single
    sign-on, apart from the secret."""
    return (
        row.issuer,
        row.client_id,
        row.redirect_uri,
        row.group_claim,
        row.group_roles,
        row.anyone_else,
    )


@router.put("/sso/settings")
def put_setup(body: SsoSetupIn, request: Request, kitchen: Here) -> SsoSetupOut:
    """Admins only. Save the setup. The secret is sealed before it is stored; a blank one
    keeps the saved one. Turning password sign-in off is refused (409 `passwords_needed`)
    unless an admin can sign in with single sign-on and its switch is on, and never in the
    same save as a change to who gets in (the issuer, client ID, secret, callback address,
    groups claim, groups or "Anyone else"): that setup hasn't been tested. While password
    sign-in is off, such a change turns it back on and says so (`passwords_back_on`), so a
    mistake in the setup can't lock every admin out (O1 review r1 M3)."""
    kitchen.admin_only(Action.SIGN_IN)
    issuer = sso.tidy_issuer(body.issuer)
    if issuer is None:
        raise _bad("bad_issuer", BAD_ISSUER)
    redirect_uri = _check_redirect(request, body.redirect_uri)
    groups = [g.model_dump() for g in body.group_roles]
    if len({g["group"] for g in groups}) != len(groups):
        raise _bad("same_group", "Each group can be in the list once.")  # cabledrawer 12 Nov
    db = kitchen.db
    data_dir = request.app.state.settings.data_dir
    row = sso_accounts.settings_row(db, kitchen.household_id)
    before: tuple[object, ...] | None = None
    was_off = False
    if row is None:
        if not body.client_secret:
            raise _bad("no_secret", NO_SECRET)
        row = SsoSettings(household_id=kitchen.household_id)
        db.add(row)
    elif not body.client_secret and not row.client_secret_sealed:
        raise _bad("no_secret", NO_SECRET)
    else:
        before = _who_gets_in(row)
        was_off = not row.password_sign_in
    new_secret = bool(body.client_secret) and not sso_accounts.same_secret(
        row, data_dir, body.client_secret
    )
    after = (
        issuer,
        body.client_id.strip(),
        redirect_uri,
        body.group_claim.strip(),
        groups,
        body.anyone_else,
    )
    changed = before is not None and (new_secret or before != after)
    if changed and not was_off and not body.password_sign_in:
        # Turning passwords off together with a change nobody has tested yet.
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)
    row.issuer = issuer
    row.client_id = body.client_id.strip()
    if new_secret:
        row.client_secret_sealed = seal(data_dir, body.client_secret)
    row.button_name = body.button_name.strip()
    row.redirect_uri = redirect_uri
    row.group_claim = body.group_claim.strip()
    row.group_roles = groups
    row.anyone_else = body.anyone_else
    row.make_accounts = body.make_accounts
    row.updated_at = utcnow()
    db.flush()
    back_on = was_off and changed
    if back_on:
        row.password_sign_in = True
    elif not body.password_sign_in and row.password_sign_in:
        _passwords_off_allowed(request, kitchen, row)
        row.password_sign_in = False
    else:
        row.password_sign_in = body.password_sign_in
    db.commit()
    sso.cache.forget()
    _forget_test(request, kitchen.household_id)  # it was a test of the setup before
    log.info("Single sign-on: setup saved by %s", kitchen.login.username)
    saved = _setup(request, kitchen, row)
    if back_on:
        log.warning("Single sign-on: password sign-in is on again, as the setup changed")
        saved = saved.model_copy(update={"passwords_back_on": True, "notice": PASSWORDS_BACK_ON})
    return saved


class PasswordsIn(BaseModel):
    on: bool


@router.put("/sso/password-sign-in")
def put_passwords(body: PasswordsIn, request: Request, kitchen: Here) -> SsoSetupOut:
    """Admins only. Settings → Sign-in's "Password sign-in" switch on its own."""
    kitchen.admin_only(Action.SIGN_IN)
    row = sso_accounts.settings_row(kitchen.db, kitchen.household_id)
    if row is None:
        if body.on:
            return _setup(request, kitchen, None)
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)
    if not body.on and row.password_sign_in:
        _passwords_off_allowed(request, kitchen, row)
    if row.password_sign_in != body.on:
        row.password_sign_in = body.on
        kitchen.db.commit()
        log.info(
            "Single sign-on: password sign-in turned %s by %s",
            "on" if body.on else "off",
            kitchen.login.username,
        )
    return _setup(request, kitchen, row)


@router.post("/sso/link")
def link(request: Request, kitchen: Here) -> SsoSetupOut:
    """Admins only: "Link (you) to (them)?", confirmed. Links the admin's own login to the
    identity their last test found, when the groups made it an Admin. Refused (409
    `link_gone`) when no such test is waiting: it was someone else's, it ran out, or the
    setup was saved since."""
    kitchen.admin_only(Action.SIGN_IN)
    row = sso_accounts.settings_row(kitchen.db, kitchen.household_id)
    waiting = _waiting(request, kitchen)
    try:
        if row is None or waiting is None:
            raise sso.SsoFailed("link_gone")
        sso_accounts.link(kitchen.db, row, kitchen.login, waiting.issuer, waiting.subject)
    except sso.SsoFailed as failure:
        kitchen.db.rollback()
        raise Problem(status.HTTP_409_CONFLICT, failure.code, failure.message) from None
    kitchen.db.commit()
    request.app.state.sso_links.pop(kitchen.household_id, None)
    result: TestResult | None = request.app.state.sso_tests.get(kitchen.household_id)
    if result is not None:
        request.app.state.sso_tests[kitchen.household_id] = result.model_copy(
            update={"link": "linked"}
        )
    return _setup(request, kitchen, row)


@router.delete("/sso/link")
def not_now(request: Request, kitchen: Here) -> SsoSetupOut:
    """Admins only: "Not now". Drops the link that was waiting for this admin; nothing was
    linked."""
    kitchen.admin_only(Action.SIGN_IN)
    if _waiting(request, kitchen) is not None:
        request.app.state.sso_links.pop(kitchen.household_id, None)
    return _setup(request, kitchen, sso_accounts.settings_row(kitchen.db, kitchen.household_id))
