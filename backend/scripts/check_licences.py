"""Check every installed Python package against the licence allow list (spec section 8).

Allowed (cabledrawer 17 Oct): MIT, MIT-0, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL, PSF-2.0,
MPL-2.0, BlueOak-1.0.0.
Also allowed for development-only packages, never for anything in the app image (cabledrawer
17 Oct): 0BSD, Unlicense, CC0-1.0 and Zlib. Development-only means: Python packages needed
only by the dev group in uv.lock, and every package of an npm project given with
--npm-dev (the browser tests in e2e/). The web app's own npm packages always count as
shipped, even devDependencies, because the build bundles parts of some of them (Svelte).
GPL-2.0-only is never allowed. OFL-1.1 is allowed for fonts only, so never for a Python
package. MPL-2.0 packages marked "Incompatible With Secondary Licenses" (MPL-2.0 Exhibit B)
must be rejected: MPL-2.0 only works with AGPL through that secondary-licence clause.

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


def runtime_packages(lock_text: str) -> set[str]:
    """Names of the packages the app needs to run, read from uv.lock.

    Walks the project's own dependencies (with their extras), not its dev group. Markers
    are ignored, so a package needed on any platform counts: that only makes the check
    stricter.
    """
    lock = tomllib.loads(lock_text)
    packages = {p["name"]: p for p in lock.get("package", [])}
    needed: set[str] = set()
    todo = [
        dep for name in SELF if name in packages for dep in packages[name].get("dependencies", [])
    ]
    while todo:
        dep = todo.pop()
        name = dep["name"]
        package = packages.get(name, {})
        extras = dep.get("extra", [])
        if name in needed and not extras:
            continue
        needed.add(normalise(name))
        todo.extend(package.get("dependencies", []))
        for extra in extras:
            todo.extend(package.get("optional-dependencies", {}).get(extra, []))
    return needed


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
    runtime = runtime_packages(LOCK_FILE.read_text())
    failures = 0
    seen: set[str] = set()
    for dist in sorted(distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = (dist.metadata["Name"] or "").lower()
        if name in SELF or name in seen:
            continue
        seen.add(name)
        ok, detail = check(dist, dev=normalise(name) not in runtime)
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name} {dist.version}: {detail}")
    print(f"\n{len(seen)} packages, {failures} not allowed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
