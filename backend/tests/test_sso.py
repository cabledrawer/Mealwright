"""Single sign-on's protocol part (0.9 O1), against a fake identity provider on a fake network.

Nothing here goes online: name look-ups and connections are faked (tests/fake_idp.py)."""

import base64
import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from fake_idp import (
    ADDRESS,
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    KEY,
    OTHER_KEY,
    FakeProvider,
    FakeTLS,
    sign,
    unsigned,
)
from sqlalchemy.orm import Session, sessionmaker

from mealwright import migrate, sso
from mealwright.db import make_engine, make_sessionmaker
from mealwright.models import Household, OwnNetworkEntry
from mealwright.outbound import USER_AGENT, Connection, OutboundGate, set_switch
from mealwright.sso import Client, Flows, SsoFailed

REDIRECT = "https://mealwright.example.com/auth/callback"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "test.db"
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine)
    factory = make_sessionmaker(engine)
    with factory() as session:
        session.add(Household(id=1, name="Home"))
        session.commit()
        set_switch(session, 1, Connection.SINGLE_SIGN_ON, True)
        session.commit()
    engine.dispose()
    return path


@pytest.fixture
def sessions(template: Path, tmp_path: Path) -> sessionmaker[Session]:
    path = tmp_path / "test.db"
    shutil.copyfile(template, path)
    return make_sessionmaker(make_engine(f"sqlite:///{path}"))


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


