# ABOUTME: Opens the application database and creates the A.1 tables, their value-set checks and the append-only triggers on events.
# ABOUTME: Every value-set check is built from the Literal types of event_types, except the run mode, which comes from settings, so the store and the event payloads share one definition of each set.
import sqlite3
from collections.abc import Iterable
from typing import get_args

from uwh.runtime.event_types import (
    ApprovalDecision,
    ApprovalItemKind,
    BlockerKind,
    BlockerOwner,
    IntentState,
    MessageKind,
    ObservationSource,
    ObservationStatus,
    ProposalState,
    RunStatus,
    Status,
)
from uwh.settings import RUN_MODES


# A connection waiting for another writer's lock waits this long before SQLite raises SQLITE_BUSY.
BUSY_TIMEOUT_MS = 30_000


def _in_set(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"CHECK ({column} IN ({quoted}))"


def table_ddl() -> dict[str, str]:
    """The CREATE TABLE statement of each A.1 table, by table name."""
    return {
        "leads": f"""CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY, run_id TEXT, source TEXT, received_at TEXT,
            status TEXT, revision INTEGER, plan_json TEXT, plan_hash TEXT,
            {_in_set("status", get_args(Status))})""",
        "events": f"""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, run_id TEXT, mode TEXT, lead_id TEXT, type TEXT,
            payload_json TEXT, actor TEXT, ruleset_hash TEXT, prompt_versions_json TEXT,
            model_id TEXT, request_id TEXT, real_ts TEXT, sim_ts TEXT,
            {_in_set("mode", RUN_MODES)})""",
        "observations": f"""CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY, lead_id TEXT, key TEXT, value_json TEXT, source TEXT,
            evidence_json TEXT, status TEXT, event_id INTEGER,
            {_in_set("source", get_args(ObservationSource))},
            {_in_set("status", get_args(ObservationStatus))})""",
        "effective_facts": """CREATE TABLE IF NOT EXISTS effective_facts (
            lead_id TEXT, key TEXT, observation_id INTEGER, confirmed INTEGER,
            PRIMARY KEY (lead_id, key))""",
        "blockers": f"""CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY, lead_id TEXT, kind TEXT, owner TEXT, detail_json TEXT,
            opened_event_id INTEGER, closed_event_id INTEGER,
            {_in_set("kind", get_args(BlockerKind))},
            {_in_set("owner", get_args(BlockerOwner))})""",
        "intents": f"""CREATE TABLE IF NOT EXISTS intents (
            id TEXT PRIMARY KEY, run_id TEXT, lead_id TEXT, round INTEGER, kind TEXT,
            recipient TEXT, subject TEXT, body TEXT, ask_ids_json TEXT, payload_hash TEXT,
            state TEXT, mailbox_id INTEGER, lead_revision INTEGER,
            {_in_set("state", get_args(IntentState))},
            {_in_set("kind", get_args(MessageKind))})""",
        "approvals": f"""CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY, lead_id TEXT, item_kind TEXT, intent_id TEXT,
            lead_revision INTEGER, plan_hash TEXT, ruleset_hash TEXT, recipient TEXT,
            payload_hash TEXT, actor TEXT, decision TEXT, reason TEXT, event_id INTEGER,
            {_in_set("item_kind", get_args(ApprovalItemKind))},
            {_in_set("decision", get_args(ApprovalDecision))})""",
        "runs": f"""CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, seed INTEGER, mode TEXT, started_at TEXT, status TEXT,
            {_in_set("mode", RUN_MODES)},
            {_in_set("status", get_args(RunStatus))})""",
        "proposals": f"""CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY, payload_json TEXT, state TEXT, actor TEXT, event_id INTEGER,
            {_in_set("state", get_args(ProposalState))})""",
    }


# The event log is append-only (section 7.2): a changed, removed or replaced row raises.
# REPLACE conflict resolution deletes the old row without firing delete triggers, so an insert
# that names an existing id raises here, before the conflict is resolved.
EVENTS_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
       BEGIN SELECT RAISE(ABORT, 'events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
       BEGIN SELECT RAISE(ABORT, 'events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS events_no_replace BEFORE INSERT ON events
       WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM events WHERE id = NEW.id)
       BEGIN SELECT RAISE(ABORT, 'events is append-only'); END""",
)


def create_tables(db: sqlite3.Connection, names: Iterable[str]) -> None:
    """Create the named A.1 tables if missing, and the `events` triggers whenever `events` is among them.

    Dropping `events` drops its triggers, so recreating it goes through here.
    """
    ddl = table_ddl()
    chosen = list(names)
    for name in chosen:
        db.execute(ddl[name])
    if "events" in chosen:
        for trigger in EVENTS_TRIGGERS:
            db.execute(trigger)


def open_store(path: str) -> sqlite3.Connection:
    """Open the database at `path`, creating any missing table. Existing rows are left alone.

    Every connection waits `BUSY_TIMEOUT_MS` for a lock held by another writer.
    """
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    create_tables(db, table_ddl())
    db.commit()
    return db
