# ABOUTME: Tests that the opened database has exactly the A.1 tables and columns, refuses values outside the value sets and keeps events append-only.
# ABOUTME: The expected tables are written out here from A.1; each refusal test inserts a bad value and a good one so a missing constraint cannot pass.
import sqlite3
from pathlib import Path

import pytest

from uwh.runtime.store import create_tables, open_store

# A.1: table -> ordered (column, declared type, primary-key position).
EXPECTED_TABLES: dict[str, list[tuple[str, str, int]]] = {
    "leads": [
        ("lead_id", "TEXT", 1),
        ("run_id", "TEXT", 0),
        ("source", "TEXT", 0),
        ("received_at", "TEXT", 0),
        ("status", "TEXT", 0),
        ("revision", "INTEGER", 0),
        ("plan_json", "TEXT", 0),
        ("plan_hash", "TEXT", 0),
    ],
    "events": [
        ("id", "INTEGER", 1),
        ("run_id", "TEXT", 0),
        ("mode", "TEXT", 0),
        ("lead_id", "TEXT", 0),
        ("type", "TEXT", 0),
        ("payload_json", "TEXT", 0),
        ("actor", "TEXT", 0),
        ("ruleset_hash", "TEXT", 0),
        ("prompt_versions_json", "TEXT", 0),
        ("model_id", "TEXT", 0),
        ("request_id", "TEXT", 0),
        ("real_ts", "TEXT", 0),
        ("sim_ts", "TEXT", 0),
    ],
    "observations": [
        ("id", "INTEGER", 1),
        ("lead_id", "TEXT", 0),
        ("key", "TEXT", 0),
        ("value_json", "TEXT", 0),
        ("source", "TEXT", 0),
        ("evidence_json", "TEXT", 0),
        ("status", "TEXT", 0),
        ("event_id", "INTEGER", 0),
    ],
    "effective_facts": [
        ("lead_id", "TEXT", 1),
        ("key", "TEXT", 2),
        ("observation_id", "INTEGER", 0),
        ("confirmed", "INTEGER", 0),
    ],
    "blockers": [
        ("id", "INTEGER", 1),
        ("lead_id", "TEXT", 0),
        ("kind", "TEXT", 0),
        ("owner", "TEXT", 0),
        ("detail_json", "TEXT", 0),
        ("opened_event_id", "INTEGER", 0),
        ("closed_event_id", "INTEGER", 0),
    ],
    "intents": [
        ("id", "TEXT", 1),
        ("run_id", "TEXT", 0),
        ("lead_id", "TEXT", 0),
        ("round", "INTEGER", 0),
        ("kind", "TEXT", 0),
        ("recipient", "TEXT", 0),
        ("subject", "TEXT", 0),
        ("body", "TEXT", 0),
        ("ask_ids_json", "TEXT", 0),
        ("payload_hash", "TEXT", 0),
        ("state", "TEXT", 0),
        ("mailbox_id", "INTEGER", 0),
    ],
    "approvals": [
        ("id", "INTEGER", 1),
        ("lead_id", "TEXT", 0),
        ("item_kind", "TEXT", 0),
        ("intent_id", "TEXT", 0),
        ("lead_revision", "INTEGER", 0),
        ("plan_hash", "TEXT", 0),
        ("ruleset_hash", "TEXT", 0),
        ("recipient", "TEXT", 0),
        ("payload_hash", "TEXT", 0),
        ("actor", "TEXT", 0),
        ("decision", "TEXT", 0),
        ("reason", "TEXT", 0),
        ("event_id", "INTEGER", 0),
    ],
    "runs": [
        ("run_id", "TEXT", 1),
        ("seed", "INTEGER", 0),
        ("mode", "TEXT", 0),
        ("started_at", "TEXT", 0),
        ("status", "TEXT", 0),
    ],
    "proposals": [
        ("id", "INTEGER", 1),
        ("kind", "TEXT", 0),
        ("payload_json", "TEXT", 0),
        ("diff_hash", "TEXT", 0),
        ("state", "TEXT", 0),
        ("actor", "TEXT", 0),
        ("event_id", "INTEGER", 0),
    ],
    "settings": [
        ("key", "TEXT", 1),
        ("value_json", "TEXT", 0),
    ],
}

