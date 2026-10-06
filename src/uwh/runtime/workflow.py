# ABOUTME: The lead workflow of 7.1 and A.3: lead rows, status transitions, a lead's ordered steps with at most one data blocker on failure, re-evaluation of a lead that is not terminal, the settled run of A.5 and the bounded lead pool of A.10.
# ABOUTME: The steps arrive as an ordered sequence; each step runs in one unit of work, an explicit transaction on the lead's own connection that nests as a savepoint inside a caller's transaction, where one savepoint holds the whole pass.
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

from uwh.rules.models import ActionPlan
from uwh.runtime.event_types import BlockerDetail, EventType, LeadReceived, Status
from uwh.runtime.events import (
    EventContext,
    MakeContext,
    StaleRun,
    append_event,
    require_current_run,
)
from uwh.runtime.facts import (
    LedgerRules,
    ReplyValue,
    observe_late_reply,
    observe_reply,
)
from uwh.runtime.store import open_store
from uwh.runtime.waits import Blocker, close_blocker, open_blocker, open_blockers
from uwh.skills.vertical import TERMINAL_STATUSES, TRANSITIONS

# A.10: lead concurrency.
MAX_LEADS_IN_FLIGHT = 4

# The statuses of a lead whose first pass has not completed: `in_progress` means a pass has run
# every step (A.3), so a lead still `received` or `triaged` has not.
_FIRST_PASS_STATUSES: tuple[Status, ...] = ("received", "triaged")


@dataclass(frozen=True)
class Step:
    """One workflow step of a lead. `run` acts on the lead through the ledger, the waits and the other
    runtime modules. It runs inside a unit of work that `run_steps` opens, so it neither opens its own nor
    commits, and it leaves the posting of a message to the send primitive.
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


def is_terminal(db: sqlite3.Connection, lead_id: str) -> bool:
    """Whether the lead is `quote_sent` or `declined`. Raises ValueError for a lead that does not exist."""
    return _status(db, lead_id) in TERMINAL_STATUSES


def lead_revision_and_plan_hash(db: sqlite3.Connection, lead_id: str) -> tuple[int, str | None]:
    """The lead's revision and action-plan hash now; the hash is None until a plan exists. Raises
    ValueError for a lead that does not exist."""
    row = db.execute(
        "SELECT revision, plan_hash FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"there is no lead {lead_id}")
    return int(row[0]), row[1]


def stored_plan(db: sqlite3.Connection, lead_id: str) -> ActionPlan:
    """The action plan the lead's evaluation stored. Raises ValueError for a lead with no plan yet."""
    row = db.execute("SELECT plan_json FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if row is None or row[0] is None:
        raise ValueError(f"lead {lead_id} has no plan")
    return ActionPlan.model_validate_json(row[0])


def transition_refusal(db: sqlite3.Connection, lead_id: str, target: Status) -> str | None:
    """Why the lead cannot move to `target` along the A.3 table, or None when it can. Raises ValueError
    for a lead that does not exist."""
    current = _status(db, lead_id)
    if (current, target) not in TRANSITIONS:
        return f"a lead cannot move from {current} to {target}"
    return None


def transition(db: sqlite3.Connection, lead_id: str, target: Status) -> None:
    """Move the lead to `target` along the A.3 table. The caller commits.

    The terminal statuses are reached only here: the send primitive calls it with `quote_sent` or
    `declined` when a packet or a decline notice is sent. Raises ValueError, writing nothing, for a
    move outside the table.
    """
    refusal = transition_refusal(db, lead_id, target)
    if refusal is not None:
        raise ValueError(refusal)
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
            text=f"Step {step.name} failed: {error}",
        ),
    )


def _run_step(
    db: sqlite3.Connection,
    make_context: MakeContext,
    lead_id: str,
    step: Step,
    *,
    last: bool,
) -> None:
    """Run the step and the status moves after it. The last step also moves the lead to `in_progress`
    and closes its step-failure blocker, so a pass that ran every step leaves neither a stale status
    nor a stale blocker.

    Raises StaleRun, with nothing run or written, when the pass belongs to a replaced run."""
    context = make_context()
    require_current_run(db, context.run_id)
    step.run(db, context, lead_id)
    if _status(db, lead_id) == "received":
        transition(db, lead_id, "triaged")
    if last:
        transition(db, lead_id, "in_progress")
        for blocker in _step_failure_blockers(db, lead_id):
            close_blocker(db, make_context(), blocker.id)


