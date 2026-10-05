# ABOUTME: Tests that the event log is append-only: an update, a delete or a replacement of an event raises.
# ABOUTME: The triggers are checked on a fresh store and on an events table that was dropped and created again.
import sqlite3
from pathlib import Path

import pytest

from uwh.runtime.store import create_tables, open_store


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "uwh.db"))


def test_events_refuse_update_delete_and_replacement(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    for statement in (
        "UPDATE events SET type = 'x' WHERE id = 1",
        "DELETE FROM events WHERE id = 1",
        "INSERT OR REPLACE INTO events (id, type) VALUES (1, 'x')",
        "REPLACE INTO events (id, type) VALUES (1, 'x')",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute(statement)
    assert db.execute("SELECT id, type FROM events").fetchall() == [(1, "run_started")]


def test_recreating_events_restores_the_append_only_triggers(db: sqlite3.Connection) -> None:
    db.execute("DROP TABLE events")
    create_tables(db, ["events"])
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE events SET type = 'x' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM events WHERE id = 1")
