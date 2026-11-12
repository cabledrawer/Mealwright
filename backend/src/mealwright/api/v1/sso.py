"""Single sign-on (0.9 O1): its setup (admins only), and signing in with it.

The sign-in goes start → the sign-in server → the callback → a session:

1. `GET /sso/start` (a link the browser follows) asks the sign-in server's discovery document
   through the outbound gate, keeps the sign-in's state, nonce and PKCE verifier in memory
   for 10 minutes, ties them to this browser with a cookie of its own, and sends the browser
   to the sign-in server.
2. The sign-in server sends the browser back to the redirect address the admin saved: the web
   app's `/auth/callback` page. That page posts what came back to `POST /sso/finish`, which
   takes the state once, from the browser that started it, swaps the code for tokens and
   checks the ID token (`mealwright.sso`). The account is found by issuer and subject, made
   on first sign-in if allowed, and its role follows the groups (`mealwright.sso_accounts`).
3. A session starts like a password sign-in's, with the refresh token sealed.

`GET /sso/test` does the same for the setup screen's "Test sign-in", signed in as an admin:
it links that admin to the identity (so turning password sign-in off can't lock them out) and
keeps the result in memory for the setup screen.

The client secret is sealed (`mealwright.secret_box`) before it is stored, and no answer ever
holds it: the setup says only whether one is saved. Nothing here logs a token, a code, the
secret or an address.
"""

import logging
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
from mealwright.secret_box import seal

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
BAD_REDIRECT = (
    "The address to give your sign-in server must be this Mealwright’s own address, "
    "ending in /auth/callback. Open Mealwright at that address and save again."
)
BAD_ISSUER = "Enter the issuer address, starting with https://."
NO_SECRET = "Enter the client secret."  # noqa: S105 (words, not a secret)


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
def sign_in_options(db: Db) -> SignInOptions:
    """Public: what the sign-in page offers. The button shows once single sign-on is set up
    and its Privacy switch is on."""
    row = _row(db)
    button = None
    if sso_accounts.usable(row) and row and sso_accounts.switch_on(db, row.household_id):
        button = row.button_name
    return SignInOptions(password=sso_accounts.password_sign_in_on(db), sso_button=button)


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
) -> RedirectResponse:
    """Send the browser to the sign-in server, or back with `?sso=<code>` if that can't be."""
    back = "/sign-in" if mode == "sign_in" else "/settings/sso"
    row = _row(db)
    if row is None or not sso_accounts.usable(row):
        return _go(back, "not_set_up")
    if not _same_host(request, row.redirect_uri):
        return _go(back, "wrong_address")
    try:
        client = sso_accounts.client(row, request.app.state.settings.data_dir)
        started = sso.start(
            _gate(request),
            request.app.state.sso_flows,
            client,
            mode=mode,
            remember=remember,
            login_id=login_id,
        )
    except sso.SsoFailed as failure:
        log.warning("Single sign-on couldn’t start: %s", failure.code)
        return _go(back, failure.code)
    settings: Settings = request.app.state.settings
    response = RedirectResponse(started.url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        _cookie(settings),
        started.binding,
        max_age=sso.FLOW_FOR,
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",  # sent when the sign-in server sends the browser back
        path="/",
    )
    return response


@router.get("/sso/start", response_class=RedirectResponse, status_code=303)
def start(request: Request, db: Db, remember: bool = False) -> RedirectResponse:
    """Public: begin signing in with single sign-on (a link, not a fetch). Answers with a
    redirect to the sign-in server, or to `/sign-in?sso=<code>` when it can't."""
    return _begin(request, db, mode="sign_in", remember=remember)


@router.get("/sso/test", response_class=RedirectResponse, status_code=303)
def test(request: Request, kitchen: Here) -> RedirectResponse:
    """Admins only: the setup screen's "Test sign-in", in a new tab."""
    kitchen.admin_only(Action.SIGN_IN)
    return _begin(request, kitchen.db, mode="test", login_id=kitchen.login.id)


class FinishIn(BaseModel):
    state: str = Field(max_length=200)
    code: str | None = Field(default=None, max_length=4000)
    # What the sign-in server said instead of a code ("access_denied"): never shown as is.
    error: str | None = Field(default=None, max_length=200)


class TestResult(BaseModel):
    passed: bool
    username: str | None = None
    groups: list[str] = []
    role: Literal["admin", "member"] | None = None
    # Why it didn't pass, in plain words.
    message: str | None = None
    code: str | None = None


class FinishOut(BaseModel):
    done: Literal["signed_in", "tested"]
    me: Me | None = None
    test: TestResult | None = None


def _refused(failure: sso.SsoFailed) -> Problem:
    return Problem(status.HTTP_400_BAD_REQUEST, failure.code, failure.message)


def _tested(request: Request, household_id: int, result: TestResult) -> FinishOut:
    request.app.state.sso_tests[household_id] = result
    return FinishOut(done="tested", test=result)


