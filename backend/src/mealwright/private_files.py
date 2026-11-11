"""Everything in the data folder is readable and writable only by the user Mealwright runs
as (spec section 7, "Database file readable only by Mealwright", cabledrawer 19 Oct): files
0600, folders 0700.

New files get this from the process umask (set in `mealwright.__main__`); files and folders
that an older version made with wider permissions are fixed by `tighten` on every start."""

import logging
import os
from pathlib import Path

FILE_MODE = 0o600
FOLDER_MODE = 0o700

log = logging.getLogger(__name__)


def tighten(data_dir: Path) -> None:
    """Set the data folder and everything in it to 0700 (folders) and 0600 (files).
    Symbolic links are left alone. A path that can't be changed (it belongs to someone
    else) gets one warning line at the end, and start-up goes on."""
    if not data_dir.is_dir():
        return
    failed = 0
    for folder, subfolders, files in os.walk(data_dir):
        base = Path(folder)
        for name, mode in [(".", FOLDER_MODE)] + [(n, FILE_MODE) for n in files]:
            path = base / name
            if path.is_symlink():
                continue
            failed += _chmod(path, mode)
        for name in subfolders:
            path = base / name
            if not path.is_symlink():
                failed += _chmod(path, FOLDER_MODE)
    if failed:
        log.warning(
            "Couldn't restrict %d path(s) in %s to the Mealwright user. The data folder must "
            "belong to the user Mealwright runs as (see the install notes).",
            failed,
            data_dir,
        )


def _chmod(path: Path, mode: int) -> int:
    try:
        if (path.stat().st_mode & 0o777) != mode:
            path.chmod(mode)
    except OSError:
        return 1
    return 0
