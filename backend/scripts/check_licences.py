"""Check every installed Python package against the licence allow list (spec section 8).

Allowed (cabledrawer 17 Oct): MIT, MIT-0, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL, PSF-2.0,
MPL-2.0, BlueOak-1.0.0.
Also allowed for development-only packages, never for anything in the app image (cabledrawer
17 Oct): 0BSD, Unlicense, CC0-1.0 and Zlib. Development-only means: Python packages
needed only by the dev group in uv.lock (anything else counts as shipped), and every
package of an npm project given with --npm-dev (the browser tests in e2e/). The web app's
own npm packages always count as shipped, even devDependencies, because the build bundles
parts of some of them (Svelte).
GPL-2.0-only is never allowed. OFL-1.1 is allowed for fonts only, so never for a Python
package. MPL-2.0 packages marked "Incompatible With Secondary Licenses" (MPL-2.0 Exhibit B)
must be rejected: MPL-2.0 only works with AGPL through that secondary-licence clause.
MIT-CMU is allowed for Pillow only (cabledrawer 19 Oct; ONE_PACKAGE): the package name and its
License-Expression must both match exactly, so any other package, or a change to Pillow's
licence, fails again.

Anything the script can't read for certain fails, rather than being guessed. Once a person
has checked such a package by hand, add it to REVIEWED with a note.

Run inside the project environment (stdlib only):

    uv run python -I scripts/check_licences.py                   # Python packages
    uv run python -I scripts/check_licences.py --npm ../frontend # an npm project that ships
    uv run python -I scripts/check_licences.py --npm-dev ../e2e  # a dev-only npm project

For npm, it reads the project's package-lock.json, which records every package's
licence. OFL-1.1 is accepted only for font packages (FONT_PACKAGES).
"""

import json
import re
import sys
import tomllib
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import Any

ALLOWED = {
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "ISC",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "PSF-2.0",
    "MPL-2.0",
    "MIT-0",  # cabledrawer 17 Oct (cffi)
    "BlueOak-1.0.0",  # cabledrawer 17 Oct (minimatch, used by ESLint)
}

# Allowed only for development-only packages (cabledrawer 17 Oct, standing rule; spec section 8).
DEV_ONLY = frozenset({"0BSD", "Unlicense", "CC0-1.0", "Zlib"})
DEV_ALLOWED = frozenset(ALLOWED | DEV_ONLY)

LOCK_FILE = Path(__file__).resolve().parent.parent / "uv.lock"

# Trove classifiers that name exactly one allowed licence. The generic
# "BSD License" classifier is left out on purpose: it could be BSD-4-Clause.
CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
}

# npm packages whose OFL-1.1 licence is allowed: fonts only (cabledrawer 17 Oct).
FONT_PACKAGES = re.compile(r"^@fontsource(-variable)?/")

# Packages checked by hand: name -> (licence, who checked it and when).
REVIEWED: dict[str, tuple[str, str]] = {}

# A licence allowed for one package only: name -> its exact License-Expression.
ONE_PACKAGE = {
    "pillow": "MIT-CMU",  # cabledrawer 19 Oct (photos); exact match, cabledrawer 20 Oct
}

# Never checked: the project itself.
SELF = {"mealwright"}

EXHIBIT_B = b"Incompatible With Secondary Licenses"
LICENCE_FILE = re.compile(r"(^|/)(licen[cs]es?|copying|notice)([./_-]|$)", re.IGNORECASE)


def evaluate(expression: str, allowed: frozenset[str] | set[str] = ALLOWED) -> bool:
    """True if an SPDX expression is satisfied by the allow list.

    Supports OR, AND, WITH and brackets. Unknown or LicenseRef ids are not allowed.
    """
    tokens = re.findall(r"\(|\)|[^\s()]+", expression)
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def take() -> str:
        nonlocal position
        token: str = tokens[position]
        position += 1
        return token

    def atom() -> bool:
        if peek() == "(":
            take()
            value = either()
            if peek() != ")":
                raise ValueError(f"unbalanced brackets in {expression!r}")
            take()
            return value
        token = take()
        if peek() == "WITH":  # e.g. "GPL-3.0-or-later WITH GCC-exception-3.1"
            take()
            take()
        return token in allowed

    def both() -> bool:
        value = atom()
        while peek() == "AND":
            take()
            value = atom() and value
        return value

    def either() -> bool:
        value = both()
        while peek() == "OR":
            take()
            value = both() or value
        return value

    result = either()
    if peek() is not None:
        raise ValueError(f"can't read {expression!r}")
    return result


