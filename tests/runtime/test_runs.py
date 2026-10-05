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
from starlette.testclient import TestClient

from tests.runtime.helpers import ASKER, RULESET, RUN_START
from uwh.runtime.commands import CommandEnvironment, CommandResult, submit_command
from uwh.runtime.event_types import BlockerDetail, EventType, RunStarted
from uwh.runtime.events import EventContext, StaleRun, StoredEvent, format_timestamp, read_events
from uwh.runtime.facts import LedgerRules
from uwh.runtime.faults import FaultPlan
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import (
    PRE_RUN_ID,
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

NOW = RUN_START + timedelta(minutes=5)
SEED = 42
RECIPIENT = "producer@example.com"


@pytest.fixture
def db(store_path: str) -> sqlite3.Connection:
    return open_store(store_path)


@pytest.fixture
def env(tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient) -> CommandEnvironment:
    return CommandEnvironment(
        "replay", RULESET, LedgerRules(), (), tmp_path, lambda: NOW, mailbox, leadgen
    )


def start(db: sqlite3.Connection, env: CommandEnvironment, seed: int = SEED) -> CommandResult:
    return submit_command(db, env, "underwriter", "start_run", {"seed": seed})


def current_id(db: sqlite3.Connection) -> str:
    run = current_run(db)
    assert run is not None
    return run.run_id


def context_of_current_run(
    db: sqlite3.Connection, env: CommandEnvironment
) -> Callable[[], EventContext]:
    run = current_run(db)
    assert run is not None
    return pass_context(run, env.mode, env.ruleset_hash, env.now)


def first_pass(db: sqlite3.Connection, store_path: str, env: CommandEnvironment) -> None:
    run_first_pass(store_path, current_id(db), context_of_current_run(db, env), env.steps)


def lead_ids(db: sqlite3.Connection) -> list[str]:
    return [row[0] for row in db.execute("SELECT lead_id FROM leads ORDER BY rowid")]


def events_of(db: sqlite3.Connection, event_type: EventType) -> list[StoredEvent]:
    return [e for e in read_events(db) if e.type is event_type]


def run_status(db: sqlite3.Connection) -> str:
    run = current_run(db)
    assert run is not None
    return run.status


def schema(db: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()


# ---- the event context --------------------------------------------------------------------------


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
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-7', 42, 'replay', '2026-10-05T12:00:00.000000Z', 'processing')"
    )

    context = command_context(db, "workflow", "replay", RULESET, RUN_START + timedelta(hours=3))

    assert context.run_id == "run-7"
    assert context.sim_ts == REFERENCE_MORNING + timedelta(hours=3)
    assert context.actor == "workflow"


def test_the_pass_context_keeps_the_run_it_was_built_for(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    start(db, env)
    run = current_run(db)
    assert run is not None
    make_context = pass_context(run, "replay", RULESET, lambda: NOW + timedelta(hours=3))

    context = make_context()

    assert context.run_id == run.run_id
    assert context.actor == "workflow"
    assert context.sim_ts == REFERENCE_MORNING + timedelta(hours=3)
    assert context.real_ts == NOW + timedelta(hours=3)


# ---- a start ------------------------------------------------------------------------------------


def test_a_start_recreates_every_table_but_settings(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    ddl_before = schema(db)
    old = EventContext("old-run", "replay", "workflow", RULESET, NOW, NOW)
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('old-run', 1, 'replay', '2026-10-05T11:00:00.000000Z', 'settled')"
    )
    create_lead(db, old, "OLD-LEAD", "web", "2026-06-29T07:00:00Z")
    db.execute(
        "INSERT INTO proposals (kind, payload_json, diff_hash, state, actor, event_id)"
        " VALUES ('rule_change', '{}', 'h', 'open', 'underwriter', 1)"
    )
    db.execute("INSERT INTO settings (key, value_json) VALUES ('emergency_stop', 'true')")
    db.commit()

    # DELETE FROM events is refused by the append-only trigger, so only dropping the table works.
    result = start(db, env)

    assert result.accepted
    assert schema(db) == ddl_before
    assert db.execute("SELECT key, value_json FROM settings").fetchall() == [
        ("emergency_stop", "true")
    ]
    assert db.execute("SELECT run_id FROM runs").fetchall() == [(current_id(db),)]
    assert db.execute("SELECT count(*) FROM proposals").fetchone() == (0,)
    assert "OLD-LEAD" not in lead_ids(db)
    assert {e.run_id for e in read_events(db)} == {current_id(db)}


def test_a_start_writes_the_processing_run_its_event_and_ten_received_leads(
    db: sqlite3.Connection, env: CommandEnvironment, leadgen: LeadgenClient
) -> None:
    result = start(db, env)

    run_id = current_id(db)
    assert result.accepted
    assert result.reason is None
    assert db.execute("SELECT run_id, seed, mode, started_at, status FROM runs").fetchall() == [
        (run_id, SEED, "replay", format_timestamp(NOW), "processing")
    ]
    (started,) = events_of(db, EventType.run_started)
    assert started.id == result.event_id
    assert started.payload == RunStarted(seed=SEED, lead_count=10)
    assert (started.run_id, started.actor, started.lead_id) == (run_id, "underwriter", None)
    assert started.sim_ts == REFERENCE_MORNING
    queue = leadgen.list_leads()
    assert len(queue) == 10
    assert db.execute(
        "SELECT lead_id, run_id, source, received_at, status, revision FROM leads ORDER BY rowid"
    ).fetchall() == [
        (q["lead_id"], run_id, q["source"], q["received_at"], "received", 0) for q in queue
    ]
    received = events_of(db, EventType.lead_received)
    assert [e.lead_id for e in received] == [q["lead_id"] for q in queue]
    assert {e.run_id for e in received} == {run_id}
    assert {e.actor for e in received} == {"workflow"}
    assert db.execute(
        "SELECT count(*) FROM events WHERE actor IS NULL OR run_id IS NULL OR mode IS NULL"
        " OR ruleset_hash IS NULL OR real_ts IS NULL OR sim_ts IS NULL"
    ).fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM events").fetchone() == (11,)


def test_a_start_posts_the_queue_for_the_seed_it_names(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    start(db, env, seed=7)

    assert [lead_id[:14] for lead_id in lead_ids(db)] == ["LEAD-00000007-"] * 10
    assert db.execute("SELECT seed FROM runs").fetchone() == (7,)
    (started,) = events_of(db, EventType.run_started)
    assert started.payload == RunStarted(seed=7, lead_count=10)


def test_a_start_resets_the_mailbox(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    env.mailbox.send("BOOTSTRAP-probe", "uw@stand.com", "uw@stand.com", "Probe", "Nothing asked.")
    assert len(env.mailbox.list_for_lead("BOOTSTRAP-probe")) == 1

    start(db, env)

    assert env.mailbox.list_for_lead("BOOTSTRAP-probe") == []


def test_a_start_that_fails_leaves_the_database_as_it_was(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
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


def test_a_start_names_its_refusal_with_a_run_id_when_no_run_exists(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    result = submit_command(db, env, "assistant", "start_run", {"seed": SEED})

    assert not result.accepted
    (refused,) = events_of(db, EventType.command_refused)
    assert refused.run_id == PRE_RUN_ID
    assert current_run(db) is None


def test_a_start_whose_seed_is_not_an_integer_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    for seed in ("42", True, None):
        result = submit_command(db, env, "underwriter", "start_run", {"seed": seed})  # type: ignore[dict-item]
        assert not result.accepted
        assert "seed" in str(result.reason)
    assert current_run(db) is None
    assert lead_ids(db) == []


def test_start_while_processing_refused(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    start(db, env)
    run_id, leads = current_id(db), lead_ids(db)
    events_before = len(read_events(db))

    second = start(db, env, seed=7)

    assert not second.accepted
    assert "processing" in str(second.reason)
    (refused,) = events_of(db, EventType.command_refused)
    assert refused.id == second.event_id
    assert (refused.run_id, refused.actor) == (run_id, "underwriter")
    assert refused.payload.command_type == "start_run"  # type: ignore[attr-defined]
    assert (current_id(db), lead_ids(db)) == (run_id, leads)
    assert db.execute("SELECT seed FROM runs").fetchone() == (SEED,)
    assert len(read_events(db)) == events_before + 1


def test_a_start_after_the_run_settled_is_accepted_and_replaces_the_run(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    start(db, env)
    first_run = current_id(db)
    first_pass(db, store_path, env)

    second = start(db, env, seed=7)

    assert second.accepted
    assert current_id(db) != first_run
    assert [lead_id[:14] for lead_id in lead_ids(db)] == ["LEAD-00000007-"] * 10
    assert run_status(db) == "processing"
    assert {e.run_id for e in read_events(db)} == {current_id(db)}


# ---- the first pass -----------------------------------------------------------------------------


def test_a_pass_settles_the_run_when_no_lead_has_a_runnable_step(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    start(db, env)
    assert run_status(db) == "processing"

    first_pass(db, store_path, env)

    assert run_status(db) == "settled"
    assert {status for (status,) in db.execute("SELECT status FROM leads")} == {"received"}


def test_a_pass_runs_every_lead_of_the_run_through_the_steps_and_then_settles(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    ran: list[tuple[str, str, str]] = []

    def record(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        ran.append((lead_id, context.run_id, context.actor))

    with_steps = replace(env, steps=(Step("record", record),))
    start(db, with_steps)

    first_pass(db, store_path, with_steps)

    run_id = current_id(db)
    assert sorted(ran) == sorted((lead_id, run_id, "workflow") for lead_id in lead_ids(db))
    assert {status for (status,) in db.execute("SELECT status FROM leads")} == {"in_progress"}
    assert run_status(db) == "settled"


class PoolAbort(BaseException):
    """An exception no step handler catches, so it escapes a lead's pass."""


def test_a_failure_outside_a_step_still_settles_the_run(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
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


def test_stale_run_writes_nothing(
    db: sqlite3.Connection,
    store_path: str,
    env: CommandEnvironment,
    faults: FaultPlan,
) -> None:
    start(db, env)
    first_run = current_run(db)
    assert first_run is not None
    first_leads = lead_ids(db)
    first_pass(db, store_path, env)
    stale = pass_context(first_run, env.mode, env.ruleset_hash, env.now)
    create_draft(
        db, stale(), ASKER, first_leads[0], "routine_request", RECIPIENT, "S", "B", ["acreage"]
    )
    (intent_id,) = db.execute("SELECT id FROM intents").fetchone()
    db.commit()

    # A start replaces the run while the post of a dispatch of the first run is in flight.
    def replace_the_run() -> None:
        assert start(db, env, seed=7).accepted

    faults.hold_in_flight = replace_the_run
    with pytest.raises(StaleRun):
        dispatch(db, env.mailbox, stale, intent_id)
    faults.hold_in_flight = None

    second_run = current_id(db)
    assert second_run != first_run.run_id
    assert events_of(db, EventType.message_sent) == []
    assert {e.run_id for e in read_events(db)} == {second_run}
    events_before = len(read_events(db))

    # A pass of the first run writes nothing, and finishing does not settle the second run.
    def change_the_lead(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        db.execute("UPDATE leads SET revision = revision + 1 WHERE lead_id = ?", (lead_id,))

    with pytest.raises(BaseExceptionGroup) as raised:
        run_leads(store_path, stale, lead_ids(db), (Step("change", change_the_lead),))
    assert all(isinstance(error, StaleRun) for error in raised.value.exceptions)
    run_first_pass(store_path, first_run.run_id, stale, env.steps)

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
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    start(db, env)
    first_run = current_run(db)
    assert first_run is not None
    first_pass(db, store_path, env)
    lead_id = lead_ids(db)[0]
    stale = pass_context(first_run, env.mode, env.ruleset_hash, env.now)
    stale_connection = sqlite3.connect(store_path, factory=ReplaceRunAfterRollback)

    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    # A start replaces the run after the failed step has rolled back and before its blocker opens.
    stale_connection.after_rollback = lambda: start(db, env, seed=7)
    with pytest.raises(StaleRun):
        run_steps(stale_connection, stale, lead_id, [Step("fetch", fail)])
    stale_connection.close()

    second_run = current_id(db)
    assert second_run != first_run.run_id
    assert events_of(db, EventType.blocker_opened) == []
    assert {e.run_id for e in read_events(db)} == {second_run}
    assert db.execute("SELECT count(*) FROM blockers").fetchone() == (0,)


def test_the_dispatch_after_a_command_leaves_the_drafts_of_a_run_that_replaced_its_run(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    start(db, env)
    first_run = current_run(db)
    assert first_run is not None
    first_pass(db, store_path, env)
    lead_id = lead_ids(db)[0]
    committing = sqlite3.connect(store_path, factory=ReplaceRunAfterCommit)

    # A start is accepted between the command's commit and its dispatch; the second run holds a draft
    # for the lead of the same id.
    def start_the_second_run() -> None:
        assert start(db, env).accepted
        assert lead_ids(db)[0] == lead_id
        run = current_run(db)
        assert run is not None
        create_draft(
            db,
            pass_context(run, env.mode, env.ruleset_hash, env.now)(),
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
    payload = {"lead_id": lead_id, "key": "acreage", "value": 3, "reason": "the producer called"}
    result = submit_command(committing, env, "underwriter", "resolve_fact", payload)
    committing.close()

    assert result.accepted
    assert current_id(db) != first_run.run_id
    assert db.execute("SELECT state FROM intents").fetchall() == [("draft",)]
    assert env.mailbox.list_for_lead(lead_id) == []


def test_a_command_whose_dispatch_finds_its_run_replaced_is_still_accepted(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment, faults: FaultPlan
) -> None:
    start(db, env)
    first_run = current_run(db)
    assert first_run is not None
    first_pass(db, store_path, env)
    lead_id = lead_ids(db)[0]
    stale = pass_context(first_run, env.mode, env.ruleset_hash, env.now)
    create_draft(db, stale(), ASKER, lead_id, "routine_request", RECIPIENT, "S", "B", ["acreage"])
    db.commit()

    # A start replaces the run while the command's dispatch has the post of the first run's draft in flight.
    def replace_the_run() -> None:
        assert start(db, env, seed=7).accepted

    faults.hold_in_flight = replace_the_run
    payload = {"lead_id": lead_id, "key": "acreage", "value": 3, "reason": "the producer called"}
    result = submit_command(db, env, "underwriter", "resolve_fact", payload)
    faults.hold_in_flight = None

    assert result.accepted
    assert current_id(db) != first_run.run_id
    assert events_of(db, EventType.message_sent) == []


# ---- a restart ----------------------------------------------------------------------------------


def test_startup_settles_interrupted_run(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
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

    resume_after_restart(
        store_path, env.mailbox, env.mode, env.ruleset_hash, env.now, with_steps.steps
    )

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


def test_a_restart_with_no_run_does_nothing(
    db: sqlite3.Connection, store_path: str, env: CommandEnvironment
) -> None:
    resume_after_restart(store_path, env.mailbox, env.mode, env.ruleset_hash, env.now, env.steps)

    assert current_run(db) is None
    assert read_events(db) == []
