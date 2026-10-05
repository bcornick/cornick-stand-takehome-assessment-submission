# ABOUTME: The lead workflow of 7.1 and A.3: lead rows, status transitions, a lead's ordered steps with at most one data blocker on failure, re-evaluation on a changed revision, the settled run of A.5 and the bounded lead pool of A.10.
# ABOUTME: The steps arrive as an ordered sequence; each step runs in one unit of work, an explicit transaction on the lead's own connection that nests as a savepoint inside a caller's transaction.
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

from uwh.runtime.event_types import BlockerDetail, EventType, LeadReceived, Status
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.facts import LedgerRules, ReplyValue, RevisionChange, observe_reply
from uwh.runtime.store import open_store
from uwh.runtime.waits import Blocker, close_blocker, open_blocker, open_blockers
from uwh.skills.vertical import TERMINAL_STATUSES, TRANSITIONS

# A.10: lead concurrency.
MAX_LEADS_IN_FLIGHT = 4

# The statuses of a lead whose first pass has not completed: `in_progress` means a pass has run
# every step (A.3), so a lead still `received` or `triaged` has a step to run.
_FIRST_PASS_STATUSES: tuple[Status, ...] = ("received", "triaged")


@dataclass(frozen=True)
class Step:
    """One workflow step of a lead. `run` acts on the lead through the ledger, the waits and the other
    runtime modules. It runs inside one unit of work that `run_steps` opens and commits, so it neither
    opens its own nor commits, and it leaves the posting of a message to the send primitive.
    """

    name: str
    run: Callable[[sqlite3.Connection, EventContext, str], None]


@contextmanager
def unit_of_work(db: sqlite3.Connection) -> Iterator[None]:
    """One explicit transaction: `BEGIN IMMEDIATE` and commit, or roll back when the body raises.

    Taking the write lock at the start means the body's reads and writes cannot race another lead's;
    a second writer waits for the lock (the busy timeout `open_store` sets). Inside an open
    transaction it is a savepoint instead, released on success and rolled back on a raise, and the outer transaction
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
    `declined` when a packet or a decline notice is sent. Raises ValueError, writing nothing, for a
    move outside the table.
    """
    current = _status(db, lead_id)
    if (current, target) not in TRANSITIONS:
        raise ValueError(f"a lead cannot move from {current} to {target}")
    db.execute("UPDATE leads SET status = ? WHERE lead_id = ?", (target, lead_id))


# What a step-failure `data` blocker says resumes the lead; it is how the blocker is told apart from
# the other `data` blockers (7.1).
_STEP_FAILURE_RESUME_TRIGGER = "the cause is fixed and the lead is evaluated again"


def _step_failure_blockers(db: sqlite3.Connection, lead_id: str) -> list[Blocker]:
    return [
        blocker
        for blocker in open_blockers(db, lead_id)
        if blocker.kind == "data" and blocker.detail.resume_trigger == _STEP_FAILURE_RESUME_TRIGGER
    ]


def _open_step_failure_blocker(
    db: sqlite3.Connection, context: EventContext, lead_id: str, step: Step, error: Exception
) -> None:
    """A lead holds at most one open step-failure blocker, so a repeat failure opens no second one."""
    if _step_failure_blockers(db, lead_id):
        return
    open_blocker(
        db,
        context,
        lead_id,
        "data",
        "data_team",
        BlockerDetail(
            resume_trigger=_STEP_FAILURE_RESUME_TRIGGER,
            text=f"Step {step.name} failed: {type(error).__name__}: {error}",
        ),
    )


