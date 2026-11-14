"""THIRD-PARTY-NOTICES.md (0.9.5): written by scripts/third_party_notices.py from the lock files.

The step that proves the whole file is current is in ./check (it needs the web build); these
tests hold the parts that need no build.
"""

import importlib.util
import re
from importlib.metadata import distributions
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
NOTICES = Path(__file__).resolve().parents[2] / "THIRD-PARTY-NOTICES.md"


@pytest.fixture(scope="module")
def notices() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tpn", SCRIPTS / "third_party_notices.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_file_names_every_runtime_python_library_of_the_lock(notices: ModuleType) -> None:
    runtime, dev_only = notices.lic.dependency_sets((SCRIPTS.parent / "uv.lock").read_text())
    headings = {m.group(1) for m in re.finditer(r"^### (\S+) \S+$", NOTICES.read_text(), re.M)}
    # A library that exists only for another platform (tzdata, for Windows) is not installed here,
    # so the script can't list it: only installed ones are asked for.
    installed = {notices.lic.normalise(d.metadata["Name"] or "") for d in distributions()}
    assert not {n for n in runtime & installed if n not in headings}, (
        "THIRD-PARTY-NOTICES.md is missing a library of uv.lock: run scripts/third_party_notices.py"
    )
    assert not (dev_only & headings), "a development-only library is in the notices"


def test_the_file_names_the_fonts_and_every_web_dependency(notices: ModuleType) -> None:
    import json

    own = json.loads((SCRIPTS.parents[1] / "frontend" / "package.json").read_text())
    headings = {m.group(1) for m in re.finditer(r"^### (\S+) \S+$", NOTICES.read_text(), re.M)}
    assert set(own["dependencies"]) <= headings
    assert "@fontsource-variable/newsreader" in headings
    assert "@fontsource-variable/plus-jakarta-sans" in headings


def test_every_licence_in_the_file_is_on_the_allow_list(notices: ModuleType) -> None:
    lic = notices.lic
    for name, licence in re.findall(r"^### (\S+) \S+\n\nLicence: (.+)$", NOTICES.read_text(), re.M):
        font = lic.FONT_PACKAGES.match(name) is not None
        allowed = lic.ALLOWED | {"OFL-1.1"} if font else lic.ALLOWED
        ok = lic.evaluate(licence, allowed) or (
            name == "pillow" and licence == lic.ONE_PACKAGE["pillow"]
        )
        assert ok, f"{name}: {licence} is not on the allow list"


def test_render_gives_each_package_a_heading_licence_and_text(notices: ModuleType) -> None:
    entry = notices.Entry
    text = notices.render(
        [entry("alpha", "1.0", "MIT", "Alpha licence text")],
        [entry("beta", "2.0", "ISC", None)],
    )
    assert "### alpha 1.0\n\nLicence: MIT\n\n```text\nAlpha licence text\n```" in text
    assert "### beta 2.0\n\nLicence: ISC\n\n(This package ships no licence file" in text
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_the_image_carries_the_notices_and_the_check_proves_it() -> None:
    repo = NOTICES.parent
    assert (
        "COPY THIRD-PARTY-NOTICES.md /app/THIRD-PARTY-NOTICES.md"
        in (repo / "Dockerfile").read_text()
    )
    assert "!THIRD-PARTY-NOTICES.md" in (repo / ".dockerignore").read_text().splitlines()
    check = (repo / "check").read_text()
    assert 'step "image: notices"        notices_in_image' in check
    assert "/app/THIRD-PARTY-NOTICES.md | cmp -s - THIRD-PARTY-NOTICES.md" in check