@pytest.fixture
def idp(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    provider.install(monkeypatch)
    return provider


@pytest.fixture
def gate(sessions: sessionmaker[Session]) -> OutboundGate:
    return OutboundGate(sessions, tls=cast(Any, FakeTLS()))


def client(issuer: str = ISSUER, secret: str = CLIENT_SECRET) -> Client:
    return Client(
        household_id=1,
        issuer=issuer,
        client_id=CLIENT_ID,
        client_secret=secret,
        redirect_uri=REDIRECT,
    )


def switch(sessions: sessionmaker[Session], on: bool) -> None:
    with sessions() as session:
        set_switch(session, 1, Connection.SINGLE_SIGN_ON, on)
        session.commit()


def sign_in(
    gate: OutboundGate, idp: FakeProvider, **kwargs: Any
) -> tuple[sso.Identity, sso.Started]:
    flows = Flows()
    started = sso.start(gate, flows, client(), mode="sign_in")
    code, state = idp.sign_in(started.url, **kwargs)
    flow = flows.take(state, started.binding)
    return sso.finish(gate, flow, client(), code), started


# --- A good sign-in ----------------------------------------------------------------------------


def test_a_sign_in_goes_through_the_gate_and_gives_the_checked_identity(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    identity, started = sign_in(gate, idp)
    assert identity.issuer == ISSUER
    assert identity.subject == "user-1"
    assert identity.username == "ayla"
    assert identity.groups == ["mealwright-users"]
    assert identity.refresh_token == "rt-1"
    # The browser is sent to the provider with PKCE (S256), a state and a nonce.
    query = parse_qs(urlsplit(started.url).query)
    assert started.url.startswith(f"{ISSUER}/authorize?")
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [REDIRECT]
    assert len(query["state"][0]) >= 40 and len(query["nonce"][0]) >= 40
    # Every request went to the provider's one checked address, as Mealwright.
    assert {c for c in idp.connections} == {(ADDRESS, 443)}
    assert [(s.method, urlsplit(s.path).path) for s in idp.seen] == [
        ("GET", "/.well-known/openid-configuration"),
        ("POST", "/token"),
        ("GET", "/jwks"),
    ]
    assert all(s.headers["user-agent"] == USER_AGENT for s in idp.seen)
    token = idp.seen[1]
    assert token.headers["content-type"] == "application/x-www-form-urlencoded"
    assert token.headers["authorization"].startswith("Basic ")
    form = parse_qs(token.body.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["redirect_uri"] == [REDIRECT]
    assert "client_secret" not in form  # sent in the Authorization header only


def test_the_secret_goes_in_the_form_when_the_provider_takes_only_that(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    idp.secret_post_only = True
    identity, _ = sign_in(gate, idp)
    assert identity.subject == "user-1"
    assert "authorization" not in idp.seen[1].headers


def test_groups_come_from_userinfo_when_the_id_token_has_none(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    idp.userinfo = {"sub": "user-1", "groups": ["mealwright-admins"]}
    identity, _ = sign_in(gate, idp, extra={"groups": None})
    assert identity.groups == []  # a null claim is there, so userinfo isn't asked
    idp.seen.clear()

    def without_groups(claims: dict[str, Any]) -> str:
        return sign({k: v for k, v in claims.items() if k != "groups"})

    identity, _ = sign_in(gate, idp, id_token=without_groups)
    assert identity.groups == ["mealwright-admins"]
    userinfo = [s for s in idp.seen if s.path.endswith("/userinfo")]
    assert userinfo[0].headers["authorization"] == "Bearer at-1"


def test_userinfo_for_another_subject_is_ignored(gate: OutboundGate, idp: FakeProvider) -> None:
    idp.userinfo = {"sub": "someone-else", "groups": ["mealwright-admins"]}

    def without_groups(claims: dict[str, Any]) -> str:
        return sign({k: v for k, v in claims.items() if k != "groups"})

    identity, _ = sign_in(gate, idp, id_token=without_groups)
    assert identity.groups == []


# --- Tokens that are refused ------------------------------------------------------------------


def _refused(gate: OutboundGate, idp: FakeProvider, **kwargs: Any) -> None:
    with pytest.raises(SsoFailed) as caught:
        sign_in(gate, idp, **kwargs)
    assert caught.value.code == "refused"


def test_a_token_from_another_issuer_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    _refused(gate, idp, extra={"iss": "https://evil.example"})


def test_a_token_for_another_client_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    _refused(gate, idp, extra={"aud": "another-app"})


def test_a_token_with_another_nonce_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    _refused(gate, idp, extra={"nonce": "not-the-one-sent"})


def test_a_token_without_a_nonce_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    def no_nonce(claims: dict[str, Any]) -> str:
        return sign({k: v for k, v in claims.items() if k != "nonce"})

    _refused(gate, idp, id_token=no_nonce)


def test_an_expired_token_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    long_ago = int(time.time()) - 3600
    _refused(gate, idp, extra={"exp": long_ago, "iat": long_ago - 300})


def test_an_unsigned_token_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    _refused(gate, idp, id_token=unsigned)


def test_a_token_signed_with_hs256_using_the_public_key_is_refused(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    # The classic confusion: the provider's public key used as an HMAC secret.
    public_pem = KEY.as_pem(is_private=False)

    def hs256(claims: dict[str, Any]) -> str:
        # Made by hand: Authlib itself won't use a PEM key as an HMAC secret.
        def part(value: dict[str, Any]) -> str:
            raw = json.dumps(value).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        signed = f"{part({'alg': 'HS256', 'kid': 'k1'})}.{part(claims)}"
        mac = hmac.new(public_pem, signed.encode(), hashlib.sha256).digest()
        return f"{signed}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"

    _refused(gate, idp, id_token=hs256)


def test_a_token_signed_with_another_key_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    _refused(gate, idp, id_token=lambda claims: sign(claims, key=OTHER_KEY))


def test_a_changed_token_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    def changed(claims: dict[str, Any]) -> str:
        head, _body, signature = sign(claims).split(".")
        other = sign({**claims, "sub": "admin"}).split(".")[1]
        return ".".join([head, other, signature])

    _refused(gate, idp, id_token=changed)


def test_new_keys_at_the_provider_are_fetched_once_more(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    sign_in(gate, idp)  # keys now cached
    idp.jwks = {"keys": [OTHER_KEY.as_dict(is_private=False)]}
    identity, _ = sign_in(gate, idp, id_token=lambda claims: sign(claims, key=OTHER_KEY))
    assert identity.subject == "user-1"


def test_a_discovery_document_for_another_issuer_is_refused(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    idp.discovery_extra = {"issuer": "https://evil.example"}
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client(), mode="sign_in")
    assert caught.value.code == "bad_answer"


def test_a_wrong_client_secret_is_refused(gate: OutboundGate, idp: FakeProvider) -> None:
    flows = Flows()
    started = sso.start(gate, flows, client(secret="wrong"), mode="sign_in")
    code, state = idp.sign_in(started.url)
    with pytest.raises(SsoFailed) as caught:
        sso.finish(gate, flows.take(state, started.binding), client(secret="wrong"), code)
    assert caught.value.code == "refused"


# --- One-time, short-lived and bound to the browser ---------------------------------------------


def test_a_state_is_used_once_and_only_by_the_browser_that_started_it(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    flows = Flows()
    started = sso.start(gate, flows, client(), mode="sign_in")
    _, state = idp.sign_in(started.url)
    with pytest.raises(SsoFailed) as caught:
        flows.take(state, "another browser")
    assert caught.value.code == "expired"
    # A wrong browser used it up too: nobody can try again with it.
    with pytest.raises(SsoFailed):
        flows.take(state, started.binding)
    started = sso.start(gate, flows, client(), mode="sign_in")
    _, state = idp.sign_in(started.url)
    flows.take(state, started.binding)
    with pytest.raises(SsoFailed):
        flows.take(state, started.binding)
    with pytest.raises(SsoFailed):
        flows.take(state, None)


def test_a_state_runs_out(
    gate: OutboundGate, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    flows = Flows()
    started = sso.start(gate, flows, client(), mode="sign_in")
    _, state = idp.sign_in(started.url)
    later = time.monotonic() + sso.FLOW_FOR + 1
    monkeypatch.setattr(time, "monotonic", lambda: later)
    with pytest.raises(SsoFailed):
        flows.take(state, started.binding)


def test_only_so_many_sign_ins_wait_at_once(gate: OutboundGate, idp: FakeProvider) -> None:
    flows = Flows()
    first = sso.start(gate, flows, client(), mode="sign_in")
    for _ in range(sso.MOST_FLOWS):
        sso.start(gate, flows, client(), mode="sign_in")
    assert len(flows) == sso.MOST_FLOWS
    _, state = idp.sign_in(first.url)
    with pytest.raises(SsoFailed):
        flows.take(state, first.binding)


def test_a_code_from_another_sign_in_fails_its_pkce(gate: OutboundGate, idp: FakeProvider) -> None:
    flows = Flows()
    one = sso.start(gate, flows, client(), mode="sign_in")
    two = sso.start(gate, flows, client(), mode="sign_in")
    code_one, _ = idp.sign_in(one.url)
    _, state_two = idp.sign_in(two.url)
    with pytest.raises(SsoFailed):
        sso.finish(gate, flows.take(state_two, two.binding), client(), code_one)


# --- The Privacy switch and "Your own network" --------------------------------------------------


def test_nothing_leaves_while_the_switch_is_off(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    switch(sessions, False)
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client(), mode="sign_in")
    assert caught.value.code == "switched_off"
    assert idp.lookups == [] and idp.connections == [] and idp.seen == []


def test_turning_the_switch_off_mid_sign_in_stops_the_rest(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    flows = Flows()
    started = sso.start(gate, flows, client(), mode="sign_in")
    code, state = idp.sign_in(started.url)
    switch(sessions, False)
    sent = len(idp.seen)
    with pytest.raises(SsoFailed) as caught:
        sso.finish(gate, flows.take(state, started.binding), client(), code)
    assert caught.value.code == "switched_off"
    assert len(idp.seen) == sent


def test_a_refresh_sends_nothing_while_the_switch_is_off(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    switch(sessions, False)
    assert sso.refresh(gate, client(), "rt-1") == ("later", None)
    assert idp.seen == [] and idp.lookups == []


def test_a_provider_on_the_own_network_must_be_listed(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    idp.address = "192.168.1.20"
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client(), mode="sign_in")
    assert caught.value.code == "own_network"
    assert idp.connections == []
    with sessions() as session:
        session.add(OwnNetworkEntry(household_id=1, kind="name", value="id.example.org"))
        session.commit()
    sso.start(gate, Flows(), client(), mode="sign_in")
    assert idp.connections == [("192.168.1.20", 443)]


def test_plain_http_and_other_ports_work_only_for_a_listed_place(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    idp.issuer = "http://id.example.org"
    idp.port = 80
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client("http://id.example.org"), mode="sign_in")
    assert caught.value.code == "not_https"
    idp.issuer, idp.port = "https://id.example.org:8443", 8443
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client("https://id.example.org:8443"), mode="sign_in")
    assert caught.value.code == "own_network"
    assert idp.connections == []
    with sessions() as session:
        session.add(OwnNetworkEntry(household_id=1, kind="address", value=ADDRESS))
        session.commit()
    sso.start(gate, Flows(), client("https://id.example.org:8443"), mode="sign_in")
    assert idp.connections == [(ADDRESS, 8443)]


def test_this_server_itself_is_never_used(
    gate: OutboundGate, idp: FakeProvider, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        session.add(OwnNetworkEntry(household_id=1, kind="range", value="127.0.0.0/8"))
        session.commit()
    for issuer in ("https://localhost", "https://127.0.0.1"):
        with pytest.raises(SsoFailed) as caught:
            sso.start(gate, Flows(), client(issuer), mode="sign_in")
        assert caught.value.code == "always_blocked"
    idp.address = "127.0.0.1"
    with pytest.raises(SsoFailed) as caught:
        sso.start(gate, Flows(), client(), mode="sign_in")
    assert caught.value.code == "always_blocked"
    assert idp.connections == []


# --- Refresh --------------------------------------------------------------------------------


def test_refresh_keeps_a_sign_in_alive_until_the_provider_ends_it(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    identity, _ = sign_in(gate, idp)
    assert identity.refresh_token is not None
    assert sso.refresh(gate, client(), identity.refresh_token) == ("ok", None)
    form = parse_qs(idp.seen[-1].body.decode())
    assert form["grant_type"] == ["refresh_token"]
    idp.refresh_tokens.clear()  # ended at the provider
    assert sso.refresh(gate, client(), identity.refresh_token) == ("ended", None)


def test_refresh_tries_later_when_the_provider_cant_be_reached(
    gate: OutboundGate, idp: FakeProvider
) -> None:
    idp.token_override = lambda _form: (503, {"error": "busy"})
    assert sso.refresh(gate, client(), "rt-1") == ("later", None)
    idp.port = 9999  # nothing listens
    sso.cache.forget()
    assert sso.refresh(gate, client(), "rt-1") == ("later", None)


# --- Small pieces -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tidy"),
    [
        ("https://id.example.org/", "https://id.example.org"),
        (
            " https://id.example.org/application/o/mealwright/ ",
            "https://id.example.org/application/o/mealwright",
        ),
        ("http://192.168.1.20:5556/dex", "http://192.168.1.20:5556/dex"),
        ("ftp://id.example.org", None),
        ("https://user:pw@id.example.org", None),
        ("https://id.example.org/?x=1", None),
        ("https://id.example.org/#x", None),
        ("https://id.example.org:99999", None),
        ("id.example.org", None),
        ("", None),
    ],
)
def test_tidy_issuer(text: str, tidy: str | None) -> None:
    assert sso.tidy_issuer(text) == tidy


def test_groups_in() -> None:
    assert sso.groups_in({"groups": ["a", "b"]}, "groups") == ["a", "b"]
    assert sso.groups_in({"roles": "a"}, "roles") == ["a"]
    assert sso.groups_in({"groups": [1, None, "", "a"]}, "groups") == ["a"]
    assert sso.groups_in({"groups": {"a": 1}}, "groups") == []
    assert sso.groups_in({}, "groups") == []
