# ABOUTME: The lead workflow of 7.1 and A.3: lead rows, status transitions, a lead's ordered steps with a data blocker on failure, re-evaluation on a changed revision, the settled run of A.5 and the bounded lead pool of A.10.
# ABOUTME: The steps arrive as an ordered sequence; every write goes through a unit of work, an explicit transaction on the lead's own connection that nests as a savepoint inside a caller's transaction.
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass


from uwh.runtime.event_types import BlockerDetail, EventType, LeadReceived, Status
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.facts import LedgerRules, ReplyValue, RevisionChange, observe_reply
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker
from uwh.skills.vertical import TERMINAL_STATUSES, TRANSITIONS

# A.10: lead concurrency.
MAX_LEADS_IN_FLIGHT = 4

# A lead waiting for another writer's lock waits this long before SQLite raises SQLITE_BUSY.
BUSY_TIMEOUT_MS = 30_000

# The statuses of a lead that has not yet run its steps (7.1): once a lead's steps have run it is
# `in_progress`, and from there it waits on blockers or reaches a terminal status.
_NOT_YET_EVALUATED: tuple[Status, ...] = ("received", "triaged")


class TransitionRefused(ValueError):
    """A status change outside the A.3 table."""


@dataclass(frozen=True)
class Step:
    """One workflow step of a lead. `run` acts on the lead through the ledger, the waits and the other
    runtime modules, wrapping its writes in `unit_of_work` and doing slow external calls outside it.

    `reads_facts` marks a step that depends on the lead's facts: a changed revision re-runs the steps
    from the first of them. The first step of a sequence is the triage step, which does not read facts.
    """

    name: str
    run: Callable[[sqlite3.Connection, EventContext, str], None]
    reads_facts: bool = False


@contextmanager
def unit_of_work(db: sqlite3.Connection) -> Iterator[None]:
    """One explicit transaction: `BEGIN IMMEDIATE` and commit, or roll back when the body raises.

    Taking the write lock at the start means the body's reads and writes cannot race another lead's;
    a second writer waits for the lock (`BUSY_TIMEOUT_MS`). Inside an open transaction it is a
    savepoint instead, released on success and rolled back on a raise, and the outer transaction
    stays the caller's to commit.
    """
    if db.in_transaction:
        db.execute("SAVEPOINT unit")
        try:
            yield
        except BaseException:
            db.execute("ROLLBACK TO unit")
            db.execute("RELEASE unit")
            raise
        db.execute("RELEASE unit")
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.rollback()
        raise
    db.commit()


def create_lead(
    db: sqlite3.Connection, context: EventContext, lead_id: str, source: str, received_at: str
) -> None:
    """Insert the lead as `received` at revision 0 and write `lead_received`. The caller commits.

    Raises sqlite3.IntegrityError for a lead id that exists.
    """
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES (?, ?, ?, ?, 'received', 0)",
        (lead_id, context.run_id, source, received_at),
    )
    append_event(
        db,
        context,
        EventType.lead_received,
        LeadReceived(source=source, received_at=received_at),
        lead_id=lead_id,
    )


def _status(db: sqlite3.Connection, lead_id: str) -> Status:
    row = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if row is None:
        raise ValueError(f"no lead {lead_id}")
    status: Status = row[0]
    return status


def transition(db: sqlite3.Connection, lead_id: str, target: Status) -> None:
    """Move the lead to `target` along the A.3 table. The caller commits.

    The terminal statuses are reached only here: the send primitive calls it with `quote_sent` or
    `declined` when a packet or a decline notice is sent. Raises TransitionRefused, writing nothing,
    for a move outside the table.
    """
    current = _status(db, lead_id)
    if (current, target) not in TRANSITIONS:
        raise TransitionRefused(f"a lead cannot move from {current} to {target}")
    db.execute("UPDATE leads SET status = ? WHERE lead_id = ?", (target, lead_id))


