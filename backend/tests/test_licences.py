import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="module")
def lic() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licences", SCRIPTS / "check_licences.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDist:
    def __init__(self, name: str, files: list[Any] | None = None, **fields: Any) -> None:
        self.metadata = _Meta({"Name": name, **fields})
        self.version = "1.0"
        self.files = files or []


class _Meta(dict[str, Any]):
    def get_all(self, key: str) -> list[str] | None:
        value = self.get(key)
        return list(value) if value else None


@pytest.mark.parametrize(
    ("expression", "allowed"),
    [
        ("MIT", True),
        ("Apache-2.0 OR BSD-2-Clause", True),
        ("GPL-2.0-only OR MIT", True),
        ("MIT AND GPL-2.0-only", False),
        ("GPL-2.0-only", False),
        ("OFL-1.1", False),
        ("(MIT OR Apache-2.0) AND PSF-2.0", True),
        ("GPL-3.0-or-later WITH GCC-exception-3.1", True),
        ("MIT-0", True),
        ("BlueOak-1.0.0", True),
        ("SSPL-1.0", False),
        ("LicenseRef-Proprietary", False),
    ],
)
def test_evaluate(lic: ModuleType, expression: str, allowed: bool) -> None:
    assert lic.evaluate(expression) is allowed


def test_generic_bsd_classifier_needs_a_person(lic: ModuleType) -> None:
    dist = FakeDist("thing", Classifier=["License :: OSI Approved :: BSD License"])
    ok, detail = lic.check(dist)
    assert not ok and "check by hand" in detail


def test_mpl_classifier_is_allowed(lic: ModuleType) -> None:
    dist = FakeDist(
        "thing", Classifier=["License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"]
    )
    assert lic.check(dist) == (True, "MPL-2.0 (classifier)")


def test_mpl_with_exhibit_b_is_rejected(lic: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "thing.py"
    source.write_text(
        '# This Source Code Form is "Incompatible With Secondary Licenses", as defined by\n'
        "# the Mozilla Public License, v. 2.0.\n"
    )
    licence = tmp_path / "LICENSE"
    licence.write_text('Exhibit B - "Incompatible With Secondary Licenses" Notice\n')

    class File:
        def __init__(self, path: Path) -> None:
            self.path = path

        def locate(self) -> Path:
            return self.path

        def __str__(self) -> str:
            return self.path.name

    plain = FakeDist("plain", files=[File(licence)], **{"License-Expression": "MPL-2.0"})
    marked = FakeDist(
        "marked", files=[File(licence), File(source)], **{"License-Expression": "MPL-2.0"}
    )
    assert lic.check(plain)[0] is True
    ok, detail = lic.check(marked)
    assert not ok and "Incompatible With Secondary Licenses" in detail


def test_installed_packages_pass(lic: ModuleType) -> None:
    assert lic.main() == 0


@pytest.mark.parametrize(
    ("name", "licence", "allowed"),
    [
        ("@fontsource/newsreader", "OFL-1.1", True),
        ("@fontsource-variable/plus-jakarta-sans", "OFL-1.1", True),
        ("some-icons", "OFL-1.1", False),  # OFL only for fonts
        ("left-pad", {"type": "MIT"}, True),  # old-style licence object
        ("mystery", None, False),
        ("gpl2-thing", "GPL-2.0-only", False),
    ],
)
def test_npm_packages(
    lic: ModuleType, tmp_path: Path, name: str, licence: object, allowed: bool
) -> None:
    info = {"version": "1.0.0"} | ({"license": licence} if licence is not None else {})
    assert lic.check_npm_package(name, info, tmp_path / "missing")[0] is allowed


def test_npm_lockfile(lic: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "package-lock.json").write_text(
        '{"packages": {"": {"name": "app"},'
        ' "node_modules/a": {"version": "1.0.0", "license": "MIT"},'
        ' "node_modules/b": {"version": "2.0.0", "license": "SSPL-1.0"}}}'
    )
    assert lic.main_npm(tmp_path) == 1


@pytest.mark.parametrize("licence", ["0BSD", "Unlicense", "CC0-1.0", "Zlib"])
def test_dev_only_licences(lic: ModuleType, tmp_path: Path, licence: str) -> None:
    dist = FakeDist("tool", **{"License-Expression": licence})
    assert lic.check(dist, dev=True)[0] is True
    ok, detail = lic.check(dist)
    assert not ok and "development-only" in detail
    info = {"version": "1.0.0", "license": licence}
    assert lic.check_npm_package("tool", info, tmp_path, dev=True)[0] is True
    assert lic.check_npm_package("tool", info, tmp_path)[0] is False


def test_dev_only_never_relaxes_the_rest(lic: ModuleType, tmp_path: Path) -> None:
    for licence in ["GPL-2.0-only", "SSPL-1.0", "OFL-1.1"]:
        info = {"version": "1.0.0", "license": licence}
        assert lic.check_npm_package("tool", info, tmp_path, dev=True)[0] is False


LOCK = """
version = 1
[[package]]
name = "mealwright"
dependencies = [{ name = "fastapi" }, { name = "uvicorn", extra = ["standard"] }]
[package.optional-dependencies]
extra-feature = [{ name = "pillow" }]
[package.dev-dependencies]
dev = [{ name = "pytest" }, { name = "fastapi" }]
docs = [{ name = "sphinx" }]

[[package]]
name = "fastapi"
dependencies = [{ name = "Typing_Extensions" }]

[[package]]
name = "uvicorn"
[package.optional-dependencies]
standard = [{ name = "uvloop" }]

[[package]]
name = "uvloop"
version = "1"
[[package]]
name = "uvloop"
version = "2"
dependencies = [{ name = "only-in-v2" }]

[[package]]
name = "pytest"
dependencies = [{ name = "pluggy" }, { name = "a", extra = ["x"] }]

[[package]]
name = "a"
[package.optional-dependencies]
x = [{ name = "b", extra = ["y"] }]
[[package]]
name = "b"
[package.optional-dependencies]
y = [{ name = "a", extra = ["x"] }]
"""


def test_dependency_sets_follow_the_lock(lic: ModuleType) -> None:
    runtime, dev_only = lic.dependency_sets(LOCK)
    assert runtime == {
        "fastapi",
        "typing-extensions",
        "uvicorn",
        "uvloop",
        "only-in-v2",  # every version's dependencies count
        "pillow",  # the project's own extras ship
    }
    assert dev_only == {"pytest", "pluggy", "a", "b"}  # extras loop ends; sphinx not dev


def test_missing_project_entry_fails(lic: ModuleType) -> None:
    with pytest.raises(SystemExit, match="no entry"):
        lic.dependency_sets(LOCK.replace('name = "mealwright"', 'name = "renamed"'))


def test_real_lock_marks_dev_tools_as_dev(lic: ModuleType) -> None:
    runtime, dev_only = lic.dependency_sets(lic.LOCK_FILE.read_text())
    assert {"fastapi", "sqlalchemy", "argon2-cffi"} <= runtime
    assert {"pytest", "mypy", "ruff"} <= dev_only
    assert not runtime & dev_only
