# ABOUTME: Fixtures for the sending tests: a database with one in-progress lead, Stand's mailbox in process behind a client with an unarmed fault plan, and an event context clock that advances on every call.
# ABOUTME: The constants of that lead and the ruleset are in helpers.py; the mailbox is emptied before each test, since Stand's in-process mailbox keeps one database for the whole session.
import sqlite3
from pathlib import Path

import httpx2
import pytest

from tests.runtime.helpers import (
    LEAD_ID,
    PLAN_HASH,
    REVISION,
    MakeContext,
    insert_run,
    ticking_context,
)
from uwh.runtime.faults import FaultPlan
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store


@pytest.fixture
def store_path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def store(store_path: str) -> sqlite3.Connection:
    """A database with the current run and the lead `LEAD_ID`, `in_progress` at `REVISION` with a plan."""
    db = open_store(store_path)
    insert_run(db)
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
def make_context() -> MakeContext:
    return ticking_context()
