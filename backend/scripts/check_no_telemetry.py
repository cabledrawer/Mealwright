"""Fail if an OpenTelemetry SDK or exporter is installed.

FastAPI needs `opentelemetry-api`, which does nothing on its own. An SDK or exporter
package would be able to send data, so none may be installed. Runs in the test suite
and against the built Docker image (stdlib only, so it needs nothing from the app):

    docker run --rm -v ./backend/scripts:/scripts:ro --entrypoint python \\
        <image> -I /scripts/check_no_telemetry.py
"""

import sys
from importlib.metadata import distributions

ALLOWED = {"opentelemetry-api"}


def forbidden_packages() -> list[str]:
    names = {(dist.metadata["Name"] or "").lower().replace("_", "-") for dist in distributions()}
    return sorted(
        name for name in names if name.startswith("opentelemetry") and name not in ALLOWED
    )


def main() -> int:
    found = forbidden_packages()
    if found:
        print("Telemetry packages installed (not allowed): " + ", ".join(found), file=sys.stderr)
        return 1
    print("OK: no OpenTelemetry SDK or exporter installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
