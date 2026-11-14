"""Write (or check) THIRD-PARTY-NOTICES.md: the open-source libraries and fonts the image ships,
each with its version, its licence and its licence text (0.9.5; the licence texts are what the
licences ask to be kept with a copy).

    uv run --frozen python -I scripts/third_party_notices.py           # write the file
    uv run --frozen python -I scripts/third_party_notices.py --check   # fail if it is out of date

What is listed:

- The server's Python libraries: everything uv.lock reaches from the project's own
  dependencies (no development tools). Versions come from uv.lock; the licence and its text
  from the installed package's own metadata and licence files.
- The web app's libraries and the bundled fonts: every production dependency in
  frontend/package.json, plus every package whose code the web build put in the browser bundle
  (the list the build's own plugin writes, frontend/.svelte-kit/bundled-packages.json; the
  same rule as the build's third-party-licences.txt). Versions and licences come from
  frontend/package-lock.json; the text from the installed package. Run the web build first.

Each licence is checked with the same allow list as scripts/check_licences.py (imported, so the
two can't disagree): a package that list refuses stops the script. No library is used beyond
the standard library. Nothing is downloaded or sent.
"""

import importlib.util
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import Distribution, distributions
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
REPO = BACKEND.parent
NOTICES = REPO / "THIRD-PARTY-NOTICES.md"
FRONTEND = REPO / "frontend"
BUNDLED_LIST = FRONTEND / ".svelte-kit" / "bundled-packages.json"


def _licences() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licences", HERE / "check_licences.py")
    if spec is None or spec.loader is None:
        raise SystemExit("can't load scripts/check_licences.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licences"] = module
    spec.loader.exec_module(module)
    return module


lic = _licences()


@dataclass(frozen=True)
class Entry:
    name: str
    version: str
    licence: str
    text: str | None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip()


def _python_text(dist: Distribution) -> str | None:
    """The package's licence files (licence, copying, notice), in name order, joined."""
    found: list[tuple[str, str]] = []
    for file in dist.files or []:
        if lic.LICENCE_FILE.search(str(file)):
            path = Path(str(file.locate()))
            if path.is_file():
                found.append((str(file), _read(path)))
    if not found:
        return None
    return "\n\n".join(text for _, text in sorted(found))


def python_entries() -> list[Entry]:
    runtime, _ = lic.dependency_sets((BACKEND / "uv.lock").read_text())
    entries = []
    seen: set[str] = set()
    for dist in distributions():
        name = lic.normalise(dist.metadata["Name"] or "")
        if name in lic.SELF or name not in runtime or name in seen:
            continue
        seen.add(name)
        ok, detail = lic.check(dist)
        if not ok:
            raise SystemExit(f"{name} {dist.version}: {detail}")
        expression, _ = lic.licence_of(dist)
        licence = expression or detail.split(" (")[0]
        entries.append(Entry(name, dist.version, licence, _python_text(dist)))
    return sorted(entries, key=lambda e: e.name)


def _npm_text(folder: Path) -> str | None:
    names = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and lic.LICENCE_FILE.search(p.name) and not p.name.endswith(".json")
    )
    return _read(names[0]) if names else None


def npm_entries() -> list[Entry]:
    own = json.loads((FRONTEND / "package.json").read_text())
    if not BUNDLED_LIST.is_file():
        raise SystemExit(f"No list of bundled packages at {BUNDLED_LIST}: run the web build first.")
    bundled = json.loads(BUNDLED_LIST.read_text())
    if not isinstance(bundled, list) or not bundled:
        raise SystemExit(f"{BUNDLED_LIST} lists no packages.")
    names = sorted({*own.get("dependencies", {}), *bundled})
    lock = json.loads((FRONTEND / "package-lock.json").read_text())["packages"]
    entries = []
    for name in names:
        key = f"node_modules/{name}"
        info = lock.get(key)
        if info is None:
            raise SystemExit(f"{name} is not in frontend/package-lock.json")
        ok, detail = lic.check_npm_package(name, info, FRONTEND / key)
        if not ok:
            raise SystemExit(f"{name} {info.get('version')}: {detail}")
        raw = info["license"]
        licence = raw if isinstance(raw, str) else raw["type"]
        folder = FRONTEND / key
        text = _npm_text(folder) if folder.is_dir() else None
        entries.append(Entry(name, info["version"], licence, text))
    return entries


def render(python: Iterable[Entry], npm: Iterable[Entry]) -> str:
    lines = [
        "# Third-party notices",
        "",
        "Mealwright itself is AGPL-3.0-only. It ships with the open-source libraries and fonts",
        "below, each under its own licence: its name, version, licence and licence text.",
        "",
        "This file is written by `backend/scripts/third_party_notices.py` from the lock files",
        "(`backend/uv.lock`, `frontend/package-lock.json`) and the packages' own licence files.",
        "Do not edit it by hand: `./check` fails when it is out of date. The web app also serves",
        "the same list for its own libraries at `/third-party-licences.txt`.",
        "",
    ]
    for title, entries in (
        ("The server's Python libraries", python),
        ("The web app's libraries and fonts", npm),
    ):
        lines += [f"## {title}", ""]
        for e in entries:
            lines += [f"### {e.name} {e.version}", "", f"Licence: {e.licence}", ""]
            if e.text:
                lines += ["```text", e.text, "```", ""]
            else:
                lines += ["(This package ships no licence file; its licence is named above.)", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    text = render(python_entries(), npm_entries())
    if "--check" in sys.argv[1:]:
        if not NOTICES.is_file() or NOTICES.read_text() != text:
            print(
                "THIRD-PARTY-NOTICES.md is out of date. Run, in backend/:\n"
                "  uv run --frozen python -I scripts/third_party_notices.py"
            )
            return 1
        print("THIRD-PARTY-NOTICES.md is up to date.")
        return 0
    NOTICES.write_text(text)
    print(f"Wrote {NOTICES.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