def run_steps(
    db: sqlite3.Connection, context: EventContext, lead_id: str, steps: Sequence[Step]
) -> None:
    """Run the steps in order, each to completion before the next, and stop the lead if one raises.

    The lead is `triaged` once the first step has run and `in_progress` from the first step that
    reads facts, or from the end of the sequence. A raising step leaves a `data` blocker naming it;
    the steps after it do not run and the writes of its own units of work are rolled back. A step
    that returns with a transaction it opened still open, on a connection that had none, fails.
    """
    nested = db.in_transaction
    for step in steps:
        if step.reads_facts:
            with unit_of_work(db):
                transition(db, lead_id, "in_progress")
        try:
            step.run(db, context, lead_id)
            if db.in_transaction and not nested:
                db.rollback()
                raise RuntimeError(f"{step.name} left a transaction open")
        except Exception as error:
            with unit_of_work(db):
                open_blocker(
                    db,
                    context,
                    lead_id,
                    "data",
                    "data_team",
                    BlockerDetail(
                        resume_trigger="the cause is fixed and the lead is evaluated again",
                        text=f"Step {step.name} failed: {type(error).__name__}: {error}",
                    ),
                )
            return
        if _status(db, lead_id) == "received":
            with unit_of_work(db):
                transition(db, lead_id, "triaged")
    if _status(db, lead_id) == "triaged":
        with unit_of_work(db):
            transition(db, lead_id, "in_progress")


def reevaluate(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    steps: Sequence[Step],
    change: RevisionChange,
) -> None:
    """Run the steps again from the first that reads facts, when `change` moved the revision (7.1).

    A lead that has not been triaged has its first run to come, and a terminal lead is not evaluated
    again: neither runs a step. The command layer calls this in the transaction of the command.
    """
    if not change.changed or _status(db, lead_id) in ("received", *TERMINAL_STATUSES):
        return
    first = next((i for i, step in enumerate(steps) if step.reads_facts), len(steps))
    run_steps(db, context, lead_id, steps[first:])


def record_reply(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    values: Sequence[ReplyValue],
    rules: LedgerRules,
    *,
    round_closed: bool,
) -> RevisionChange:
    """Record a reply in the ledger. A reply to a terminal lead is recorded `pending_review` and
    raises a `reply_after_terminal_status` review, and the status stays (A.3). The caller commits."""
    if _status(db, lead_id) in TERMINAL_STATUSES:
        return observe_reply(
            db,
            context,
            lead_id,
            values,
            rules,
            round_closed=True,
            review_cause="reply_after_terminal_status",
        )
    return observe_reply(db, context, lead_id, values, rules, round_closed=round_closed)


def run_is_settled(db: sqlite3.Connection, run_id: str) -> bool:
    """True when no lead of the run has a runnable step (A.5): every lead is terminal, holds an open
    blocker, or has run its steps. Call it when no lead's steps are executing, after `run_leads`."""
    placeholders = ", ".join("?" for _ in _NOT_YET_EVALUATED)
    row = db.execute(
        f"SELECT 1 FROM leads WHERE run_id = ? AND status IN ({placeholders})"
        " AND NOT EXISTS (SELECT 1 FROM blockers"
        "   WHERE blockers.lead_id = leads.lead_id AND blockers.closed_event_id IS NULL)"
        " LIMIT 1",
        (run_id, *_NOT_YET_EVALUATED),
    ).fetchone()
    return row is None


def settle_run(db: sqlite3.Connection, run_id: str) -> bool:
    """Mark the run `settled` when it is, and say whether it is. The caller commits."""
    if not run_is_settled(db, run_id):
        return False
    db.execute("UPDATE runs SET status = 'settled' WHERE run_id = ?", (run_id,))
    return True


def _run_lead(
    db_path: str, make_context: Callable[[], EventContext], lead_id: str, steps: Sequence[Step]
) -> None:
    db = open_store(db_path)
    try:
        db.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        run_steps(db, make_context(), lead_id, steps)
    finally:
        db.close()


def run_leads(
    db_path: str,
    make_context: Callable[[], EventContext],
    lead_ids: Sequence[str],
    steps: Sequence[Step],
) -> None:
    """Run every lead's steps, at most `MAX_LEADS_IN_FLIGHT` leads at once, and return when all are done.

    Each lead runs on its own thread with its own connection, so its steps never interleave with
    themselves. `make_context` builds the context of the lead's events when it starts. An exception
    outside a step, such as a database error, is raised here once every lead has finished.
    """
    with ThreadPoolExecutor(max_workers=MAX_LEADS_IN_FLIGHT) as pool:
        futures = [
            pool.submit(_run_lead, db_path, make_context, lead_id, steps) for lead_id in lead_ids
        ]
    for future in futures:
        future.result()
