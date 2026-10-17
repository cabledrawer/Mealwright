"""Run the server: python -m mealwright"""

import logging

import uvicorn

from mealwright.config import get_settings
from mealwright.main import create_app


def main() -> None:
    # Our own log lines (errors and sign-ins only; spec section 7) go to the container log.
    logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s")
    logging.getLogger("mealwright").setLevel(logging.INFO)
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
        # No request log: addresses would show what people look at and search for.
        access_log=False,
    )


if __name__ == "__main__":
    main()
