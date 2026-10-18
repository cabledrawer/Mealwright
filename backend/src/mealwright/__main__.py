"""Run the server: python -m mealwright"""

from types import FrameType

import uvicorn

from mealwright.config import get_settings
from mealwright.events import Broadcaster
from mealwright.logs import set_up_logging
from mealwright.main import create_app

GRACEFUL_SECONDS = 5


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


def main() -> None:
    settings = get_settings()
    # Our own log lines (errors and sign-ins only; spec section 7): the container output
    # and a 14-day log file in the data folder (mealwright.logs).
    log_file = set_up_logging(settings.data_dir)
    app = create_app(settings, log_file)
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        # Forwarded headers are handled inside the app (ProxyHeadersMiddleware in
        # create_app), so they're tested; don't apply them twice.
        proxy_headers=False,
        # No request log: addresses would show what people look at and search for.
        access_log=False,
        # Logging is set up above; uvicorn's errors reach the same output and file.
        log_config=None,
        # Backstop: after this many seconds anything still open is cut off.
        timeout_graceful_shutdown=GRACEFUL_SECONDS,
    )
    StoppableServer(config, app.state.events).run()


if __name__ == "__main__":
    main()
