# ABOUTME: GET /api/run and POST /api/run/start (A.5): the run's id, mode, seed, simulated time, summary counts and whether its first pass is complete, and the start that submits start_run as the underwriter.
# ABOUTME: A start returns at once while the first pass runs in the background, or after the run has settled with `wait`; `first_pass_complete` reads the run's status, which only a finished pass sets.
import sqlite3
from typing import get_args

from fastapi import APIRouter, HTTPException

from uwh.api.runtime import Runtime, RuntimeDependency
from uwh.api.views import RunSummary, RunView
from uwh.runtime.clock import sim_now
from uwh.runtime.event_types import RequestKind
from uwh.runtime.events import format_timestamp
from uwh.runtime.runs import current_run
from uwh.runtime.waits import primary_next_action
from uwh.skills.vertical import REFERENCE_MORNING

router = APIRouter()

_REQUEST_KINDS = get_args(RequestKind)


def _sent(db: sqlite3.Connection, *kinds: str) -> int:
    placeholders = ", ".join("?" for _ in kinds)
    (count,) = db.execute(
        f"SELECT count(*) FROM intents WHERE state = 'sent' AND kind IN ({placeholders})", kinds
    ).fetchone()
    return int(count)


# The `RunSummary` count that a lead counts in, by the kind of its primary next action.
_WAITING_COUNT = {
    "underwriter_review": "waiting_on_underwriter",
    "underwriter_question": "waiting_on_underwriter",
    "producer_reply": "waiting_on_producer",
    "data": "waiting_on_data",
    "delivery_unknown": "delivery_unknown",
}


def _summary(db: sqlite3.Connection) -> RunSummary:
    """The seven counts of section 11. A lead counts once among the four waiting counts, by its
    primary next action; a terminal lead has none."""
    waiting = dict.fromkeys(_WAITING_COUNT.values(), 0)
    for (lead_id,) in db.execute("SELECT lead_id FROM leads").fetchall():
        action = primary_next_action(db, lead_id)
        if action is not None:
            waiting[_WAITING_COUNT[action.kind]] += 1
    return RunSummary(
        quotes_sent=_sent(db, "quote_packet"),
        follow_ups_sent=_sent(db, *_REQUEST_KINDS),
        declines_approved=_sent(db, "decline_notice"),
        **waiting,
    )


def _run_view(db: sqlite3.Connection, runtime: Runtime) -> RunView:
    run = current_run(db)
    if run is None:
        return RunView(
            run_id=None,
            mode=runtime.env.mode,
            seed=runtime.settings.seed,
            sim_now=None,
            first_pass_complete=False,
            summary=_summary(db),
        )
    return RunView(
        run_id=run.run_id,
        mode=runtime.env.mode,
        seed=run.seed,
        sim_now=format_timestamp(sim_now(REFERENCE_MORNING, run.started_at, runtime.env.now())),
        first_pass_complete=run.status == "settled",
        summary=_summary(db),
    )


# The handlers carry no docstring: FastAPI copies one into the OpenAPI document.
@router.get("/api/run")
def get_run(runtime: RuntimeDependency) -> RunView:
    with runtime.database() as db:
        return _run_view(db, runtime)


@router.post("/api/run/start")
def start_run(runtime: RuntimeDependency, wait: bool = False) -> RunView:
    with runtime.database() as db:
        result, first_pass = runtime.submit_as_underwriter(
            db, "start_run", {"seed": runtime.settings.seed}
        )
    if not result.accepted:
        raise HTTPException(status_code=409, detail=result.reason)
    assert first_pass is not None  # an accepted start launches its first pass
    if wait and (failure := first_pass.exception()) is not None:
        raise HTTPException(status_code=500, detail="the first pass failed") from failure
    with runtime.database() as db:
        return _run_view(db, runtime)