def run_steps(
    db: sqlite3.Connection,
    make_context: Callable[[], EventContext],
    lead_id: str,
    steps: Sequence[Step],
) -> None:
    """Run the steps in order, each to completion before the next, in one unit of work per step.

    The unit of a step also holds the status move after it: `received` to `triaged` when the first
    step completes, and `in_progress` (A.3) when the last does, so a lead whose pass was cut short is
    still `received` or `triaged`. `make_context` builds the context of each unit's events.

    A step that raises rolls its unit back, the lead's remaining steps do not run and a `data`
    blocker naming the step is opened in a unit of its own (7.1, 8). A pass that runs every step
    closes the lead's step-failure blocker. Inside a caller's transaction a unit is a savepoint, so
    the rollback and the blocker leave the caller's own writes to commit (A.11).
    """
    for position, step in enumerate(steps):
        try:
            with unit_of_work(db):
                step.run(db, make_context(), lead_id)
                if _status(db, lead_id) == "received":
                    transition(db, lead_id, "triaged")
                if position == len(steps) - 1:
                    transition(db, lead_id, "in_progress")
        except Exception as error:
            with unit_of_work(db):
                _open_step_failure_blocker(db, make_context(), lead_id, step, error)
            return
    with unit_of_work(db):
        for blocker in _step_failure_blockers(db, lead_id):
            close_blocker(db, make_context(), blocker.id)


def reevaluate(
    db: sqlite3.Connection,
    make_context: Callable[[], EventContext],
    lead_id: str,
    steps: Sequence[Step],
    change: RevisionChange,
) -> None:
    """Run every step again when `change` moved the revision; a terminal lead is not evaluated again.

    Every skill reads facts (8), so the whole sequence runs, on a lead that is `received` or `triaged`
    as on an `in_progress` one. The command layer calls this in the transaction of the command, where
    a failing step rolls back to its savepoint and opens the step-failure blocker, and the command's
    own writes commit.
    """
    if not change.changed or _status(db, lead_id) in TERMINAL_STATUSES:
        return
    run_steps(db, make_context, lead_id, steps)


def record_reply(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    values: Sequence[ReplyValue],
    rules: LedgerRules,
    *,
    round_closed: bool,
    intent_id: str,
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
            intent_id=intent_id,
            review_cause="reply_after_terminal_status",
        )
    return observe_reply(
        db, context, lead_id, values, rules, round_closed=round_closed, intent_id=intent_id
    )


def run_is_settled(db: sqlite3.Connection, run_id: str) -> bool:
    """True when no lead of the run has a runnable step (A.5). A lead has one when it is `received` or
    `triaged` and holds no open blocker; an `in_progress` lead has completed a pass and a terminal
    lead has finished. Call it when no lead's steps are executing, after `run_leads`."""
    placeholders = ", ".join("?" for _ in _FIRST_PASS_STATUSES)
    row = db.execute(
        f"SELECT 1 FROM leads WHERE run_id = ? AND status IN ({placeholders})"
        " AND NOT EXISTS (SELECT 1 FROM blockers"
        "   WHERE blockers.lead_id = leads.lead_id AND blockers.closed_event_id IS NULL)"
        " LIMIT 1",
        (run_id, *_FIRST_PASS_STATUSES),
    ).fetchone()
    return row is None


def _run_lead(
    db_path: str, make_context: Callable[[], EventContext], lead_id: str, steps: Sequence[Step]
) -> None:
    db = open_store(db_path)
    try:
        run_steps(db, make_context, lead_id, steps)
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
    themselves. A failing step is handled inside `run_steps` and does not raise here. What can still
    raise out of a lead's thread is opening the store, `make_context`, and a failure while opening
    the blocker (a database error, or the blocker refused). Every such failure is raised together, as
    an exception group whose members carry a note naming their lead, once every lead has finished.
    """
    with ThreadPoolExecutor(max_workers=MAX_LEADS_IN_FLIGHT) as pool:
        futures = {
            lead_id: pool.submit(_run_lead, db_path, make_context, lead_id, steps)
            for lead_id in lead_ids
        }
    failures: list[BaseException] = []
    for lead_id, future in futures.items():
        error = future.exception()
        if error is not None:
            error.add_note(f"lead {lead_id}")
            failures.append(error)
    if failures:
        raise BaseExceptionGroup("leads failed outside a step", failures)
