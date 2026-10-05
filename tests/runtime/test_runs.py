# ABOUTME: Tests the event context of a command (7.2, 7.6): the current run's id and simulated time, and the fixed pre-run id and the reference morning when no run exists.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and reads the context back.
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from uwh.runtime.runs import PRE_RUN_ID, command_context
from uwh.runtime.store import open_store
from uwh.skills.vertical import REFERENCE_MORNING

RULESET = "r" * 64
RUN_START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "app.db"))


def start_run(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-7', 42, 'replay', '2026-10-05T12:00:00.000000Z', 'processing')"
    )


def test_with_no_run_the_context_is_pre_run_at_the_reference_morning(
    db: sqlite3.Connection,
) -> None:
    real_now = RUN_START + timedelta(hours=3)

    context = command_context(db, "underwriter", "replay", RULESET, real_now)

    assert context.run_id == PRE_RUN_ID == "pre-run"
    assert context.sim_ts == REFERENCE_MORNING
    assert context.real_ts == real_now
    assert (context.actor, context.mode, context.ruleset_hash) == ("underwriter", "replay", RULESET)


def test_with_a_run_the_context_takes_its_id_and_simulated_time(db: sqlite3.Connection) -> None:
    start_run(db)

    context = command_context(db, "workflow", "replay", RULESET, RUN_START + timedelta(hours=3))

    assert context.run_id == "run-7"
    assert context.sim_ts == REFERENCE_MORNING + timedelta(hours=3)
    assert context.actor == "workflow"
