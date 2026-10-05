# ABOUTME: Tests the run of 7.2, 7.6 and 14: the event context of a command, a run start that recreates the tables, resets the mailbox, posts the queue and ingests ten leads, the first pass that settles the run, the stale-run rule and the restart recovery of 7.1.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and runs against Stand's leadgen and mailbox apps in process; a start goes through submit_command, as it does over HTTP.
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import JsonValue
from starlette.testclient import TestClient

from tests.runtime.helpers import (
    ASKER,
    NOW,
    RECIPIENT,
    RULESET,
    RUN_START,
    command_environment,
    events_of,
    insert_run,
)
from uwh.runtime.commands import CommandResult, submit_command
from uwh.runtime.event_types import BlockerDetail, EventType, RunStarted
from uwh.runtime.events import EventContext, StaleRun, format_timestamp, read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import (
    PRE_RUN_ID,
    RunEnvironment,
    command_context,
    current_run,
    pass_context,
    resume_after_restart,
    run_first_pass,
)
from uwh.runtime.send import create_draft, dispatch
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers
from uwh.runtime.workflow import Step, create_lead, run_leads, run_steps
from uwh.skills.vertical import REFERENCE_MORNING

SEED = 42


@pytest.fixture
def db(store_path: str) -> sqlite3.Connection:
    return open_store(store_path)


@pytest.fixture
def env(tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient) -> RunEnvironment:
    return command_environment(tmp_path, mailbox, leadgen)


def start(db: sqlite3.Connection, env: RunEnvironment, seed: int = SEED) -> CommandResult:
    return submit_command(db, env, "underwriter", "start_run", {"seed": seed})


def current_id(db: sqlite3.Connection) -> str:
    run = current_run(db)
    assert run is not None
    return run.run_id


def context_of_current_run(
    db: sqlite3.Connection, env: RunEnvironment
) -> Callable[[], EventContext]:
    run = current_run(db)
    assert run is not None
    return pass_context(run, env)


def first_pass(db: sqlite3.Connection, store_path: str, env: RunEnvironment) -> None:
    run_first_pass(store_path, current_id(db), context_of_current_run(db, env), env.steps)


def lead_ids(db: sqlite3.Connection) -> list[str]:
    return [row[0] for row in db.execute("SELECT lead_id FROM leads ORDER BY rowid")]


def run_status(db: sqlite3.Connection) -> str:
    run = current_run(db)
    assert run is not None
    return run.status


