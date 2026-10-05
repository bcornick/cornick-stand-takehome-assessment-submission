# ABOUTME: Opens the application database and creates the A.1 tables, their value-set checks and the append-only triggers on events.
# ABOUTME: The vertical passes in its message kinds; the store itself fixes the other A.1 value sets (blocker owners, approval item kinds, run modes and the rest).
import sqlite3
from collections.abc import Iterable
from typing import get_args

from uwh.runtime.event_types import (
    ApprovalDecision,
    ApprovalItemKind,
    BlockerOwner,
    IntentState,
    ObservationSource,
    ObservationStatus,
    ProposalKind,
    ProposalState,
    RunStatus,
)
from uwh.settings import RUN_MODES


def _in_set(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"CHECK ({column} IN ({quoted}))"


def table_ddl(intent_kinds: Iterable[str]) -> dict[str, str]:
    """The CREATE TABLE statement of each A.1 table, by table name.

    `intent_kinds` are the message kinds the vertical registers; they constrain `intents.kind`.
    """
    return {
        "leads": """CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY, run_id TEXT, source TEXT, received_at TEXT,
            status TEXT, revision INTEGER, plan_json TEXT, plan_hash TEXT)""",
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
            {_in_set("owner", get_args(BlockerOwner))})""",
        "intents": f"""CREATE TABLE IF NOT EXISTS intents (
            id TEXT PRIMARY KEY, run_id TEXT, lead_id TEXT, round INTEGER, kind TEXT,
            recipient TEXT, subject TEXT, body TEXT, ask_ids_json TEXT, payload_hash TEXT,
            state TEXT, mailbox_id INTEGER,
            {_in_set("state", get_args(IntentState))},
            {_in_set("kind", intent_kinds)})""",
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
            id INTEGER PRIMARY KEY, kind TEXT, payload_json TEXT, diff_hash TEXT, state TEXT,
            actor TEXT, event_id INTEGER,
            {_in_set("kind", get_args(ProposalKind))},
            {_in_set("state", get_args(ProposalState))})""",
        "settings": """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value_json TEXT)""",
    }


# The event log is append-only (section 7.2): a changed or removed row raises.
EVENTS_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
       BEGIN SELECT RAISE(ABORT, 'events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
       BEGIN SELECT RAISE(ABORT, 'events is append-only'); END""",
)


def create_tables(
    db: sqlite3.Connection, names: Iterable[str], *, intent_kinds: Iterable[str]
) -> None:
    """Create the named A.1 tables if missing, and the `events` triggers whenever `events` is among them.

    Dropping `events` drops its triggers, so recreating it goes through here.
    """
    ddl = table_ddl(tuple(intent_kinds))
    chosen = list(names)
    for name in chosen:
        db.execute(ddl[name])
    if "events" in chosen:
        for trigger in EVENTS_TRIGGERS:
            db.execute(trigger)


def open_store(path: str, *, intent_kinds: Iterable[str]) -> sqlite3.Connection:
    """Open the database at `path`, creating any missing table. Existing rows are left alone."""
    kinds = tuple(intent_kinds)  # read once: a generator would be empty at the second use
    db = sqlite3.connect(path)
    create_tables(db, table_ddl(kinds), intent_kinds=kinds)
    db.commit()
    return db
