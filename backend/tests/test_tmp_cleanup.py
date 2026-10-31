"""A test run leaves nothing behind in /tmp (cabledrawer 22 Oct).

On 22 Oct leftover test folders filled 2.8 GB of /tmp (a memory-backed disk on the dev
machine). The pytest settings in pyproject.toml now remove each test's folder and the run's own
folder. These tests run a tiny pytest of their own, with its own private temp folder, so no
other run on the machine can change the answer.
"""

import os
import subprocess
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

INNER_TEST = """
def test_writes_into_its_temp_folder(tmp_path):
    (tmp_path / "data.bin").write_bytes(b"x" * 1000)
    assert (tmp_path / "data.bin").exists()
"""


def run_inner(tmp_path: Path, *extra: str) -> list[str]:
    """Run one tiny test under the project's pytest settings; what is left in its /tmp."""
    project = tmp_path / "project"
    private_tmp = tmp_path / "private-tmp"
    project.mkdir()
    private_tmp.mkdir()
    (project / "test_inner.py").write_text(INNER_TEST)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["TMPDIR"] = str(private_tmp)
    done = subprocess.run(  # noqa: S603 (fixed command, no user input)
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(PYPROJECT),
            "--rootdir",
            str(project),
            *extra,
            str(project / "test_inner.py"),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    # pytest keeps "pytest-of-<user>" itself and a "pytest-current" link; the run folders
    # ("pytest-0", "pytest-1" …) and anything inside them are what must be gone.
    return sorted(
        str(path.relative_to(private_tmp))
        for path in private_tmp.rglob("*")
        if path.is_dir()
        and path.name.startswith("pytest-")
        and not path.name.startswith("pytest-of-")
    )


def test_a_run_removes_its_temp_folders(tmp_path: Path) -> None:
    assert run_inner(tmp_path) == []


def test_the_check_can_see_folders_that_are_left(tmp_path: Path) -> None:
    # The same run with the old setting leaves its folder, so the test above isn't vacuous.
    left = run_inner(tmp_path, "-o", "tmp_path_retention_policy=all")
    assert left, "expected pytest to keep its folder with the retention policy on 'all'"


def test_a_run_in_several_workers_removes_its_temp_folders(tmp_path: Path) -> None:
    # ./check runs the backend tests in several workers (pytest-xdist, cabledrawer 31 Oct); each
    # worker has a folder of its own inside the run's, and all of them must go too.
    assert run_inner(tmp_path, "-n", "2") == []


def test_the_check_can_see_a_worker_folder_that_is_left(tmp_path: Path) -> None:
    left = run_inner(tmp_path, "-n", "2", "-o", "tmp_path_retention_policy=all")
    assert left, "expected pytest to keep its folder with the retention policy on 'all'"
