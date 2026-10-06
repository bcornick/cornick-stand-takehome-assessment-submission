# ABOUTME: Tests the lead workflow of 7.1: A.3 status transitions, ordered steps with a data blocker on failure, re-evaluation of a lead that is not terminal, replies after a terminal status, the stale-run checks, the leads a restart runs again and the bounded lead pool of A.10.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and runs plain Python functions as steps; the pool tests use one connection per lead, as the runtime does.
import sqlite3
import threading
from pathlib import Path

import pytest

from tests.runtime.helpers import LEAD_ID as LEAD
from tests.runtime.helpers import MakeContext, events_of, insert_run, send_nothing
from uwh.runtime.event_types import BlockerDetail, EventType, Status
from uwh.runtime.events import EventContext, StaleRun, read_events
from uwh.runtime.facts import LedgerRules, ReplyValue, effective_facts, observe, resolve_fact
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers, primary_next_action
from uwh.runtime.workflow import (
    Step,
    StepRun,
    create_lead,
    interrupted_leads,
    reevaluate,
    record_reply,
    run_leads,
    run_steps,
    transition,
    transition_refusal,
    unit_of_work,
)

RULES = LedgerRules()
TERMINAL: list[Status] = ["quote_sent", "declined"]
ALL_STATUSES: list[Status] = ["received", "triaged", "in_progress", "quote_sent", "declined"]


@pytest.fixture
def path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def db(path: str, make_context: MakeContext) -> sqlite3.Connection:
    db = open_store(path)
    insert_run(db)
    create_lead(db, make_context(), LEAD, "web", "2026-06-29T07:00:00Z")
    db.commit()
    return db


def status_of(db: sqlite3.Connection, lead_id: str = LEAD) -> str:
    return str(db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()[0])


def set_status(db: sqlite3.Connection, status: str, lead_id: str = LEAD) -> None:
    db.execute("UPDATE leads SET status = ? WHERE lead_id = ?", (status, lead_id))
    db.commit()


def logging_step(log: list[str], name: str) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        log.append(f"{name}:{status_of(db, lead_id)}")

    return Step(name, run)


def failing_step(name: str) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    return Step(name, run)


def observing_step(key: str, value: int = 1) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, key, value, "submitted", {}, RULES)

    return Step(key, run)


def step_failure_blockers(db: sqlite3.Connection) -> list[str]:
    return [b.detail.text for b in open_blockers(db, LEAD) if b.detail.text.startswith("Step ")]


def data_blocker(db: sqlite3.Connection, context: EventContext) -> int:
    detail = BlockerDetail(resume_trigger="the provider returns", text="Provider is unavailable.")
    return open_blocker(db, context, LEAD, "data", "data_team", detail)


# ---- A.3 transitions ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "target", "allowed"),
    [
        ("received", "triaged", True),
        ("in_progress", "quote_sent", True),
        ("triaged", "declined", True),
        ("received", "in_progress", False),
        ("triaged", "received", False),
        *[(start, target, False) for start in TERMINAL for target in ALL_STATUSES],
    ],
)
def test_a_transition_follows_the_a3_table_and_a_refusal_changes_nothing(
    db: sqlite3.Connection, start: Status, target: Status, allowed: bool
) -> None:
    set_status(db, start)
    events_before = len(read_events(db))

    refusal = transition_refusal(db, LEAD, target)
    if allowed:
        assert refusal is None
        transition(db, LEAD, target)
        assert status_of(db) == target
    else:
        assert refusal == f"a lead cannot move from {start} to {target}"
        with pytest.raises(ValueError, match="cannot move"):
            transition(db, LEAD, target)
        assert status_of(db) == start
    assert len(read_events(db)) == events_before


# ---- steps in order -----------------------------------------------------------------------------


