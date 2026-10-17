"""Check every installed Python package against the licence allow list (spec section 8).

Allowed (cabledrawer 17 Oct): MIT, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL, PSF-2.0, MPL-2.0.
GPL-2.0-only is never allowed. OFL-1.1 is allowed for fonts only, so never for a Python
package. MPL-2.0 packages marked "Incompatible With Secondary Licenses" (MPL-2.0 Exhibit B)
must be rejected: MPL-2.0 only works with AGPL through that secondary-licence clause.

Anything the script can't read for certain fails, rather than being guessed. Once a person
has checked such a package by hand, add it to REVIEWED with a note.

Run inside the project environment (stdlib only):

    uv run python -I scripts/check_licences.py
"""

import re
import sys
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
}

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

# Packages checked by hand: name -> (licence, who checked it and when).
REVIEWED: dict[str, tuple[str, str]] = {}

# Never checked: the project itself.
SELF = {"mealwright"}

EXHIBIT_B = b"Incompatible With Secondary Licenses"
LICENCE_FILE = re.compile(r"(^|/)(licen[cs]es?|copying|notice)([./_-]|$)", re.IGNORECASE)


def evaluate(expression: str) -> bool:
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
        return token in ALLOWED

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


def check(dist: Distribution) -> tuple[bool, str]:
    name = (dist.metadata["Name"] or "").lower()
    if name in REVIEWED:
        licence, note = REVIEWED[name]
        return True, f"{licence} (checked by hand: {note})"
    expression, source = licence_of(dist)
    if expression is None:
        return False, f"can't tell ({source}); check by hand"
    try:
        allowed = evaluate(expression)
    except ValueError, IndexError:
        return False, f"can't read {expression!r}; check by hand"
    if not allowed:
        return False, f"{expression} is not on the allow list"
    if "MPL-2.0" in expression and has_exhibit_b(dist):
        return False, f"{expression}, but marked 'Incompatible With Secondary Licenses'"
    return True, f"{expression} ({source})"


def main() -> int:
    failures = 0
    seen: set[str] = set()
    for dist in sorted(distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = (dist.metadata["Name"] or "").lower()
        if name in SELF or name in seen:
            continue
        seen.add(name)
        ok, detail = check(dist)
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name} {dist.version}: {detail}")
    print(f"\n{len(seen)} packages, {failures} not allowed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