@router.post("/sso/finish")
def finish(body: FinishIn, request: Request, response: Response, db: Db) -> FinishOut:
    """Public: the callback page posts what the sign-in server sent back. Signs in (or, for a
    test, links the admin) and answers what happened. A refusal is a 400 with a `code` and a
    sentence to show."""
    settings: Settings = request.app.state.settings
    needs_https(request, settings)
    binding = request.cookies.get(_cookie(settings))
    response.delete_cookie(
        _cookie(settings), httponly=True, secure=not settings.allow_plain_http, path="/"
    )
    try:
        flow = request.app.state.sso_flows.take(body.state, binding)
    except sso.SsoFailed as failure:
        raise _refused(failure) from None
    try:
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
    log.info("Signed in with single sign-on: %s from %s", login.username, client_address(request))
    return FinishOut(done="signed_in", me=_me(login))


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
    role = sso_accounts.link_for_test(db, row, login, identity)
    db.commit()
    result = TestResult(
        passed=role is not None,
        username=sso_accounts.new_username(identity),
        groups=identity.groups[:MOST_GROUPS],
        role="admin" if role == ADMIN else "member" if role == MEMBER else None,
        message=None if role is not None else sso.MESSAGES["not_let_in"],
        code=None if role is not None else "not_let_in",
    )
    log.info("Single sign-on test by %s: %s", login.username, "passed" if role else "not let in")
    return _tested(request, row.household_id, result)


# --- The setup (admins only) ------------------------------------------------------------------


class GroupRole(BaseModel):
    group: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "member"]


class SetupOut(BaseModel):
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


class SetupIn(BaseModel):
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


def _setup(request: Request, kitchen: Here, row: SsoSettings | None) -> SetupOut:
    switch = sso_accounts.switch_on(kitchen.db, kitchen.household_id)
    test = request.app.state.sso_tests.get(kitchen.household_id)
    if row is None:
        return SetupOut(
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
    return SetupOut(
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
def get_setup(request: Request, kitchen: Here) -> SetupOut:
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


def _passwords_off_allowed(kitchen: Here, row: SsoSettings) -> None:
    if not (
        sso_accounts.usable(row)
        and sso_accounts.switch_on(kitchen.db, kitchen.household_id)
        and sso_accounts.admin_signs_in_with_sso(kitchen.db, row)
    ):
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)


@router.put("/sso/settings")
def put_setup(body: SetupIn, request: Request, kitchen: Here) -> SetupOut:
    """Admins only. Save the setup. The secret is sealed before it is stored; a blank one
    keeps the saved one. Turning password sign-in off is refused (409 `passwords_needed`)
    unless an admin can sign in with single sign-on and its switch is on."""
    kitchen.admin_only(Action.SIGN_IN)
    issuer = sso.tidy_issuer(body.issuer)
    if issuer is None:
        raise _bad("bad_issuer", BAD_ISSUER)
    redirect_uri = _check_redirect(request, body.redirect_uri)
    groups = [g.model_dump() for g in body.group_roles]
    if len({g["group"] for g in groups}) != len(groups):
        raise _bad("same_group", "Each group can be in the list once.")  # proposed
    db = kitchen.db
    row = sso_accounts.settings_row(db, kitchen.household_id)
    if row is None:
        if not body.client_secret:
            raise _bad("no_secret", NO_SECRET)
        row = SsoSettings(household_id=kitchen.household_id)
        db.add(row)
    elif not body.client_secret and not row.client_secret_sealed:
        raise _bad("no_secret", NO_SECRET)
    row.issuer = issuer
    row.client_id = body.client_id.strip()
    if body.client_secret:
        row.client_secret_sealed = seal(request.app.state.settings.data_dir, body.client_secret)
    row.button_name = body.button_name.strip()
    row.redirect_uri = redirect_uri
    row.group_claim = body.group_claim.strip()
    row.group_roles = groups
    row.anyone_else = body.anyone_else
    row.make_accounts = body.make_accounts
    row.updated_at = utcnow()
    db.flush()
    if not body.password_sign_in and row.password_sign_in:
        _passwords_off_allowed(kitchen, row)
    row.password_sign_in = body.password_sign_in
    db.commit()
    sso.cache.forget()
    log.info("Single sign-on: setup saved by %s", kitchen.login.username)
    return _setup(request, kitchen, row)


class PasswordsIn(BaseModel):
    on: bool


@router.put("/sso/password-sign-in")
def put_passwords(body: PasswordsIn, request: Request, kitchen: Here) -> SetupOut:
    """Admins only. Settings → Sign-in's "Password sign-in" switch on its own."""
    kitchen.admin_only(Action.SIGN_IN)
    row = sso_accounts.settings_row(kitchen.db, kitchen.household_id)
    if row is None:
        if body.on:
            return _setup(request, kitchen, None)
        raise Problem(status.HTTP_409_CONFLICT, "passwords_needed", PASSWORDS_NEEDED)
    if not body.on and row.password_sign_in:
        _passwords_off_allowed(kitchen, row)
    if row.password_sign_in != body.on:
        row.password_sign_in = body.on
        kitchen.db.commit()
        log.info(
            "Single sign-on: password sign-in turned %s by %s",
            "on" if body.on else "off",
            kitchen.login.username,
        )
    return _setup(request, kitchen, row)