def test_a_leads_steps_run_in_order_each_sees_the_one_before_and_the_status_follows(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    seen: list[str] = []

    def writer(key: str) -> Step:
        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            seen.append(f"{key} sees {sorted(effective_facts(db, lead_id))} at {status_of(db)}")
            observe(db, context, lead_id, key, 1, "submitted", {}, RULES)

        return Step(key, run)

    run_steps(db, make_context, LEAD, [writer("a"), writer("b"), writer("c")])

    assert seen == [
        "a sees [] at received",
        "b sees ['a'] at triaged",
        "c sees ['a', 'b'] at triaged",
    ]
    assert status_of(db) == "in_progress"


def prepared_step(seen: list[str], run: StepRun | None = None) -> Step:
    """A step whose `prepare` notes whether it runs inside a transaction and hands back `run`, or a
    run that notes the same."""

    def prepare(db: sqlite3.Connection, make_context: MakeContext, lead_id: str) -> StepRun:
        seen.append(f"prepare in transaction: {db.in_transaction}")

        def default(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            seen.append(f"run in transaction: {db.in_transaction}")

        return run or default

    return Step("prepared", lambda *_: pytest.fail("run is replaced by prepare"), prepare)


def test_a_steps_prepare_runs_before_its_unit_and_the_run_it_returns_runs_inside_it(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    seen: list[str] = []

    run_steps(db, make_context, LEAD, [prepared_step(seen)])

    assert seen == ["prepare in transaction: False", "run in transaction: True"]


def test_a_steps_prepare_runs_inside_the_callers_transaction_when_there_is_one(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    seen: list[str] = []

    with unit_of_work(db):
        run_steps(db, make_context, LEAD, [prepared_step(seen)])

    assert seen == ["prepare in transaction: True", "run in transaction: True"]


def test_what_a_prepare_wrote_in_its_own_unit_stays_when_the_run_raises(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    def prepare(db: sqlite3.Connection, make_context: MakeContext, lead_id: str) -> StepRun:
        with unit_of_work(db):
            observe(db, make_context(), lead_id, "kept", 1, "submitted", {}, RULES)

        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            observe(db, context, lead_id, "lost", 1, "submitted", {}, RULES)
            raise RuntimeError("the draft failed")

        return run

    run_steps(db, make_context, LEAD, [Step("ask", lambda *_: None, prepare)])

    assert sorted(effective_facts(db, LEAD)) == ["kept"]
    assert step_failure_blockers(db) == ["Step ask failed: the draft failed"]


def test_a_prepare_that_raises_stops_the_lead_with_the_step_failure_blocker(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    def prepare(db: sqlite3.Connection, make_context: MakeContext, lead_id: str) -> StepRun:
        raise RuntimeError("no plan")

    run_steps(db, make_context, LEAD, [Step("ask", lambda *_: None, prepare)])

    assert step_failure_blockers(db) == ["Step ask failed: no plan"]


def test_a_step_that_raises_stops_the_lead_with_one_data_blocker_naming_the_step(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    seen: list[str] = []
    steps = [logging_step(seen, "triage"), failing_step("fetch_data"), logging_step(seen, "end")]

    run_steps(db, make_context, LEAD, steps)
    run_steps(db, make_context, LEAD, steps)  # a repeat failure opens no second blocker

    assert seen == ["triage:received", "triage:triaged"]
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.owner) == ("data", "data_team")
    assert blocker.detail.text == "Step fetch_data failed: provider is down"
    assert status_of(db) == "triaged"
    assert primary_next_action(db, LEAD) == blocker
    assert len(events_of(db, EventType.blocker_opened)) == 1


def test_a_completed_pass_closes_the_step_failure_blocker_and_leaves_other_blockers(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    other = data_blocker(db, make_context())
    db.commit()
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    assert len(open_blockers(db, LEAD)) == 2

    run_steps(db, make_context, LEAD, [logging_step([], "triage")])

    assert [b.id for b in open_blockers(db, LEAD)] == [other]
    assert status_of(db) == "in_progress"


def test_a_failing_step_rolls_back_all_its_writes_and_keeps_the_steps_before_it(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    def write_then_fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "year_built", 1990, "submitted", {}, RULES)
        observe(db, context, lead_id, "stories", 2, "submitted", {}, RULES)
        raise RuntimeError("after the writes")

    run_steps(
        db, make_context, LEAD, [observing_step("acreage", 2), Step("fetch", write_then_fail)]
    )

    assert sorted(effective_facts(db, LEAD)) == ["acreage"]
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    assert len(events_of(db, EventType.fact_observed)) == 1
    assert [b.kind for b in open_blockers(db, LEAD)] == ["data"]


def test_a_steps_writes_and_the_status_move_after_it_commit_together(
    path: str, db: sqlite3.Connection, make_context: MakeContext
) -> None:
    other = open_store(path)
    seen_inside: list[tuple[str, list[str]]] = []

    def write_and_look(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "acreage", 2, "submitted", {}, RULES)
        seen_inside.append((status_of(other), sorted(effective_facts(other, LEAD))))

    run_steps(db, make_context, LEAD, [Step("triage", write_and_look)])

    assert seen_inside == [("received", [])]
    assert (status_of(other), sorted(effective_facts(other, LEAD))) == ("in_progress", ["acreage"])
    other.close()


def test_a_failing_lead_does_not_touch_the_other_leads(
    path: str, db: sqlite3.Connection, make_context: MakeContext
) -> None:
    create_lead(db, make_context(), "L-2", "web", "2026-06-29T07:00:00Z")
    db.commit()

    def fail_for_first(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        if lead_id == LEAD:
            raise RuntimeError("only this lead")

    run_leads(path, make_context, [LEAD, "L-2"], [Step("triage", fail_for_first)], send_nothing)

    assert [b.kind for b in open_blockers(db, LEAD)] == ["data"]
    assert open_blockers(db, "L-2") == []
    assert (status_of(db, LEAD), status_of(db, "L-2")) == ("received", "in_progress")


# ---- re-evaluation ------------------------------------------------------------------------------


def test_an_accepted_fact_re_evaluates_the_lead_through_the_whole_sequence(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    log: list[str] = []

    def evaluate(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        fact = effective_facts(db, lead_id).get("acreage")
        log.append(f"evaluate:{None if fact is None else fact.value}")

    steps = [logging_step(log, "triage"), Step("evaluate", evaluate)]
    run_steps(db, make_context, LEAD, steps)
    resolve_fact(db, make_context(), LEAD, "acreage", 7, "the producer phoned", RULES)
    reevaluate(db, make_context, LEAD, steps)

    assert log == ["triage:received", "evaluate:None", "triage:in_progress", "evaluate:7"]


def test_a_failing_step_in_the_callers_transaction_rolls_back_the_whole_pass_and_keeps_the_callers_writes(
    path: str, db: sqlite3.Connection, make_context: MakeContext
) -> None:
    other = open_store(path)
    with unit_of_work(db):
        resolve_fact(db, make_context(), LEAD, "acreage", 7, "reason", RULES)
        reevaluate(db, make_context, LEAD, [observing_step("stories"), failing_step("evaluate")])
        assert sorted(effective_facts(other, LEAD)) == []  # nothing is committed yet

    assert sorted(effective_facts(other, LEAD)) == ["acreage"]
    assert status_of(other) == "received"
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    assert len(step_failure_blockers(other)) == 1
    other.close()


@pytest.mark.parametrize("status", TERMINAL)
def test_a_terminal_lead_is_not_re_evaluated(
    db: sqlite3.Connection, make_context: MakeContext, status: str
) -> None:
    log: list[str] = []
    set_status(db, status)

    reevaluate(db, make_context, LEAD, [logging_step(log, "triage")])

    assert log == [] and status_of(db) == status


# ---- a reply after a terminal status ------------------------------------------------------------


@pytest.mark.parametrize("status", TERMINAL)
def test_a_reply_after_a_terminal_status_is_recorded_with_a_review_and_no_status_change(
    db: sqlite3.Connection, make_context: MakeContext, status: str
) -> None:
    set_status(db, status)
    values = [ReplyValue("year_built", 1990, {})]

    record_reply(db, make_context(), LEAD, values, RULES, round_closed=False, intent_id="I-1")

    assert status_of(db) == status
    assert db.execute("SELECT value_json, status FROM observations").fetchall() == [
        ("1990", "pending_review")
    ]
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.detail.item_kind, blocker.detail.cause) == (
        "underwriter_review",
        "review",
        "reply_after_terminal_status",
    )


def test_a_reply_to_a_live_lead_follows_its_round(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    set_status(db, "in_progress")
    values = [ReplyValue("year_built", 1990, {})]

    record_reply(db, make_context(), LEAD, values, RULES, round_closed=False, intent_id="I-1")
    assert effective_facts(db, LEAD)["year_built"].value == 1990
    assert open_blockers(db, LEAD) == []

    record_reply(db, make_context(), LEAD, values, RULES, round_closed=True, intent_id="I-1")
    assert [b.detail.cause for b in open_blockers(db, LEAD)] == ["late_reply"]


# ---- a run that a start has replaced ------------------------------------------------------------


def test_a_pass_of_a_replaced_run_runs_no_step_and_opens_no_blocker(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    db.execute("UPDATE runs SET run_id = 'run-2'")
    db.commit()
    events_before = len(read_events(db))
    ran: list[str] = []

    with pytest.raises(StaleRun):
        run_steps(db, make_context, LEAD, [logging_step(ran, "triage"), failing_step("fetch")])

    assert ran == []
    assert status_of(db) == "received"
    assert open_blockers(db, LEAD) == []
    assert len(read_events(db)) == events_before


def test_a_pass_whose_run_is_replaced_after_its_first_step_runs_no_further_step(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    ran: list[str] = []

    def replace_the_run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        ran.append("first")
        db.execute("UPDATE runs SET run_id = 'run-2'")

    with pytest.raises(StaleRun):
        run_steps(
            db, make_context, LEAD, [Step("first", replace_the_run), logging_step(ran, "second")]
        )

    assert ran == ["first"]
    assert open_blockers(db, LEAD) == []


# ---- leads whose pass a restart runs again ------------------------------------------------------


def test_the_leads_a_restart_runs_again_are_received_or_triaged_with_no_blocker_or_only_a_step_failure(
    db: sqlite3.Connection, make_context: MakeContext
) -> None:
    def add_lead(lead_id: str, status: str) -> None:
        db.execute(
            "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
            " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', ?, 0)",
            (lead_id, status),
        )

    add_lead("L-triaged", "triaged")
    add_lead("L-failed", "received")
    add_lead("L-waiting", "received")
    add_lead("L-other-data", "received")
    for lead_id, status in [("L-in-progress", "in_progress"), ("L-sent", "quote_sent")]:
        add_lead(lead_id, status)
    db.commit()
    run_steps(db, make_context, "L-failed", [failing_step("fetch_data")])
    producer = BlockerDetail(resume_trigger="the producer replies", text="Waiting.")
    open_blocker(db, make_context(), "L-waiting", "producer_reply", "producer", producer)
    data = BlockerDetail(resume_trigger="the data team answers", text="A lookup is pending.")
    open_blocker(db, make_context(), "L-other-data", "data", "data_team", data)
    db.commit()

    assert interrupted_leads(db) == [LEAD, "L-triaged", "L-failed"]


# ---- the pool -----------------------------------------------------------------------------------


# Every step holds the database's write lock for its whole unit of work, so step bodies of different
# leads do not overlap. The bound of A.10 is on leads in flight: a lead is in flight from the start
# of its pass (its thread opens its connection) to the end of its last step, including while it
# waits for the lock between steps, so this test counts leads at pass level, not inside a step.
@pytest.mark.slow
def test_never_more_than_four_leads_are_in_flight_and_ten_leads_all_complete(
    path: str, db: sqlite3.Connection, make_context: MakeContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = [LEAD, *(f"L-{n}" for n in range(2, 11))]
    for lead_id in ids[1:]:
        create_lead(db, make_context(), lead_id, "web", "2026-06-29T07:00:00Z")
    db.commit()
    lock = threading.Lock()
    in_flight: set[int] = set()
    peaks: list[int] = []
    ran: dict[str, list[str]] = {lead_id: [] for lead_id in ids}
    step_names = ["fetch_data", "resolve", "evaluate", "render"]
    writes_per_step = 25

    def open_store_for_a_pass(db_path: str) -> sqlite3.Connection:
        # A lead's pass starts when its thread opens its connection.
        with lock:
            in_flight.add(threading.get_ident())
            peaks.append(len(in_flight))
        return open_store(db_path)

    monkeypatch.setattr("uwh.runtime.workflow.open_store", open_store_for_a_pass)

    def pass_step(name: str) -> Step:
        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            with lock:
                ran[lead_id].append(name)
            for number in range(writes_per_step):
                observe(db, context, lead_id, f"{name}.k{number}", number, "submitted", {}, RULES)
            if name == step_names[-1]:
                with lock:
                    in_flight.remove(threading.get_ident())

        return Step(name, run)

    run_leads(path, make_context, ids, [pass_step(name) for name in step_names], send_nothing)

    assert len(peaks) == len(ids)
    assert max(peaks) <= 4
    assert in_flight == set()
    assert all(ran[lead_id] == step_names for lead_id in ids)
    assert [status_of(db, lead_id) for lead_id in ids] == ["in_progress"] * 10
    writes = len(ids) * len(step_names) * writes_per_step
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == writes
    assert len(events_of(db, EventType.fact_observed)) == writes
    assert all(open_blockers(db, lead_id) == [] for lead_id in ids)
