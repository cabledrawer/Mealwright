"""`python -m mealwright reset-admin <username>`: a way back in for the only admin (PR A2).

Run inside the container (`docker exec -it mealwright python -m mealwright reset-admin tess`).
It sets a new random password on that admin's login, prints it once, and signs that login out
on every device. For `auth.NEW_PASSWORD_WINDOW` after, the username's pause doesn't stop that
admin's new password (it goes by the password's date). Only someone who can run commands in the
container can use it, which is the same person who can read the database. The password is never
logged or stored as typed. If password sign-in was turned off for single sign-on (0.9 O1), it's
turned back on, so this always works (proposed, for cabledrawer).
"""

import logging
import secrets
import sys
from typing import TextIO

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from mealwright.auth import hash_password, now
from mealwright.config import Settings
from mealwright.db import make_engine, make_sessionmaker
from mealwright.models import JoinLink, Login, Member, Session, SsoSettings, utcnow

# Mealwright's own log file (mealwright.logs): who was reset, never the password.
log = logging.getLogger("mealwright.sign_in")


def new_password() -> str:
    """16 characters from 12 random bytes (96 bits): over the 12-character minimum."""
    return secrets.token_urlsafe(12)


def _admins(db: DbSession) -> list[str]:
    """The admins who can sign in: not removed, with a password, or with a sign-in link not
    used yet (marked so; cabledrawer 12 Nov)."""
    live_link = (
        select(JoinLink.id)
        .where(
            JoinLink.login_id == Login.id,
            JoinLink.used_at.is_(None),
            JoinLink.expires_at > utcnow(),
        )
        .exists()
    )
    rows = db.execute(
        select(Login.username, Login.password_hash, live_link)
        .outerjoin(Member, Member.id == Login.member_id)
        .where(Login.role == "admin", Member.removed_at.is_(None))
        .order_by(Login.username)
    ).all()
    return [
        username if password_hash else f"{username} (sign-in link not used yet)"
        for username, password_hash, pending in rows
        if password_hash or pending
    ]


def reset_admin(settings: Settings, username: str, out: TextIO = sys.stdout) -> int:
    """Give back the exit status: 0 done, 1 refused (with the reason on stderr)."""
    if settings.database_url is None and not (settings.data_dir / "mealwright.db").exists():
        print(f"There's no Mealwright database in {settings.data_dir}.", file=sys.stderr)
        return 1
    engine = make_engine(settings.sqlalchemy_url)
    try:
        with make_sessionmaker(engine)() as db:
            name = username.strip().lower()
            login = db.scalars(select(Login).where(Login.username == name)).one_or_none()
            member = db.get(Member, login.member_id) if login and login.member_id else None
            if login is None or login.role != "admin" or (member and member.removed_at):
                if login is None:
                    why = f"The login {name!r} doesn't exist"
                elif member and member.removed_at:  # cabledrawer 12 Nov
                    why = (
                        f"The login {name!r} can't be reset: "
                        f"{member.name} has been removed from the household"
                    )
                else:
                    why = f"The login {name!r} isn't an admin"
                print(f"{why}. Admins: {', '.join(_admins(db)) or 'none'}.", file=sys.stderr)
                return 1
            password = new_password()
            login.password_hash = hash_password(password)
            login.password_changed_at = now()
            mine = Session.login_id == login.id
            ended = db.scalar(select(func.count()).select_from(Session).where(mine)) or 0
            db.execute(delete(Session).where(mine))
            # A way back in even with password sign-in turned off for single sign-on (0.9 O1;
            # proposed, for cabledrawer): it's turned back on for the household.
            sso = db.get(SsoSettings, login.household_id)
            turned_on = sso is not None and not sso.password_sign_in
            if sso is not None:
                sso.password_sign_in = True
            db.commit()
    finally:
        engine.dispose()
    log.warning(
        "reset-admin: new password set for %s; signed out on %d device(s)", login.username, ended
    )
    if turned_on:
        log.warning("reset-admin: password sign-in turned back on")
    print(f"New password for {login.username}: {password}", file=out)
    print(
        "It's shown only this once. Sign in with it, then change it in Settings, Sign-in. "
        f"{login.username} is now signed out everywhere.",
        file=out,
    )
    if turned_on:
        print("Password sign-in was off for single sign-on: it's on again.", file=out)
    return 0
