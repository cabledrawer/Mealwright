"""One undo window (0.9.5-beta.3, D4, CL9).

cabledrawer 11 Nov: the undo window "is not a setting in 0.9 (no `undo_days`)". The server has
one number, `household.UNDO_DAYS`; the web app's sentences take theirs from
frontend/src/lib/undoWords.ts. Nothing else names the window.
"""

import re
from pathlib import Path

from mealwright import household
from mealwright.history import too_old_sentence

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "backend" / "src" / "mealwright"


def test_the_web_app_names_the_same_window() -> None:
    words = (ROOT / "frontend" / "src" / "lib" / "undoWords.ts").read_text(encoding="utf-8")
    found = re.search(r"export const UNDO_DAYS = (\d+);", words)
    assert found is not None
    assert int(found.group(1)) == household.UNDO_DAYS == 7
    assert household.UNDO_WINDOW.days == household.UNDO_DAYS
    assert too_old_sentence() == "Too late to undo: changes can be undone for 7 days."


def test_no_other_window_in_the_server() -> None:
    """No feature keeps a window of its own or reads the old column."""
    for path in SOURCES.rglob("*.py"):
        if "migrations" in path.parts or path.name in ("household.py", "models.py"):
            continue
        text = path.read_text(encoding="utf-8")
        assert ".undo_days" not in text, path
        assert not re.search(r"UNDO_DAYS\s*=", text), path


def test_no_sentence_on_screen_names_the_days_by_hand() -> None:
    """Every on-screen sentence about the window is built from UNDO_SPAN."""
    sources = ROOT / "frontend" / "src"
    for path in [*sources.rglob("*.ts"), *sources.rglob("*.svelte")]:
        if path.name.endswith(".test.ts") or path.name == "undoWords.ts":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/**")):
                continue
            assert not re.search(r"['\"`>][^'\"`<]*\b(7|seven) days", line), (path, line)
