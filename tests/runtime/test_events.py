# ABOUTME: Tests that an appended event carries its context in the A.1 columns, is refused when a required value is missing, and reads back in id order.
# ABOUTME: Each test opens a real database through open_store; the append-only triggers are the store's, exercised here through the same connection.
import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from uwh.runtime.event_types import EventType, LeadReceived, RunStarted, SettingChanged
from uwh.runtime.events import EventContext, append_event, format_timestamp, read_events
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


def test_appended_event_carries_every_context_column(db: sqlite3.Connection) -> None:
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


def test_event_without_a_model_call_or_lead_stores_null_for_those_columns(
    db: sqlite3.Connection,
) -> None:
    append_event(
        db, context(), EventType.run_started, RunStarted(seed=7, lead_count=3), lead_id=None
    )
    row = db.execute(
        "SELECT lead_id, model_id, request_id, prompt_versions_json FROM events"
    ).fetchone()
    assert row == (None, None, None, None)


@pytest.mark.parametrize("mode", ["live", "replay", "record"])
def test_mode_is_stored_on_the_event(db: sqlite3.Connection, mode: str) -> None:
    append_event(db, context(mode=mode), EventType.lead_received, received(), lead_id="L-1")
    assert db.execute("SELECT mode FROM events").fetchone() == (mode,)


@pytest.mark.parametrize("field", ["run_id", "mode", "actor", "ruleset_hash", "real_ts", "sim_ts"])
def test_a_missing_context_value_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        context(**{field: None})


@pytest.mark.parametrize("field", ["run_id", "mode", "actor", "ruleset_hash"])
def test_an_empty_context_value_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        context(**{field: ""})


@pytest.mark.parametrize("field", ["real_ts", "sim_ts"])
def test_a_timestamp_without_a_time_zone_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        context(**{field: datetime(2026, 6, 29, 8, 0)})


def test_an_event_without_lead_id_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError, match="lead_id"):
        append_event(db, context(), EventType.lead_received, received())  # type: ignore[call-arg]
    assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_a_payload_of_the_wrong_model_for_its_type_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError, match="lead_received"):
        append_event(
            db, context(), EventType.lead_received, RunStarted(seed=1, lead_count=1), lead_id="L-1"
        )
    assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_timestamps_are_utc_fixed_width_and_sort_as_text() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert (
        format_timestamp(datetime(2026, 6, 29, 10, 0, tzinfo=plus_two))
        == "2026-06-29T08:00:00.000000Z"
    )
    whole_second = datetime(2026, 6, 29, 8, 0, 1, tzinfo=UTC)
    one_microsecond_later = datetime(2026, 6, 29, 8, 0, 1, 1, tzinfo=UTC)
    assert format_timestamp(whole_second) < format_timestamp(one_microsecond_later)
    with pytest.raises(ValueError, match="time zone"):
        format_timestamp(datetime(2026, 6, 29, 8, 0))


def test_append_does_not_commit(tmp_path: Path) -> None:
    path = str(tmp_path / "app.db")
    writer = open_store(path)
    append_event(writer, context(), EventType.lead_received, received(), lead_id="L-1")
    assert open_store(path).execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
    writer.commit()
    assert open_store(path).execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


def test_events_read_back_in_id_order_with_typed_payloads(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA reverse_unordered_selects = ON")
    ids = [
        append_event(db, context(), EventType.lead_received, received("a"), lead_id="L-2"),
        append_event(
            db, context(), EventType.run_started, RunStarted(seed=1, lead_count=2), lead_id=None
        ),
        append_event(
            db, context(actor="underwriter"), EventType.lead_received, received("b"), lead_id="L-1"
        ),
        append_event(
            db,
            context(),
            EventType.setting_changed,
            SettingChanged(key="k", value=[1, "x"]),
            lead_id=None,
        ),
    ]
    assert ids == sorted(ids)
    events = read_events(db)
    assert [e.id for e in events] == ids
    assert [e.type for e in events] == [
        EventType.lead_received,
        EventType.run_started,
        EventType.lead_received,
        EventType.setting_changed,
    ]
    assert events[0].payload == received("a")
    assert events[3].payload == SettingChanged(key="k", value=[1, "x"])
    assert events[2].actor == "underwriter"
    assert events[2].lead_id == "L-1"
    assert events[0].real_ts == REAL
    assert events[0].sim_ts == SIM
    assert events[0].mode == "replay"
    assert events[0].run_id == "run-1"
    assert events[0].ruleset_hash == "r" * 64
    assert events[0].model_id is None
    assert events[0].prompt_versions is None


def test_read_events_for_one_lead_in_id_order(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA reverse_unordered_selects = ON")
    first = append_event(db, context(), EventType.lead_received, received("a"), lead_id="L-1")
    append_event(db, context(), EventType.lead_received, received("b"), lead_id="L-2")
    third = append_event(db, context(), EventType.lead_received, received("c"), lead_id="L-1")
    append_event(
        db, context(), EventType.run_started, RunStarted(seed=1, lead_count=2), lead_id=None
    )
    assert [e.id for e in read_events(db, lead_id="L-1")] == [first, third]
    assert read_events(db, lead_id="L-9") == []


def test_model_call_values_read_back(db: sqlite3.Connection) -> None:
    append_event(
        db, context(), EventType.lead_received, received(), lead_id="L-1",
        model_id="claude-x", request_id="req_1", prompt_versions={"a": "v1"},
    )  # fmt: skip
    (event,) = read_events(db)
    assert (event.model_id, event.request_id, event.prompt_versions) == (
        "claude-x",
        "req_1",
        {"a": "v1"},
    )


def test_an_event_appended_later_with_an_earlier_timestamp_reads_in_id_order(
    db: sqlite3.Connection,
) -> None:
    db.execute("PRAGMA reverse_unordered_selects = ON")
    first = append_event(
        db, context(real_ts=REAL, sim_ts=SIM), EventType.lead_received, received("a"), lead_id="L-1"
    )
    second = append_event(
        db, context(real_ts=REAL - timedelta(days=1), sim_ts=SIM - timedelta(days=1)),
        EventType.lead_received, received("b"), lead_id="L-1",
    )  # fmt: skip
    assert [e.id for e in read_events(db)] == [first, second]
    assert [e.id for e in read_events(db, lead_id="L-1")] == [first, second]