def licence_of(dist: Distribution) -> tuple[str | None, str]:
    """(SPDX expression or None, where it came from)."""
    meta = dist.metadata
    if expression := meta.get("License-Expression"):
        return expression.strip(), "License-Expression"
    field = (meta.get("License") or "").strip()
    if field and "\n" not in field and len(field) < 60 and _looks_spdx(field):
        return field, "License field"
    found = {CLASSIFIERS[c] for c in meta.get_all("Classifier") or [] if c in CLASSIFIERS}
    if len(found) == 1:
        return found.pop(), "classifier"
    return None, field[:60] or "no licence metadata"


def _looks_spdx(text: str) -> bool:
    try:
        evaluate(text)
    except ValueError, IndexError:
        return False
    return all(t in ALLOWED or t in {"OR", "AND", "WITH", "(", ")"} for t in text.split())


def has_exhibit_b(dist: Distribution) -> bool:
    """True if the package's own files carry the MPL-2.0 Exhibit B notice.

    Licence files are skipped: the standard MPL-2.0 text includes the Exhibit B
    wording as a template, so it would match every MPL-2.0 package.
    """
    for file in dist.files or []:
        if LICENCE_FILE.search(str(file)):
            continue
        path = Path(file.locate())
        try:
            if path.stat().st_size > 2_000_000:
                continue
            if EXHIBIT_B in path.read_bytes():
                return True
        except OSError:
            continue
    return False


def check(dist: Distribution, dev: bool = False) -> tuple[bool, str]:
    name = (dist.metadata["Name"] or "").lower()
    if name in REVIEWED:
        licence, note = REVIEWED[name]
        return True, f"{licence} (checked by hand: {note})"
    expression, source = licence_of(dist)
    if expression is None:
        return False, f"can't tell ({source}); check by hand"
    if source == "License-Expression" and ONE_PACKAGE.get(name) == expression:
        return True, f"{expression} (allowed for {name} only)"
    try:
        allowed = evaluate(expression, DEV_ALLOWED if dev else ALLOWED)
    except ValueError, IndexError:
        return False, f"can't read {expression!r}; check by hand"
    if not allowed:
        if not dev and evaluate(expression, DEV_ALLOWED):
            return False, f"{expression} is allowed for development-only packages, not this one"
        return False, f"{expression} is not on the allow list"
    if "MPL-2.0" in expression and has_exhibit_b(dist):
        return False, f"{expression}, but marked 'Incompatible With Secondary Licenses'"
    return True, f"{expression} ({source}{', dev only' if dev else ''})"


