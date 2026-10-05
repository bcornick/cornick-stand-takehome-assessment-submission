# ABOUTME: The event context of a command: the current run's id and its simulated time (7.2, 7.6), or the fixed pre-run id and the reference morning when no run exists.
# ABOUTME: Reads the one `runs` row; the mode, ruleset hash and real now are passed in, since nothing here reads settings or the system clock.
import sqlite3
from datetime import datetime

from uwh.runtime.clock import sim_now
from uwh.runtime.event_types import Actor
from uwh.runtime.events import EventContext
from uwh.settings import RunMode
from uwh.skills.vertical import REFERENCE_MORNING

# The run id of an event written before any run exists (7.2).
PRE_RUN_ID = "pre-run"


def command_context(
    db: sqlite3.Connection,
    actor: Actor,
    mode: RunMode,
    ruleset_hash: str,
    real_now: datetime,
) -> EventContext:
    """The context of an event written now by `actor`: the current run's id with the simulated time
    since its start, or `PRE_RUN_ID` and the reference morning when no run exists."""
    row = db.execute("SELECT run_id, started_at FROM runs").fetchone()
    if row is None:
        run_id, simulated = PRE_RUN_ID, REFERENCE_MORNING
    else:
        run_id = row[0]
        simulated = sim_now(REFERENCE_MORNING, datetime.fromisoformat(row[1]), real_now)
    return EventContext(run_id, mode, actor, ruleset_hash, real_now, simulated)
