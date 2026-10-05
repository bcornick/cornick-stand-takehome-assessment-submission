# ABOUTME: The run of 7.2, 7.6 and 14: the one `runs` row, what a run and its commands need from the caller, the event context of a command and of a pass, the run start that recreates the tables and ingests the queue, and the first pass and the restart recovery that settle the run.
# ABOUTME: The mode, ruleset hash and real clock arrive in the environment, since nothing here reads settings or the system clock; a pass builds its context from the run it was started for, so a replaced run is detected (14).
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from uwh.runtime.bootstrap import LEAD_COUNT
from uwh.runtime.clock import sim_now
from uwh.runtime.event_types import Actor, EventType, RunStarted, RunStatus
from uwh.runtime.events import EventContext, MakeContext, append_event, format_timestamp
from uwh.runtime.facts import LedgerRules, observe_submitted
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.send import dispatch_ready, reconcile_dispatching
from uwh.runtime.store import create_tables, open_store, table_ddl
from uwh.runtime.workflow import Step, create_lead, interrupted_leads, run_leads
from uwh.settings import RunMode
from uwh.skills.vertical import REFERENCE_MORNING

# The run id of an event written before any run exists (7.2).
PRE_RUN_ID = "pre-run"

# The tables a start recreates: every A.1 table (14).
_RUN_TABLES = list(table_ddl())


@dataclass(frozen=True)
class RunEnvironment:
    """What a run and its commands need from their caller: the run mode, the active ruleset hash, the
    ledger rules and workflow steps a pass and a re-evaluation use, the folder that holds the skills,
    the real clock, the mailbox that dispatched drafts are posted to and the leadgen service a run
    start reads."""

    mode: RunMode
    ruleset_hash: str
    ledger_rules: LedgerRules
    steps: Sequence[Step]
    skills_root: Path
    now: Callable[[], datetime]
    mailbox: MailboxClient
    leadgen: LeadgenClient


@dataclass(frozen=True)
class Run:
    """The `runs` row: the current run."""

    run_id: str
    seed: int
    started_at: datetime
    status: RunStatus


def current_run(db: sqlite3.Connection) -> Run | None:
    """The current run, or None before the first start."""
    row = db.execute("SELECT run_id, seed, started_at, status FROM runs").fetchone()
    if row is None:
        return None
    return Run(row[0], row[1], datetime.fromisoformat(row[2]), row[3])


def run_sim_now(run: Run, real_now: datetime) -> datetime:
    """The simulated time at `real_now` in the run: the reference morning plus the real time since the run started."""
    return sim_now(REFERENCE_MORNING, run.started_at, real_now)


def _context(
    run: Run, actor: Actor, mode: RunMode, ruleset_hash: str, real_now: datetime
) -> EventContext:
    return EventContext(run.run_id, mode, actor, ruleset_hash, real_now, run_sim_now(run, real_now))


def command_context(
    db: sqlite3.Connection,
    actor: Actor,
    mode: RunMode,
    ruleset_hash: str,
    real_now: datetime,
) -> EventContext:
    """The context of an event written now by `actor`: the current run's id with the simulated time
    since its start, or `PRE_RUN_ID` and the reference morning when no run exists."""
    run = current_run(db)
    if run is None:
        return EventContext(PRE_RUN_ID, mode, actor, ruleset_hash, real_now, REFERENCE_MORNING)
    return _context(run, actor, mode, ruleset_hash, real_now)


def pass_context(run: Run, env: RunEnvironment) -> MakeContext:
    """Builds the `workflow` context of each unit of a pass. It carries the id of `run` however
    long the pass takes, so the pass of a run that a start has replaced is stale (14)."""
    return lambda: _context(run, "workflow", env.mode, env.ruleset_hash, env.now())