def normalise(name: str) -> str:
    """A package name as uv.lock writes it (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _walk(packages: dict[str, list[dict[str, Any]]], start: list[dict[str, Any]]) -> set[str]:
    """Every package reachable from the given dependency entries, with their extras.

    Each (package, extra) is expanded once, so loops between extras can't hang the check.
    When the lock holds more than one version of a package (uv can resolve per platform),
    the dependencies of every version are followed.
    """
    found: set[str] = set()
    done: set[tuple[str, str | None]] = set()
    todo = list(start)
    while todo:
        dep = todo.pop()
        name = normalise(dep["name"])
        found.add(name)
        for extra in [None, *dep.get("extra", [])]:
            if (name, extra) in done:
                continue
            done.add((name, extra))
            for version in packages.get(name, []):
                if extra is None:
                    todo.extend(version.get("dependencies", []))
                else:
                    todo.extend(version.get("optional-dependencies", {}).get(extra, []))
    return found


def dependency_sets(lock_text: str) -> tuple[set[str], set[str]]:
    """(runtime, dev only): package names read from uv.lock.

    Runtime is everything reachable from the project's own dependencies and its extras.
    Dev only is what the dev group reaches and the runtime doesn't. A package in neither
    (another dependency group, say) is treated as shipped. Markers are ignored, so a
    package needed on any platform counts: that only makes the check stricter.
    """
    lock = tomllib.loads(lock_text)
    packages: dict[str, list[dict[str, Any]]] = {}
    for package in lock.get("package", []):
        packages.setdefault(normalise(package["name"]), []).append(package)
    own = [version for name in SELF for version in packages.get(name, [])]
    if not own:
        raise SystemExit(f"uv.lock has no entry for {sorted(SELF)}; can't tell what ships")
    runtime_start = [dep for v in own for dep in v.get("dependencies", [])]
    runtime_start += [
        dep for v in own for deps in v.get("optional-dependencies", {}).values() for dep in deps
    ]
    dev_start = [dep for v in own for dep in v.get("dev-dependencies", {}).get("dev", [])]
    runtime = _walk(packages, runtime_start)
    if not runtime:
        raise SystemExit("uv.lock lists no runtime dependencies; can't tell what ships")
    return runtime, _walk(packages, dev_start) - runtime


def _has_exhibit_b_files(folder: Path) -> bool:
    for path in folder.rglob("*"):
        if "node_modules" in path.relative_to(folder).parts or LICENCE_FILE.search(path.name):
            continue
        try:
            small_file = path.is_file() and path.stat().st_size <= 2_000_000
            if small_file and EXHIBIT_B in path.read_bytes():
                return True
        except OSError:
            continue
    return False


def check_npm_package(
    name: str, info: dict[str, object], folder: Path, dev: bool = False
) -> tuple[bool, str]:
    if name in REVIEWED:
        licence, note = REVIEWED[name]
        return True, f"{licence} (checked by hand: {note})"
    raw = info.get("license")
    if isinstance(raw, dict):  # old style: {"type": "MIT"}
        raw = raw.get("type")
    if not isinstance(raw, str) or not raw.strip():
        return False, "no licence in package-lock.json; check by hand"
    licence = raw
    base = DEV_ALLOWED if dev else ALLOWED
    allowed = base | {"OFL-1.1"} if FONT_PACKAGES.match(name) else base
    try:
        ok = evaluate(licence, allowed)
    except ValueError, IndexError:
        return False, f"can't read {licence!r}; check by hand"
    if not ok:
        if not dev and evaluate(licence, DEV_ALLOWED):
            return False, f"{licence} is allowed for development-only packages, not this one"
        return False, f"{licence} is not on the allow list"
    if "MPL-2.0" in licence and folder.is_dir() and _has_exhibit_b_files(folder):
        return False, f"{licence}, but marked 'Incompatible With Secondary Licenses'"
    return True, f"{licence}, dev only" if dev else licence


def main_npm(project: Path, dev: bool = False) -> int:
    lock = json.loads((project / "package-lock.json").read_text())
    failures = 0
    count = 0
    for key, info in sorted(lock.get("packages", {}).items()):
        if not key or info.get("link"):
            continue  # the project itself, or a link to a local folder
        name = info.get("name") or key.rsplit("node_modules/", 1)[-1]
        ok, detail = check_npm_package(name, info, project / key, dev)
        count += 1
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name} {info.get('version', '?')}: {detail}")
    print(f"\n{count} packages, {failures} not allowed")
    return 1 if failures else 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] in {"--npm", "--npm-dev"}:
        return main_npm(Path(sys.argv[2]), dev=sys.argv[1] == "--npm-dev")
    _, dev_only = dependency_sets(LOCK_FILE.read_text())
    failures = 0
    seen: set[str] = set()
    for dist in sorted(distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = (dist.metadata["Name"] or "").lower()
        if name in SELF or name in seen:
            continue
        seen.add(name)
        ok, detail = check(dist, dev=normalise(name) in dev_only)
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name} {dist.version}: {detail}")
    print(f"\n{len(seen)} packages, {failures} not allowed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
