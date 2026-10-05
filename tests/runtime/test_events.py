# ABOUTME: Tests that an appended event carries its context in the A.1 columns, is refused when a required value is missing, and reads back in id order.
# ABOUTME: Each test opens a real database through open_store; the append-only triggers are the store's, exercised here through the same connection.
import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.runtime.helpers import insert_run
from uwh.runtime.event_types import EventType, LeadReceived, RunStarted
from uwh.runtime.events import (
    EventContext,
    StaleRun,
    append_event,
    format_timestamp,
    read_events,
    require_current_run,
)
from uwh.runtime.store import open_store

REAL = datetime(2026, 10, 5, 9, 30, 15, 123456, tzinfo=UTC)
SIM = datetime(2026, 6, 29, 8, 0, 5, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "app.db"))


def context(**changes: Any) -> EventContext:
    fields: dict[str, Any] = {
        "run_id": "run-1",
        "mode": "replay",
        "actor": "workflow",
        "ruleset_hash": "r" * 64,
        "real_ts": REAL,
        "sim_ts": SIM,
    }
    return EventContext(**{**fields, **changes})


def received(source: str = "web") -> LeadReceived:
    return LeadReceived(source=source, received_at="2026-06-29T07:00:00Z")


def test_an_appended_event_carries_its_context_and_model_call_in_the_a1_columns(
    db: sqlite3.Connection,
) -> None:
    event_id = append_event(
        db,
        context(),
        EventType.lead_received,
        received(),
        lead_id="L-1",
        model_id="claude-x",
        request_id="req_1",
        prompt_versions={"read_reply": "v3"},
    )
    row = db.execute(
        "SELECT id, run_id, mode, lead_id, type, payload_json, actor, ruleset_hash,"
        " prompt_versions_json, model_id, request_id, real_ts, sim_ts FROM events"
    ).fetchone()
    assert row[0] == event_id
    assert row[1:5] == ("run-1", "replay", "L-1", "lead_received")
    assert json.loads(row[5]) == {"source": "web", "received_at": "2026-06-29T07:00:00Z"}
    assert row[6:8] == ("workflow", "r" * 64)
    assert json.loads(row[8]) == {"read_reply": "v3"}
    assert row[9:] == (
        "claude-x",
        "req_1",
        "2026-10-05T09:30:15.123456Z",
        "2026-06-29T08:00:05.000000Z",
    )


def test_events_read_back_in_id_order_with_the_context_stamped_and_typed_payloads(
    db: sqlite3.Connection,
) -> None:
    db.execute("PRAGMA reverse_unordered_selects = ON")
    first = append_event(db, context(), EventType.lead_received, received("a"), lead_id="L-1")
    run_started = RunStarted(seed=1, lead_count=2)
    second = append_event(db, context(), EventType.run_started, run_started, lead_id=None)
    # An event appended later with an earlier timestamp still reads after the one before it.
    third = append_event(
        db,
        context(actor="underwriter", real_ts=REAL - timedelta(days=1)),
        EventType.lead_received,
        received("b"),
        lead_id="L-1",
    )

    events = read_events(db)

    assert [e.id for e in events] == [first, second, third]
    assert [e.id for e in read_events(db, lead_id="L-1")] == [first, third]
    assert events[0].payload == received("a") and events[1].payload == run_started
    assert (events[0].run_id, events[0].mode, events[0].actor) == ("run-1", "replay", "workflow")
    assert (events[0].real_ts, events[0].sim_ts) == (REAL, SIM)
    assert (events[0].ruleset_hash, events[0].model_id) == ("r" * 64, None)
    assert events[2].actor == "underwriter"


def test_append_does_not_commit(tmp_path: Path) -> None:
    path = str(tmp_path / "app.db")
    writer = open_store(path)
    append_event(writer, context(), EventType.lead_received, received(), lead_id="L-1")
    assert open_store(path).execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
    writer.commit()
    assert open_store(path).execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


def test_timestamps_are_utc_fixed_width_and_sort_as_text() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert (
        format_timestamp(datetime(2026, 6, 29, 10, 0, tzinfo=plus_two))
        == "2026-06-29T08:00:00.000000Z"
    )
    whole_second = datetime(2026, 6, 29, 8, 0, 1, tzinfo=UTC)
    one_microsecond_later = datetime(2026, 6, 29, 8, 0, 1, 1, tzinfo=UTC)
    assert format_timestamp(whole_second) < format_timestamp(one_microsecond_later)


def test_only_the_current_run_is_accepted_and_any_other_run_id_is_stale(
    db: sqlite3.Connection,
) -> None:
    with pytest.raises(StaleRun, match="run-2"):
        require_current_run(db, "run-2")  # no run exists yet
    insert_run(db, "run-2")

    require_current_run(db, "run-2")
    with pytest.raises(StaleRun, match="run-1"):
        require_current_run(db, "run-1")
