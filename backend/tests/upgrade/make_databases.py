"""Make the saved old databases in `databases/` (a dev script: not shipped, and the tests never
run it). They stand for real old installs, so they are NOT re-made casually: see README.md.

    python make_databases.py <work folder> [tag ...]

For each release tag it takes that tag's own code (`git archive`) into <work folder>/<tag>,
installs that tag's own locked libraries from the uv cache with NO network (UV_OFFLINE=1; if a
tag can't be installed that way, the script stops), and runs `fill_one.py` with that
environment. Keep the work folder path short (for example /var/tmp/up).
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAGS = [
    "v0.1.0",
    "v0.1.1",
    "v0.2.0",
    "v0.2.1",
    "v0.3.0",
    "v0.4.0",
    "v0.5.0",
    "v0.5.1",
    "v0.6.0",
    "v0.7.0",
    "v0.8.0",
    "v0.9.0-beta.1",
]


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def main(work: Path, tags: list[str]) -> None:
    repo = Path(
        subprocess.run(  # noqa: S603
            ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    for tag in tags:
        folder = work / tag
        folder.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "archive", tag, "backend"],  # noqa: S607
            check=True,
            capture_output=True,
        ).stdout
        subprocess.run(["tar", "-x", "-C", str(folder)], input=archive, check=True)  # noqa: S603, S607
        env = {
            **os.environ,
            "UV_OFFLINE": "1",
            "UV_PROJECT_ENVIRONMENT": str(folder / "venv"),
            "MEALWRIGHT_FRONTEND_DIR": str(folder / "no-frontend"),
        }
        backend = folder / "backend"
        run(["uv", "sync", "--frozen"], backend, env)
        target = HERE / "databases" / f"{tag}.sqlite"
        run(
            [
                str(folder / "venv" / "bin" / "python"),
                "-W",
                "ignore",
                str(HERE / "fill_one.py"),
                str(target),
                tag,
            ],
            backend,
            env,
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:] or TAGS)
