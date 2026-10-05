# ABOUTME: Fixtures for the sending tests: a database with one in-progress lead, Stand's mailbox in process behind a client with an unarmed fault plan, and an event context clock that advances on every call.
# ABOUTME: The constants of that lead, the ruleset and the skill that drafts messages are defined here; the mailbox is emptied before each test, since Stand's in-process mailbox keeps one database for the whole session.
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from uwh.runtime.events import EventContext
from uwh.runtime.faults import FaultPlan
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.skills.manifest import SkillManifest
from uwh.skills.vertical import REFERENCE_MORNING

RUN_START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
RULESET = "r" * 64
LEAD_ID = "L-1"
PLAN_HASH = "p" * 64
REVISION = 3
# The skill that issues every send class.
ASKER = SkillManifest(
    name="asker",
    version="1",
    purpose="Drafts the messages a lead needs.",
    trigger="a fact is missing or a decision is made",
    command_classes=[
        "send_routine_request",
        "send_sensitive_request",
        "send_quote_packet",
        "send_decline_notice",
    ],
    fallback="none",
    pass_threshold=1.0,
)


@pytest.fixture
def store_path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def store(store_path: str) -> sqlite3.Connection:
    """A database with the current run and the lead `LEAD_ID`, `in_progress` at `REVISION` with a plan."""
    db = open_store(store_path)
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-1', 42, 'replay', '2026-10-05T12:00:00.000000Z', 'processing')"
    )
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision, plan_hash)"
        " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', 'in_progress', ?, ?)",
        (LEAD_ID, REVISION, PLAN_HASH),
    )
    db.commit()
    return db


@pytest.fixture
def faults() -> FaultPlan:
    return FaultPlan()


@pytest.fixture
def mailbox(stand_mailbox_client: httpx2.Client, faults: FaultPlan) -> MailboxClient:
    client = MailboxClient(stand_mailbox_client, faults)
    client.reset()
    return client


@pytest.fixture
def make_context() -> Callable[[], EventContext]:
    """Each call returns a context one second later than the call before."""
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