def run_steps(
    db: sqlite3.Connection,
    make_context: MakeContext,
    lead_id: str,
    steps: Sequence[Step],
) -> None:
    """Run the steps in order, each to completion before the next.

    The last step's unit also moves the lead to `in_progress` (A.3) and closes its step-failure
    blocker; the first moves it from `received` to `triaged`, so a lead whose pass was cut short is
    still `received` or `triaged`. `make_context` builds the context of each unit's events.

    At top level each step is one unit of work. A step that raises rolls back its own unit, the
    remaining steps do not run and a `data` blocker naming the step opens in a unit of its own
    (7.1, 8). Inside a caller's transaction the whole pass is one savepoint: a step that raises rolls
    back every step of the pass and its status moves, the blocker opens and `run_steps` returns, so
    the caller's own writes commit (A.11).

    A pass of a run that a start has replaced raises StaleRun, from a step or from the blocker's unit,
    writes nothing and opens no blocker (14).
    """
    step: Step | None = None
    try:
        if db.in_transaction:
            with unit_of_work(db):
                for position, step in enumerate(steps):
                    _run_step(db, make_context, lead_id, step, last=position == len(steps) - 1)
        else:
            for position, step in enumerate(steps):
                with unit_of_work(db):
                    _run_step(db, make_context, lead_id, step, last=position == len(steps) - 1)
    except StaleRun:
        raise
    except Exception as error:
        if step is None:
            raise
        with unit_of_work(db):
            context = make_context()
            require_current_run(db, context.run_id)
            _open_step_failure_blocker(db, context, lead_id, step, error)


def reevaluate(
    db: sqlite3.Connection,
    make_context: MakeContext,
    lead_id: str,
    steps: Sequence[Step],
) -> None:
    """Run every step again, unless the lead is terminal. Every skill reads facts (8), so the whole
    sequence runs, on a lead that is `received` or `triaged` as on an `in_progress` one.

    The command layer calls this for every accepted command, in the command's transaction (A.11).
    """
    if is_terminal(db, lead_id):
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
) -> None:
    """Record a reply in the ledger. A reply to a terminal lead is recorded `pending_review` and
    raises a `reply_after_terminal_status` review, and the status stays (A.3). The caller commits."""
    if is_terminal(db, lead_id):
        observe_late_reply(
            db,
            context,
            lead_id,
            values,
            rules,
            intent_id=intent_id,
            cause="reply_after_terminal_status",
        )
    elif round_closed:
        observe_late_reply(
            db, context, lead_id, values, rules, intent_id=intent_id, cause="late_reply"
        )
    else:
        observe_reply(db, context, lead_id, values, rules)


def interrupted_leads(db: sqlite3.Connection) -> list[str]:
    """The leads whose pass a restart runs again (7.1): `received` or `triaged` with no open blocker,
    or only a step-failure blocker, in the order they were received. Every other lead keeps its state."""
    placeholders = ", ".join("?" for _ in _FIRST_PASS_STATUSES)
    lead_ids = [
        lead_id
        for (lead_id,) in db.execute(
            f"SELECT lead_id FROM leads WHERE status IN ({placeholders}) ORDER BY rowid",
            _FIRST_PASS_STATUSES,
        )
    ]
    return [
        lead_id
        for lead_id in lead_ids
        if len(open_blockers(db, lead_id)) == len(_step_failure_blockers(db, lead_id))
    ]


def _run_lead(
    db_path: str,
    make_context: MakeContext,
    lead_id: str,
    steps: Sequence[Step],
    after_pass: Callable[[sqlite3.Connection, str], None],
) -> None:
    db = open_store(db_path)
    try:
        run_steps(db, make_context, lead_id, steps)
        after_pass(db, lead_id)
    finally:
        db.close()


def run_leads(
    db_path: str,
    make_context: MakeContext,
    lead_ids: Sequence[str],
    steps: Sequence[Step],
    after_pass: Callable[[sqlite3.Connection, str], None],
) -> None:
    """Run every lead's steps, at most `MAX_LEADS_IN_FLIGHT` leads at once, and return when all are done.

    Each lead runs on its own thread with its own connection, so its steps never interleave with
    themselves. `after_pass` then runs on that connection, outside any transaction: the send of the
    drafts the pass built, which the workflow cannot import without a cycle. A failing step is handled inside `run_steps` and does not raise here. What can still
    raise out of a lead's thread is opening the store, `make_context`, and a failure while opening
    the blocker (a database error, or the blocker refused). Every such failure is raised together, as
    an exception group whose members carry a note naming their lead, once every lead has finished.
    """
    with ThreadPoolExecutor(max_workers=MAX_LEADS_IN_FLIGHT) as pool:
        futures = {
            lead_id: pool.submit(_run_lead, db_path, make_context, lead_id, steps, after_pass)
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
