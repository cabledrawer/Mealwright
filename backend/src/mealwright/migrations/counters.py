"""Keep SQLite's "never reuse an id" counters over a migration (whole-0.8 review, D1).

A table made with AUTOINCREMENT has its counter in `sqlite_sequence`. Rebuilding the table (what
every `batch_alter_table` does on SQLite: copy, drop, rename) starts that counter again at the
highest id left, so an id of a row removed just before is handed out a second time and an old
Undo can land on the new row. `env.py` reads the counters before a migration run and puts each
one back afterwards if it fell, so every rebuild, upgrade and downgrade keeps them. Nothing here
runs on Postgres, which keeps its sequences by itself.
"""

from sqlalchemy import Connection


def _has_counters(connection: Connection) -> bool:
    return (
        connection.dialect.name == "sqlite"
        and connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
        ).first()
        is not None
    )


def read_counters(connection: Connection) -> dict[str, int]:
    """Each AUTOINCREMENT table's counter (empty on any other database)."""
    if not _has_counters(connection):
        return {}
    return {
        str(name): int(seq)
        for name, seq in connection.exec_driver_sql("SELECT name, seq FROM sqlite_sequence")
    }


def raise_counter(connection: Connection, table: str, at_least: int) -> bool:
    """Make `table`'s counter at least `at_least` and at least its highest id. Does nothing for a
    table that is gone or has no AUTOINCREMENT. True when the counter went up."""
    if not _has_counters(connection):
        return False
    made = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).scalar()
    if made is None or "AUTOINCREMENT" not in made.upper():
        return False
    quoted = '"' + table.replace('"', '""') + '"'
    top = connection.exec_driver_sql(f"SELECT coalesce(max(rowid), 0) FROM {quoted}").scalar_one()  # noqa: S608  # nosec B608
    want = max(at_least, int(top))
    row = connection.exec_driver_sql(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
    ).first()
    if row is None:
        if want == 0:
            return False
        connection.exec_driver_sql(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, want)
        )
        return True
    if int(row[0]) >= want:
        return False
    connection.exec_driver_sql("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (want, table))
    return True


def restore_counters(connection: Connection, saved: dict[str, int]) -> None:
    """Put back every counter that is lower than it was."""
    for table, seq in saved.items():
        raise_counter(connection, table, seq)
