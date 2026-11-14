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
    return ["\n".join(line.strip() for line in block.strip().splitlines()) for block in blocks]


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


def test_both_put_the_photos_back_with_the_same_commands() -> None:
    """D2 (0.9.5): a backup's photo folder goes back with `cp -an`, which adds to the photos
    already there; the screen and the doc say so in one block, in the same place."""
    for commands in (_doc_commands(), _screen_commands()):
        (back,) = [block for block in commands if "-photos/." in block]
        assert back.splitlines() == [
            "sudo mkdir -p data/photos",
            "sudo cp -an data/backups/backup-<date>-<time>-photos/. data/photos/",
            "sudo chown -R 10001:10001 data/photos",
        ]
        # After the database is in place, before Mealwright starts.
        blocks = [block for block in commands if "cp data/backups" in block or "up -d" in block]
        assert commands.index(blocks[0]) < commands.index(back) < commands.index(blocks[1])


def test_the_documented_photo_command_works_over_files_that_are_the_same_file(
    tmp_path: Path,
) -> None:
    """On the same server the live photos and the backup's are hard links to one file: plain
    `cp -a` prints "are the same file" and exits 1. The documented command, read from
    docs/restore.md, exits 0 and brings the photo that is missing."""
    import subprocess

    (block,) = [b for b in _doc_commands() if "-photos/." in b]
    lines = [line.removeprefix("sudo ") for line in block.splitlines()]
    lines = [line for line in lines if not line.startswith("chown")]  # needs root
    script = "\n".join(lines).replace("<date>-<time>", "20261101-030000")
    backup = tmp_path / "data/backups/backup-20261101-030000-photos/1"
    live = tmp_path / "data/photos/1"
    backup.mkdir(parents=True)
    live.mkdir(parents=True)
    (backup / "kept.jpg").write_bytes(b"kept")
    (backup / "missing.jpg").write_bytes(b"missing")
    (live / "kept.jpg").hardlink_to(backup / "kept.jpg")
    (live / "newer.jpg").write_bytes(b"newer, not in the backup")

    plain = subprocess.run(  # noqa: S603, S607
        ["cp", "-a", f"{backup.parent}/.", f"{live.parent}/"], capture_output=True
    )
    assert plain.returncode != 0  # why the documented command is not `cp -a`
    (live / "missing.jpg").unlink(missing_ok=True)

    done = subprocess.run(  # noqa: S603, S607
        ["bash", "-ec", script], cwd=tmp_path, capture_output=True
    )
    assert done.returncode == 0, done.stderr
    assert (live / "missing.jpg").read_bytes() == b"missing"
    assert (live / "kept.jpg").read_bytes() == b"kept"
    assert (live / "newer.jpg").read_bytes() == b"newer, not in the backup"
