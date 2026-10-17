"""Run the server: python -m mealwright"""

import uvicorn

from mealwright.config import get_settings
from mealwright.main import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=True)


if __name__ == "__main__":
    main()
