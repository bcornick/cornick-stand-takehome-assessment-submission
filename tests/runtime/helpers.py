# ABOUTME: The builders the runtime tests share: the run row, the ticking event context, the environment of a command, the skill manifest, the lead and its plan, and the intents of a stopped process.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from uwh.runtime.event_types import EventType
from uwh.runtime.events import EventContext, StoredEvent, read_events
from uwh.runtime.facts import LedgerRules
from uwh.runtime.hashing import payload_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.send import create_draft, dispatch
from uwh.runtime.workflow import Step
from uwh.skills.manifest import SkillManifest
from uwh.skills.vertical import REFERENCE_MORNING

RUN_START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
NOW = RUN_START + timedelta(minutes=5)
RULESET = "r" * 64
LEAD_ID = "L-1"
PLAN_HASH = "p" * 64
REVISION = 3
RECIPIENT = "producer@example.com"

MakeContext = Callable[[], EventContext]


def skill_manifest(*command_classes: str, name: str = "asker") -> SkillManifest:
    """A deterministic skill that declares the command classes."""
    return SkillManifest(
        name=name,
        version="1",
        purpose="Drafts the messages a lead needs.",
        trigger="a fact is missing or a decision is made",
        command_classes=list(command_classes),
        fallback="none",
        pass_threshold=1.0,
    )


# The skill that issues every send class.
ASKER = skill_manifest(
    "send_routine_request", "send_sensitive_request", "send_quote_packet", "send_decline_notice"
)


def insert_run(db: sqlite3.Connection, run_id: str = "run-1", status: str = "processing") -> None:
    """The `runs` row of the current run, started at `RUN_START`. The caller commits."""
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES (?, 42, 'replay', '2026-10-05T12:00:00.000000Z', ?)",
        (run_id, status),
    )


def ticking_context() -> MakeContext:
    """Each call of the result returns a context one second later than the call before."""
    calls = 0

    def next_context() -> EventContext:
        nonlocal calls
        calls += 1
        return EventContext(
            "run-1",
            "replay",
            "workflow",
            RULESET,
            RUN_START + timedelta(seconds=calls),
            REFERENCE_MORNING + timedelta(seconds=calls),
        )

    return next_context


def send_nothing(db: sqlite3.Connection, lead_id: str) -> None:
    """The `after_pass` of a test of the lead pool, which builds no drafts."""


def command_environment(
    tmp_path: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
    steps: Sequence[Step] = (),
    *,
    skills_root: Path | None = None,
    now: Callable[[], datetime] = lambda: NOW,
) -> RunEnvironment:
    return RunEnvironment(
        "replay", RULESET, LedgerRules(), steps, skills_root or tmp_path, now, mailbox, leadgen
    )


def events_of(db: sqlite3.Connection, event_type: EventType) -> list[StoredEvent]:
    return [e for e in read_events(db) if e.type == event_type]


def state_of(db: sqlite3.Connection, intent_id: str) -> str:
    (state,) = db.execute("SELECT state FROM intents WHERE id = ?", (intent_id,)).fetchone()
    return str(state)


def draft_and_dispatch(
    db: sqlite3.Connection,
    mailbox: MailboxClient,
    make_context: MakeContext,
    lead_id: str = LEAD_ID,
) -> str:
    """Draft a routine request, which sends at once, dispatch it and return its intent id."""
    intent_id = create_draft(
        db, make_context(), ASKER, lead_id, "routine_request", RECIPIENT, "Subject", "Body", []
    )
    db.commit()
    dispatch(db, mailbox, make_context, intent_id)
    return intent_id


def insert_dispatching(
    db: sqlite3.Connection, intent_id: str, *, round_: int, lead_id: str = LEAD_ID
) -> None:
    """An intent as a stopped process leaves it: `dispatching`, the post made or not."""
    db.execute(
        "INSERT INTO intents (id, run_id, lead_id, round, kind, recipient, subject, body,"
        " ask_ids_json, payload_hash, state, lead_revision) VALUES (?, 'run-1', ?, ?,"
        " 'routine_request', ?, 'S', 'B', '[]', ?, 'dispatching', ?)",
        (intent_id, lead_id, round_, RECIPIENT, payload_hash(RECIPIENT, "S", "B"), REVISION),
    )
    db.commit()
