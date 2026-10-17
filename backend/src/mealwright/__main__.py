"""Run the server: python -m mealwright"""

import uvicorn

from mealwright.main import create_app


def main() -> None:
    # All interfaces inside the container; it is only reachable through the reverse proxy.
    uvicorn.run(create_app(), host="0.0.0.0", port=8080, proxy_headers=True)  # noqa: S104  # nosec B104


if __name__ == "__main__":
    main()