def begin_run(
    db: sqlite3.Connection,
    context: EventContext,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    seed: int,
    rules: LedgerRules,
) -> int:
    """Start a run and return the id of its `run_started` event. The caller commits.

    Recreates every table, writes the `runs` row as `processing` with the real time
    of `context` as its start, writes `run_started`, posts the queue for `seed`, ingests its leads as
    `received`, each with `lead_received` and its submitted fields as observations, and resets the
    mailbox last, after everything that can fail has succeeded. `context` names who started the run; the leads are received by the workflow.
    A failure raises and the caller's rollback restores every table; it restores neither the mailbox
    nor the leadgen queue.
    """
    for name in _RUN_TABLES:
        db.execute(f"DROP TABLE IF EXISTS {name}")
    create_tables(db, _RUN_TABLES)
    run_id = uuid.uuid4().hex
    started = replace(context, run_id=run_id, sim_ts=REFERENCE_MORNING)
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status) VALUES (?, ?, ?, ?, 'processing')",
        (run_id, seed, started.mode, format_timestamp(started.real_ts)),
    )
    event_id = append_event(
        db,
        started,
        EventType.run_started,
        RunStarted(seed=seed, lead_count=LEAD_COUNT),
        lead_id=None,
    )
    leadgen.post_queue(seed, count=LEAD_COUNT)
    received = replace(started, actor="workflow")
    for lead in leadgen.list_leads():
        create_lead(db, received, lead["lead_id"], lead["source"], lead["received_at"])
        fields = leadgen.get_lead(lead["lead_id"])["fields"]
        observe_submitted(db, received, lead["lead_id"], fields, rules)
    mailbox.reset()
    return event_id


@contextmanager
def _settling(db_path: str, run_id: str) -> Iterator[None]:
    """Mark the run `settled` when the body ends, however it ends, so a failure in a pass cannot
    leave the run `processing`. A run that a start has replaced is not touched."""
    try:
        yield
    finally:
        with closing(open_store(db_path)) as db:
            db.execute("UPDATE runs SET status = 'settled' WHERE run_id = ?", (run_id,))
            db.commit()


def run_passes(
    db_path: str,
    make_context: MakeContext,
    lead_ids: Sequence[str],
    steps: Sequence[Step],
    mailbox: MailboxClient,
) -> None:
    """Run each lead through the steps, then send the drafts its pass built that can go (7.5)."""
    run_leads(
        db_path,
        make_context,
        lead_ids,
        steps,
        lambda db, lead_id: dispatch_ready(db, mailbox, make_context, lead_id),
    )


def run_first_pass(
    db_path: str,
    run_id: str,
    make_context: MakeContext,
    steps: Sequence[Step],
    mailbox: MailboxClient,
) -> None:
    """Run every lead of the run through the steps and send what each pass built, then mark the run
    `settled`: no lead has a runnable step once each has had its pass. Raises what `run_leads` raises,
    after settling."""
    with _settling(db_path, run_id):
        with closing(open_store(db_path)) as db:
            lead_ids = [
                lead_id
                for (lead_id,) in db.execute(
                    "SELECT lead_id FROM leads WHERE run_id = ? ORDER BY rowid", (run_id,)
                )
            ]
        run_passes(db_path, make_context, lead_ids, steps, mailbox)


def resume_after_restart(db_path: str, env: RunEnvironment) -> None:
    """Startup (7.1, 7.5): reconcile the intents in `dispatching`, run again the pass of every lead
    that `interrupted_leads` names, then mark the run `settled` so that a new run can start. Every
    other lead keeps its state. Does nothing before the first start. A reconciliation that fails
    raises and leaves the run as it was."""
    with closing(open_store(db_path)) as db:
        run = current_run(db)
        if run is None:
            return
        make_context = pass_context(run, env)
        reconcile_dispatching(db, env.mailbox, make_context)
        lead_ids = interrupted_leads(db)
    with _settling(db_path, run.run_id):
        run_passes(db_path, make_context, lead_ids, env.steps, env.mailbox)
