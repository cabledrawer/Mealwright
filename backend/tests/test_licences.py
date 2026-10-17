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