# (table, column, allowed values). Every column is nullable, so a row needs only the column under test.
VALUE_SETS = [
    ("intents", "state", ("draft", "dispatching", "sent", "unknown", "closed_unsent")),
    ("intents", "kind", ("routine_request", "sensitive_request", "quote_packet", "decline_notice")),
    (
        "approvals",
        "item_kind",
        ("draft", "observation", "delivery_unknown", "no_contact_route", "review"),
    ),
    ("approvals", "decision", ("approved", "rejected")),
    ("runs", "status", ("processing", "settled")),
    ("proposals", "kind", ("rule_change", "command")),
    ("proposals", "state", ("open", "applied", "dismissed")),
    ("blockers", "owner", ("underwriter", "producer", "data_team")),
    ("leads", "status", ("received", "triaged", "in_progress", "quote_sent", "declined")),
    (
        "blockers",
        "kind",
        (
            "delivery_unknown",
            "underwriter_question",
            "underwriter_review",
            "data",
            "producer_reply",
        ),
    ),
    (
        "observations",
        "source",
        ("submitted", "fetched", "derived", "assumed", "reply", "underwriter"),
    ),
    ("observations", "status", ("accepted", "pending_review", "rejected")),
    ("events", "mode", ("live", "replay", "record")),
    ("runs", "mode", ("live", "replay", "record")),
]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "uwh.db"))


def test_opened_database_has_exactly_the_a1_tables(db: sqlite3.Connection) -> None:
    names = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert names == set(EXPECTED_TABLES)


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_table_has_exactly_the_a1_columns_in_order(db: sqlite3.Connection, table: str) -> None:
    actual = [(r[1], r[2], r[5]) for r in db.execute(f"PRAGMA table_info({table})")]
    assert actual == EXPECTED_TABLES[table]


@pytest.mark.parametrize(("table", "column", "allowed"), VALUE_SETS)
def test_store_accepts_each_allowed_value_and_refuses_others(
    db: sqlite3.Connection, table: str, column: str, allowed: tuple[str, ...]
) -> None:
    for value in allowed:
        db.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (value,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"INSERT INTO {table} ({column}) VALUES (?)", ("not_a_value",))
    count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert count == len(allowed)


def test_events_refuse_update_and_delete(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE events SET type = 'x' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM events WHERE id = 1")
    assert db.execute("SELECT id, type FROM events").fetchall() == [(1, "run_started")]


@pytest.mark.parametrize("verb", ["INSERT OR REPLACE INTO", "REPLACE INTO"])
def test_events_refuse_replacement_of_an_existing_id(db: sqlite3.Connection, verb: str) -> None:
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute(f"{verb} events (id, type) VALUES (1, 'other')")
    assert db.execute("SELECT id, type FROM events").fetchall() == [(1, "run_started")]


def test_events_take_new_and_generated_ids_and_refuse_a_duplicate_id(
    db: sqlite3.Connection,
) -> None:
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    db.execute("INSERT OR REPLACE INTO events (id, type) VALUES (2, 'lead_received')")
    db.execute("INSERT INTO events (type) VALUES ('auto_id')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO events (id, type) VALUES (1, 'duplicate')")
    assert db.execute("SELECT id, type FROM events ORDER BY id").fetchall() == [
        (1, "run_started"),
        (2, "lead_received"),
        (3, "auto_id"),
    ]


def test_other_tables_stay_updatable_and_deletable(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO blockers (id, lead_id) VALUES (1, 'a')")
    db.execute("UPDATE blockers SET lead_id = 'b' WHERE id = 1")
    db.execute("DELETE FROM blockers WHERE id = 1")
    assert db.execute("SELECT COUNT(*) FROM blockers").fetchone()[0] == 0


def test_reopening_keeps_rows(tmp_path: Path) -> None:
    path = str(tmp_path / "uwh.db")
    first = open_store(path)
    first.execute("INSERT INTO leads (lead_id, status) VALUES ('L1', 'received')")
    first.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    first.commit()
    first.close()
    second = open_store(path)
    assert second.execute("SELECT lead_id, status FROM leads").fetchall() == [("L1", "received")]
    assert second.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_recreating_events_restores_the_append_only_triggers(db: sqlite3.Connection) -> None:
    db.execute("DROP TABLE events")
    create_tables(db, ["events"])
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE events SET type = 'x' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM events WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("INSERT OR REPLACE INTO events (id, type) VALUES (1, 'x')")
    assert db.execute("SELECT id, type FROM events").fetchall() == [(1, "run_started")]


def test_recreating_every_table_but_settings_leaves_settings_rows(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO settings (key, value_json) VALUES ('autonomy.fetch_data', '\"review\"')"
    )
    db.execute("INSERT INTO leads (lead_id) VALUES ('L1')")
    names = [t for t in EXPECTED_TABLES if t != "settings"]
    for name in names:
        db.execute(f"DROP TABLE {name}")
    create_tables(db, names)
    assert db.execute("SELECT key, value_json FROM settings").fetchall() == [
        ("autonomy.fetch_data", '"review"')
    ]
    assert db.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0
    db.execute("INSERT INTO events (id, type) VALUES (1, 'run_started')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM events WHERE id = 1")
