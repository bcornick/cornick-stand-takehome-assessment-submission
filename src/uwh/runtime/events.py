# ABOUTME: Appends events to the append-only log (7.2) and reads them back in id order; every event stores its run mode (7.7) and both timestamps (7.6).
# ABOUTME: The caller passes the context and owns the transaction; nothing here reads settings, the clock or the environment.
import json
import sqlite3
from dataclasses import dataclass, fields
from datetime import UTC, datetime

from uwh.rules.models import StrictModel
from uwh.runtime.event_types import PAYLOAD_MODELS, Actor, EventType
from uwh.settings import RunMode


def format_timestamp(moment: datetime) -> str:
    """ISO 8601 in UTC with microseconds and a `Z` suffix, for example `2026-06-29T08:00:00.000000Z`.

    The width is fixed, so stored timestamps sort as text in time order.
    """
    if moment.tzinfo is None:
        raise ValueError("a timestamp needs a time zone")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class EventContext:
    """What every event carries whatever its type: the run, its mode, who acted, the active ruleset and both clocks."""

    run_id: str
    mode: RunMode
    actor: Actor
    ruleset_hash: str
    real_ts: datetime
    sim_ts: datetime

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None or value == "":
                raise ValueError(f"an event needs {field.name}")
        for name in ("real_ts", "sim_ts"):
            if getattr(self, name).tzinfo is None:
                raise ValueError(f"{name} needs a time zone")


@dataclass(frozen=True)
class StoredEvent:
    id: int
    run_id: str
    mode: RunMode
    lead_id: str | None
    type: EventType
    payload: StrictModel
    actor: Actor
    ruleset_hash: str
    prompt_versions: dict[str, str] | None
    model_id: str | None
    request_id: str | None
    real_ts: datetime
    sim_ts: datetime


def append_event(
    db: sqlite3.Connection,
    context: EventContext,
    event_type: EventType,
    payload: StrictModel,
    *,
    lead_id: str | None = None,
    model_id: str | None = None,
    request_id: str | None = None,
    prompt_versions: dict[str, str] | None = None,
) -> int:
    """Insert one event and return its id. The caller commits.

    Raises TypeError when `payload` is not the model of `event_type`. `lead_id` is None for an event that
    belongs to no lead. `model_id`, `request_id` and `prompt_versions` are set where a model was called.
    """
    model = PAYLOAD_MODELS[event_type]
    if type(payload) is not model:
        raise TypeError(
            f"{event_type.value} takes a {model.__name__}, got {type(payload).__name__}"
        )
    cursor = db.execute(
        "INSERT INTO events (run_id, mode, lead_id, type, payload_json, actor, ruleset_hash,"
        " prompt_versions_json, model_id, request_id, real_ts, sim_ts)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            context.run_id,
            context.mode,
            lead_id,
            event_type.value,
            payload.model_dump_json(),
            context.actor,
            context.ruleset_hash,
            None if prompt_versions is None else json.dumps(prompt_versions),
            model_id,
            request_id,
            format_timestamp(context.real_ts),
            format_timestamp(context.sim_ts),
        ),
    )
    assert cursor.lastrowid is not None  # an INSERT always sets it
    return cursor.lastrowid


def read_events(db: sqlite3.Connection, *, lead_id: str | None = None) -> list[StoredEvent]:
    """Every event in id order, or the events of one lead when `lead_id` is given."""
    where, args = ("", ()) if lead_id is None else ("WHERE lead_id = ?", (lead_id,))
    rows = db.execute(
        "SELECT id, run_id, mode, lead_id, type, payload_json, actor, ruleset_hash,"
        f" prompt_versions_json, model_id, request_id, real_ts, sim_ts FROM events {where} ORDER BY id",
        args,
    ).fetchall()
    return [
        StoredEvent(
            id=row[0],
            run_id=row[1],
            mode=row[2],
            lead_id=row[3],
            type=EventType(row[4]),
            payload=PAYLOAD_MODELS[EventType(row[4])].model_validate_json(row[5]),
            actor=row[6],
            ruleset_hash=row[7],
            prompt_versions=None if row[8] is None else json.loads(row[8]),
            model_id=row[9],
            request_id=row[10],
            real_ts=datetime.fromisoformat(row[11]),
            sim_ts=datetime.fromisoformat(row[12]),
        )
        for row in rows
    ]