def schema(db: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()


def accept_payload(lead_id: str) -> dict[str, JsonValue]:
    return {"lead_id": lead_id, "key": "acreage", "value": 3, "reason": "the producer called"}


# ---- the event context --------------------------------------------------------------------------


def test_a_commands_context_is_pre_run_before_any_run_and_then_takes_the_runs_id_and_sim_time(
    db: sqlite3.Connection,
) -> None:
    real_now = RUN_START + timedelta(hours=3)

    before = command_context(db, "underwriter", "replay", RULESET, real_now)

    assert (before.run_id, before.sim_ts, before.real_ts) == (
        PRE_RUN_ID,
        REFERENCE_MORNING,
        real_now,
    )

    insert_run(db, "run-7")
    during = command_context(db, "workflow", "replay", RULESET, real_now)

    assert during.run_id == "run-7"
    assert during.sim_ts == REFERENCE_MORNING + timedelta(hours=3)


# ---- a start ------------------------------------------------------------------------------------


def test_a_start_recreates_every_table(db: sqlite3.Connection, env: RunEnvironment) -> None:
    ddl_before = schema(db)
    insert_run(db, "old-run", "settled")
    old = EventContext("old-run", "replay", "workflow", RULESET, NOW, NOW)
    create_lead(db, old, "OLD-LEAD", "web", "2026-06-29T07:00:00Z")
    db.execute(
        "INSERT INTO proposals (payload_json, state, actor, event_id)"
        " VALUES ('{}', 'open', 'assistant', 1)"
    )
    db.commit()

    # DELETE FROM events is refused by the append-only trigger, so only dropping the table works.
    result = start(db, env)

    assert result.accepted
    assert schema(db) == ddl_before
    assert db.execute("SELECT run_id FROM runs").fetchall() == [(current_id(db),)]
    assert db.execute("SELECT count(*) FROM proposals").fetchone() == (0,)
    assert "OLD-LEAD" not in lead_ids(db)
    assert {e.run_id for e in read_events(db)} == {current_id(db)}


def test_a_start_writes_the_processing_run_its_event_and_the_ten_leads_of_the_seed(
    db: sqlite3.Connection, env: RunEnvironment, leadgen: LeadgenClient
) -> None:
    result = start(db, env, seed=7)

    run_id = current_id(db)
    assert result.accepted and result.reason is None
    assert db.execute("SELECT run_id, seed, mode, started_at, status FROM runs").fetchall() == [
        (run_id, 7, "replay", format_timestamp(NOW), "processing")
    ]
    (started,) = events_of(db, EventType.run_started)
    assert started.id == result.event_id
    assert started.payload == RunStarted(seed=7, lead_count=10)
    assert (started.run_id, started.actor, started.lead_id) == (run_id, "underwriter", None)
    assert started.sim_ts == REFERENCE_MORNING
    queue = leadgen.list_leads()
    assert [lead["lead_id"][:14] for lead in queue] == ["LEAD-00000007-"] * 10
    assert db.execute(
        "SELECT lead_id, run_id, source, received_at, status, revision FROM leads ORDER BY rowid"
    ).fetchall() == [
        (q["lead_id"], run_id, q["source"], q["received_at"], "received", 0) for q in queue
    ]
    received = events_of(db, EventType.lead_received)
    assert [e.lead_id for e in received] == [q["lead_id"] for q in queue]
    assert {e.actor for e in received} == {"workflow"}
    assert db.execute("SELECT count(*) FROM events").fetchone() == (11,)


def test_a_start_resets_the_mailbox(db: sqlite3.Connection, env: RunEnvironment) -> None:
    env.mailbox.send("BOOTSTRAP-probe", "uw@stand.com", "uw@stand.com", "Probe", "Nothing asked.")
    assert len(env.mailbox.list_for_lead("BOOTSTRAP-probe")) == 1

    start(db, env)

    assert env.mailbox.list_for_lead("BOOTSTRAP-probe") == []


def test_a_start_that_fails_leaves_the_database_as_it_was(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    start(db, env)
    first_pass(db, store_path, env)
    ddl, run_id, leads = schema(db), current_id(db), lead_ids(db)
    env.mailbox.send(leads[0], RECIPIENT, "uw@stand.com", "S", "B")
    # A leadgen service that answers 404 to every route, so the queue cannot be posted.
    without_queue = LeadgenClient(TestClient(FastAPI(), base_url="http://leadgen"))
    broken = replace(env, leadgen=without_queue)

    with pytest.raises(httpx2.HTTPStatusError):
        start(db, broken, seed=7)

    assert (schema(db), current_id(db), lead_ids(db)) == (ddl, run_id, leads)
    assert {e.run_id for e in read_events(db)} == {run_id}
    assert len(env.mailbox.list_for_lead(leads[0])) == 1


def test_start_while_processing_refused(db: sqlite3.Connection, env: RunEnvironment) -> None:
    start(db, env)
    run_id, leads = current_id(db), lead_ids(db)
    events_before = len(read_events(db))

    second = start(db, env, seed=7)

    assert not second.accepted
    assert "processing" in str(second.reason)
    (refused,) = events_of(db, EventType.command_refused)
    assert refused.id == second.event_id
    assert (refused.run_id, refused.actor) == (run_id, "underwriter")
    assert (current_id(db), lead_ids(db)) == (run_id, leads)
    assert db.execute("SELECT seed FROM runs").fetchone() == (SEED,)
    assert len(read_events(db)) == events_before + 1


def test_a_start_after_the_run_settled_replaces_the_run(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    start(db, env)
    first_run = current_id(db)
    first_pass(db, store_path, env)

    second = start(db, env, seed=7)

    assert second.accepted
    assert current_id(db) != first_run
    assert run_status(db) == "processing"
    assert {e.run_id for e in read_events(db)} == {current_id(db)}


# ---- the first pass -----------------------------------------------------------------------------


def test_a_pass_runs_every_lead_of_the_run_through_the_steps_and_then_settles(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    ran: list[tuple[str, str, str]] = []

    def record(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        ran.append((lead_id, context.run_id, context.actor))

    with_steps = replace(env, steps=(Step("record", record),))
    start(db, with_steps)
    assert run_status(db) == "processing"

    first_pass(db, store_path, with_steps)

    run_id = current_id(db)
    assert sorted(ran) == sorted((lead_id, run_id, "workflow") for lead_id in lead_ids(db))
    assert {status for (status,) in db.execute("SELECT status FROM leads")} == {"in_progress"}
    assert run_status(db) == "settled"


class PoolAbort(BaseException):
    """An exception no step handler catches, so it escapes a lead's pass."""


def test_a_failure_outside_a_step_still_settles_the_run(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    def abort(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise PoolAbort

    failing = replace(env, steps=(Step("abort", abort),))
    start(db, failing)

    with pytest.raises(BaseExceptionGroup) as raised:
        first_pass(db, store_path, failing)

    assert raised.group_contains(PoolAbort)
    assert run_status(db) == "settled"


# ---- a run that a start has replaced ------------------------------------------------------------


def started_and_passed(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> tuple[str, list[str], Callable[[], EventContext]]:
    """A settled first run: its id, its leads and the context of a pass of that run."""
    start(db, env)
    run_id, leads = current_id(db), lead_ids(db)
    stale = context_of_current_run(db, env)
    first_pass(db, store_path, env)
    return run_id, leads, stale


def test_stale_run_writes_nothing(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment, faults: FaultPlan
) -> None:
    first_run, first_leads, stale = started_and_passed(db, store_path, env)
    intent_id = create_draft(
        db, stale(), ASKER, first_leads[0], "routine_request", RECIPIENT, "S", "B", ["acreage"]
    )
    db.commit()

    # A start replaces the run while the post of a dispatch of the first run is in flight.
    def replace_the_run() -> None:
        assert start(db, env, seed=7).accepted

    faults.hold_in_flight = replace_the_run
    with pytest.raises(StaleRun):
        dispatch(db, env.mailbox, stale, intent_id)
    faults.hold_in_flight = None

    second_run = current_id(db)
    assert second_run != first_run
    assert events_of(db, EventType.message_sent) == []
    assert {e.run_id for e in read_events(db)} == {second_run}
    events_before = len(read_events(db))

    # A pass of the first run writes nothing, and finishing does not settle the second run.
    def change_the_lead(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        db.execute("UPDATE leads SET revision = revision + 1 WHERE lead_id = ?", (lead_id,))

    with pytest.raises(BaseExceptionGroup) as raised:
        run_leads(store_path, stale, lead_ids(db), (Step("change", change_the_lead),))
    assert all(isinstance(error, StaleRun) for error in raised.value.exceptions)
    run_first_pass(store_path, first_run, stale, env.steps)

    assert db.execute("SELECT DISTINCT revision FROM leads").fetchall() == [(0,)]
    assert len(read_events(db)) == events_before
    assert run_status(db) == "processing"


class ReplaceRunAfterRollback(sqlite3.Connection):
    """A connection that runs `after_rollback`, once, when a rollback has released the write lock."""

    after_rollback: Callable[[], None] | None = None

    def rollback(self) -> None:
        super().rollback()
        action, self.after_rollback = self.after_rollback, None
        if action is not None:
            action()


class ReplaceRunAfterCommit(sqlite3.Connection):
    """A connection that runs `after_commit`, once, when a commit has released the write lock."""

    after_commit: Callable[[], None] | None = None

    def commit(self) -> None:
        super().commit()
        action, self.after_commit = self.after_commit, None
        if action is not None:
            action()


def test_a_step_failure_of_a_replaced_run_opens_no_blocker(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    first_run, leads, stale = started_and_passed(db, store_path, env)
    stale_connection = sqlite3.connect(store_path, factory=ReplaceRunAfterRollback)

    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    # A start replaces the run after the failed step has rolled back and before its blocker opens.
    stale_connection.after_rollback = lambda: start(db, env, seed=7)
    with pytest.raises(StaleRun):
        run_steps(stale_connection, stale, leads[0], [Step("fetch", fail)])
    stale_connection.close()

    second_run = current_id(db)
    assert second_run != first_run
    assert events_of(db, EventType.blocker_opened) == []
    assert {e.run_id for e in read_events(db)} == {second_run}
    assert db.execute("SELECT count(*) FROM blockers").fetchone() == (0,)


def test_the_dispatch_after_a_command_leaves_the_drafts_of_a_run_that_replaced_its_run(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    first_run, leads, _ = started_and_passed(db, store_path, env)
    lead_id = leads[0]
    committing = sqlite3.connect(store_path, factory=ReplaceRunAfterCommit)

    # A start is accepted between the command's commit and its dispatch; the second run holds a draft
    # for the lead of the same id.
    def start_the_second_run() -> None:
        assert start(db, env).accepted
        assert lead_ids(db)[0] == lead_id
        create_draft(
            db,
            context_of_current_run(db, env)(),
            ASKER,
            lead_id,
            "routine_request",
            RECIPIENT,
            "S",
            "B",
            ["acreage"],
        )
        db.commit()

    committing.after_commit = start_the_second_run
    result = submit_command(committing, env, "underwriter", "resolve_fact", accept_payload(lead_id))
    committing.close()

    assert result.accepted
    assert current_id(db) != first_run
    assert db.execute("SELECT state FROM intents").fetchall() == [("draft",)]
    assert env.mailbox.list_for_lead(lead_id) == []


# ---- a restart ----------------------------------------------------------------------------------


def test_startup_settles_interrupted_run(
    db: sqlite3.Connection, store_path: str, env: RunEnvironment
) -> None:
    seen: list[tuple[str, str]] = []
    run_statuses: list[str] = []

    def record(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        (state,) = db.execute("SELECT state FROM intents").fetchone()
        seen.append((lead_id, state))
        run_statuses.append(run_status(db))

    with_steps = replace(env, steps=(Step("record", record),))
    start(db, with_steps)
    first, failed, waiting, in_progress, declined, *rest = lead_ids(db)
    make_context = context_of_current_run(db, env)

    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    run_steps(db, make_context, failed, [Step("fetch", fail)])
    open_blocker(
        db,
        make_context(),
        waiting,
        "producer_reply",
        "producer",
        BlockerDetail(resume_trigger="the producer replies", text="Waiting."),
    )
    for lead_id, status in [
        (failed, "triaged"),
        (in_progress, "in_progress"),
        (declined, "declined"),
        *[(lead_id, "in_progress") for lead_id in rest],
    ]:
        db.execute("UPDATE leads SET status = ? WHERE lead_id = ?", (status, lead_id))
    # The process stopped after the post and before `sent` was recorded.
    intent_id = create_draft(
        db, make_context(), ASKER, in_progress, "routine_request", RECIPIENT, "S", "B", ["acreage"]
    )
    db.execute("UPDATE intents SET state = 'dispatching' WHERE id = ?", (intent_id,))
    db.commit()
    env.mailbox.send(
        in_progress, RECIPIENT, "uw@stand.com", "S", "B", {"intent_id": intent_id, "run_id": "x"}
    )

    resume_after_restart(store_path, with_steps)

    assert sorted(seen) == sorted([(first, "sent"), (failed, "sent")])
    assert run_statuses == ["processing"] * 2
    statuses = dict(db.execute("SELECT lead_id, status FROM leads").fetchall())
    assert (statuses[first], statuses[failed]) == ("in_progress", "in_progress")
    assert (statuses[waiting], statuses[in_progress], statuses[declined]) == (
        "received",
        "in_progress",
        "declined",
    )
    assert open_blockers(db, failed) == []
    assert [b.kind for b in open_blockers(db, waiting)] == ["producer_reply"]
    assert db.execute("SELECT state FROM intents").fetchone() == ("sent",)
    assert run_status(db) == "settled"
    assert start(db, with_steps, seed=7).accepted
