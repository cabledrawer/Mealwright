"""Run the server: python -m mealwright"""

import uvicorn

from mealwright.config import get_settings
from mealwright.logs import set_up_logging
from mealwright.main import create_app


def main() -> None:
    settings = get_settings()
    # Our own log lines (errors and sign-ins only; spec section 7): the container output
    # and a 14-day log file in the data folder (mealwright.logs).
    log_file = set_up_logging(settings.data_dir)
    uvicorn.run(
        create_app(settings, log_file),
        host=settings.host,
        port=settings.port,
        # Forwarded headers are handled inside the app (ProxyHeadersMiddleware in
        # create_app), so they're tested; don't apply them twice.
        proxy_headers=False,
        # No request log: addresses would show what people look at and search for.
        access_log=False,
        # Logging is set up above; uvicorn's errors reach the same output and file.
        log_config=None,
    )


if __name__ == "__main__":
    main()
