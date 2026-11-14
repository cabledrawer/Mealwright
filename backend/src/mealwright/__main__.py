"""Run the server: python -m mealwright

Or give the only admin a new password: python -m mealwright reset-admin <username> (PR A2).
"""

import argparse
import logging
import os
from types import FrameType

import uvicorn

from mealwright.config import get_settings
from mealwright.events import Broadcaster
from mealwright.logs import set_up_logging
from mealwright.main import UnsupportedSetup, create_app
from mealwright.reset_admin import reset_admin

GRACEFUL_SECONDS = 5

# How long an idle connection stays open for its next request. uvicorn's default is 5 s.
# A reverse proxy keeps its own idle connections to us open for longer (Caddy 2 min, Traefik
# 90 s, nginx 60 s) and reuses them. If we close one first, a request the proxy sends on it
# at that moment fails ("socket hang up" / "connection reset"). A proxy must never reuse a
# connection we have already closed, so we wait a little longer than the longest of those
# defaults.
KEEP_ALIVE_SECONDS = 130


class StoppableServer(uvicorn.Server):
    """uvicorn waits for open connections before it runs the app's shutdown, and a live
    stream never ends by itself. So when the server is asked to stop, end the streams
    first (sync protocol section 10)."""

    def __init__(self, config: uvicorn.Config, events: Broadcaster) -> None:
        super().__init__(config)
        self._events = events

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self._events.close()
        super().handle_exit(sig, frame)


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m mealwright", description="Run Mealwright.")
    commands = parser.add_subparsers(dest="command")
    reset = commands.add_parser(
        "reset-admin",
        help="give an admin a new random password and sign them out everywhere",
    )
    reset.add_argument("username", help="the admin's username")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    command = parse(argv)
    # Every file and folder made from here on (the database and its -wal and -shm, backups,
    # photos, logs) is for the Mealwright user alone: files 0600, folders 0700.
    os.umask(0o077)
    settings = get_settings()
    if command.command == "reset-admin":
        if settings.data_dir.is_dir():
            set_up_logging(settings.data_dir)  # the reset goes in the log file (no password)
        raise SystemExit(reset_admin(settings, command.username))
    # Our own log lines (errors and sign-ins only; spec section 7): the container output
    # and a 14-day log file in the data folder (mealwright.logs).
    log_file = set_up_logging(settings.data_dir)
    try:
        app = create_app(settings, log_file)
    except UnsupportedSetup as refused:
        # One clear line in the container log, not a traceback.
        logging.getLogger("mealwright").error("Not starting: %s", refused)
        raise SystemExit(1) from None
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        # Forwarded headers are handled inside the app (ProxyHeadersMiddleware in
        # create_app), so they're tested; don't apply them twice.
        proxy_headers=False,
        # No `Server: uvicorn` header on any answer: it tells nothing a person needs (0.9.5).
        server_header=False,
        # No request log: addresses would show what people look at and search for.
        access_log=False,
        # Logging is set up above; uvicorn's errors reach the same output and file.
        log_config=None,
        # Backstop: after this many seconds anything still open is cut off.
        timeout_graceful_shutdown=GRACEFUL_SECONDS,
        # Idle connections outlive a reverse proxy's (see KEEP_ALIVE_SECONDS).
        timeout_keep_alive=KEEP_ALIVE_SECONDS,
    )
    StoppableServer(config, app.state.events).run()


if __name__ == "__main__":
    main()
