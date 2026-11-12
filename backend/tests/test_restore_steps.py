"""The How to restore screen and docs/restore.md give the same commands (D1 review r1).

The screen is the steps of the doc for whoever looks after the server; a command that differs
between them (say, a listing that puts the newest backup in a different place) could have
someone restore an old copy.
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
DOC = ROOT / "docs" / "restore.md"
SCREEN = ROOT / "frontend" / "src" / "routes" / "(app)" / "settings" / "your-data" / "restore"


def _doc_commands() -> list[str]:
    text = DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"^ *```bash\n(.*?)^ *```", text, flags=re.MULTILINE | re.DOTALL)
    return [
        "\n".join(line.strip() for line in block.strip().splitlines()) for block in blocks
    ]


def _screen_commands() -> list[str]:
    text = (SCREEN / "+page.svelte").read_text(encoding="utf-8")
    blocks = re.findall(r"<pre><code\s*>(.*?)</code\s*>\s*</pre>", text, flags=re.DOTALL)
    return [
        "\n".join(line.strip() for line in html.unescape(block).strip().splitlines())
        for block in blocks
    ]


def test_the_screen_and_the_doc_give_the_same_commands() -> None:
    doc = _doc_commands()
    assert len(doc) >= 5
    assert _screen_commands() == doc


def test_the_newest_backup_is_listed_first() -> None:
    """`ls` sorts by name, so `pre-upgrade-…` copies came last whatever their age."""
    for commands in (_doc_commands(), _screen_commands()):
        assert "sudo ls -lt data/backups/" in commands
        assert not any("ls -l data/backups" in block for block in commands)


def test_a_copy_of_the_data_folder_leaves_the_logs_out() -> None:
    """Spec, "Logs (cabledrawer 17 Oct)": backups leave `data/logs` out, or they keep sign-in
    lines beyond 14 days."""
    for commands in (_doc_commands(), _screen_commands()):
        (copy,) = [block for block in commands if " -czf " in block]
        assert "--exclude=data/logs" in copy
