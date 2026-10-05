# ABOUTME: Tests the lead workflow of 7.1: A.3 status transitions, ordered steps with a data blocker on failure, re-evaluation on a changed revision, the settled run of A.5, replies after a terminal status and the bounded lead pool of A.10.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and runs plain Python functions as steps; the pool tests use one connection per lead, as the runtime does.
import itertools
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pytest

from uwh.runtime.event_types import EventType, LeadReceived, Status
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.facts import (
    LedgerRules,
    ReplyValue,
    RevisionChange,
    effective_facts,
    observe,
    resolve_fact,
)
from uwh.runtime.store import open_store
from uwh.runtime.waits import close_blocker, open_blockers, primary_next_action
from uwh.runtime.workflow import (
    MAX_LEADS_IN_FLIGHT,
    Step,
    TransitionRefused,
    create_lead,
    reevaluate,
    record_reply,
    run_is_settled,
    run_leads,
    run_steps,
    settle_run,
    transition,
    unit_of_work,
)
from uwh.skills.vertical import TERMINAL_STATUSES, TRANSITIONS

NOW = datetime(2026, 6, 29, 8, 0, 0, tzinfo=UTC)
CONTEXT = EventContext("run-1", "replay", "workflow", "r" * 64, NOW, NOW)
RULES = LedgerRules()
LEAD = "L-1"


def make_context() -> EventContext:
    return CONTEXT


@pytest.fixture
def path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def db(path: str) -> sqlite3.Connection:
    db = open_store(path)
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-1', 42, 'replay', '2026-06-29T08:00:00Z', 'processing')"
    )
    create_lead(db, CONTEXT, LEAD, "web", "2026-06-29T07:00:00Z")
    db.commit()
    return db


def status_of(db: sqlite3.Connection, lead_id: str = LEAD) -> str:
    return str(db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()[0])


def set_status(db: sqlite3.Connection, status: str, lead_id: str = LEAD) -> None:
    db.execute("UPDATE leads SET status = ? WHERE lead_id = ?", (status, lead_id))
    db.commit()


def logging_step(log: list[str], name: str, *, reads_facts: bool = False) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        log.append(f"{name}:{status_of(db, lead_id)}")

    return Step(name, run, reads_facts)


def failing_step(name: str) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    return Step(name, run)


# ---- lead rows ----------------------------------------------------------------------------------


def test_creating_a_lead_inserts_a_received_row_and_writes_lead_received(
    db: sqlite3.Connection,
) -> None:
    row = db.execute(
        "SELECT run_id, source, received_at, status, revision FROM leads WHERE lead_id = ?",
        (LEAD,),
    ).fetchone()
    assert row == ("run-1", "web", "2026-06-29T07:00:00Z", "received", 0)
    (event,) = read_events(db, lead_id=LEAD)
    assert event.type is EventType.lead_received
    assert event.payload == LeadReceived(source="web", received_at="2026-06-29T07:00:00Z")
    assert event.actor == "workflow"


def test_creating_a_lead_twice_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        create_lead(db, CONTEXT, LEAD, "web", "2026-06-29T07:00:00Z")


# ---- A.3 transitions ------------------------------------------------------------------------------


@pytest.mark.parametrize(("start", "target"), list(itertools.product(get_args(Status), repeat=2)))
def test_a_transition_succeeds_exactly_along_the_a3_table_and_a_refusal_writes_nothing(
    db: sqlite3.Connection, start: Status, target: Status
) -> None:
    set_status(db, start)
    events_before = len(read_events(db))
    if (start, target) in TRANSITIONS:
        transition(db, LEAD, target)
        assert status_of(db) == target
    else:
        with pytest.raises(TransitionRefused):
            transition(db, LEAD, target)
        assert status_of(db) == start
    assert len(read_events(db)) == events_before


def test_the_a3_table_lets_in_progress_reenter_itself_and_ends_at_the_terminal_statuses() -> None:
    assert ("in_progress", "in_progress") in TRANSITIONS
    assert {start for start, _ in TRANSITIONS}.isdisjoint(TERMINAL_STATUSES)


def test_a_transition_for_an_unknown_lead_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="no lead"):
        transition(db, "L-9", "triaged")


# ---- steps in order -----------------------------------------------------------------------------


def test_a_leads_steps_run_in_the_given_order_and_each_sees_the_one_before(
    db: sqlite3.Connection,
) -> None:
    order: list[str] = []

    def writer(key: str) -> Step:
        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            order.append(f"{key} sees {sorted(effective_facts(db, lead_id))}")
            with unit_of_work(db):
                observe(db, context, lead_id, key, 1, "submitted", {}, RULES)

        return Step(key, run)

    run_steps(db, CONTEXT, LEAD, [writer("a"), writer("b"), writer("c")])
    assert order == ["a sees []", "b sees ['a']", "c sees ['a', 'b']"]


def test_the_first_step_moves_the_lead_to_triaged_and_the_first_facts_step_to_in_progress(
    db: sqlite3.Connection,
) -> None:
    seen: list[str] = []
    steps = [
        logging_step(seen, "triage"),
        logging_step(seen, "resolve"),
        logging_step(seen, "evaluate", reads_facts=True),
        logging_step(seen, "render", reads_facts=True),
    ]
    run_steps(db, CONTEXT, LEAD, steps)
    assert seen == [
        "triage:received",
        "resolve:triaged",
        "evaluate:in_progress",
        "render:in_progress",
    ]
    assert status_of(db) == "in_progress"


def test_a_lead_that_ran_every_step_without_a_facts_step_ends_in_progress(
    db: sqlite3.Connection,
) -> None:
    run_steps(db, CONTEXT, LEAD, [logging_step([], "triage")])
    assert status_of(db) == "in_progress"


def test_a_step_that_raises_stops_the_lead_with_a_data_blocker_naming_the_step(
    db: sqlite3.Connection,
) -> None:
    seen: list[str] = []
    steps = [
        logging_step(seen, "triage"),
        failing_step("fetch_data"),
        logging_step(seen, "evaluate", reads_facts=True),
    ]
    run_steps(db, CONTEXT, LEAD, steps)
    assert seen == ["triage:received"]
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.owner) == ("data", "data_team")
    assert "fetch_data" in blocker.detail.text and "provider is down" in blocker.detail.text
    assert status_of(db) == "triaged"
    assert primary_next_action(db, LEAD) == blocker


def test_a_failing_step_rolls_back_its_own_writes_and_keeps_the_steps_before_it(
    db: sqlite3.Connection,
) -> None:
    def write_then_fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        with unit_of_work(db):
            observe(db, context, lead_id, "year_built", 1990, "submitted", {}, RULES)
            raise RuntimeError("after the write")

    def write(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        with unit_of_work(db):
            observe(db, context, lead_id, "acreage", 2, "submitted", {}, RULES)

    run_steps(db, CONTEXT, LEAD, [Step("triage", write), Step("fetch", write_then_fail)])
    assert sorted(effective_facts(db, LEAD)) == ["acreage"]
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1


def test_a_step_that_leaves_a_transaction_open_fails_instead_of_losing_its_writes(
    db: sqlite3.Connection,
) -> None:
    def forgets_the_unit(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "acreage", 2, "submitted", {}, RULES)

    run_steps(db, CONTEXT, LEAD, [Step("triage", forgets_the_unit)])
    (blocker,) = open_blockers(db, LEAD)
    assert "triage" in blocker.detail.text and "transaction" in blocker.detail.text
    assert not db.in_transaction
    assert effective_facts(db, LEAD) == {}


def test_a_failing_lead_does_not_touch_the_other_leads(path: str, db: sqlite3.Connection) -> None:
    create_lead(db, CONTEXT, "L-2", "web", "2026-06-29T07:00:00Z")
    db.commit()

    def fail_for_first(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        if lead_id == LEAD:
            raise RuntimeError("only this lead")

    run_leads(path, make_context, [LEAD, "L-2"], [Step("triage", fail_for_first)])
    assert [b.kind for b in open_blockers(db, LEAD)] == ["data"]
    assert open_blockers(db, "L-2") == []
    assert (status_of(db, LEAD), status_of(db, "L-2")) == ("received", "in_progress")


# ---- re-evaluation ------------------------------------------------------------------------------


def evaluation_steps(log: list[str]) -> list[Step]:
    def evaluate(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        fact = effective_facts(db, lead_id).get("acreage")
        log.append(f"evaluate:{None if fact is None else fact.value}")

    return [logging_step(log, "triage"), Step("evaluate", evaluate, reads_facts=True)]


def test_an_accepted_fact_re_evaluates_the_lead_from_the_first_step_that_reads_facts(
    db: sqlite3.Connection,
) -> None:
    log: list[str] = []
    steps = evaluation_steps(log)
    run_steps(db, CONTEXT, LEAD, steps)
    assert log == ["triage:received", "evaluate:None"]
    change = resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "the producer phoned", RULES)
    assert change.changed
    reevaluate(db, CONTEXT, LEAD, steps, change)
    assert log == ["triage:received", "evaluate:None", "evaluate:7"]
    assert status_of(db) == "in_progress"


def test_a_change_of_nothing_does_not_re_evaluate_the_lead(db: sqlite3.Connection) -> None:
    log: list[str] = []
    steps = evaluation_steps(log)
    run_steps(db, CONTEXT, LEAD, steps)
    reevaluate(db, CONTEXT, LEAD, steps, RevisionChange(1, 1))
    assert len(log) == 2


def test_re_evaluation_runs_in_the_callers_transaction_and_commits_nothing(
    db: sqlite3.Connection, path: str
) -> None:
    log: list[str] = []
    steps = evaluation_steps(log)
    run_steps(db, CONTEXT, LEAD, steps)
    other = open_store(path)
    with pytest.raises(RuntimeError, match="refused"):
        with unit_of_work(db):
            change = resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "reason", RULES)
            reevaluate(db, CONTEXT, LEAD, steps, change)
            assert log[-1] == "evaluate:7"
            assert effective_facts(other, LEAD) == {}
            raise RuntimeError("the command is refused after its steps ran")
    assert effective_facts(db, LEAD) == {}
    assert effective_facts(other, LEAD) == {}
    other.close()


@pytest.mark.parametrize("status", ["received", *TERMINAL_STATUSES])
def test_a_lead_that_is_not_in_flight_is_not_re_evaluated(
    db: sqlite3.Connection, status: str
) -> None:
    log: list[str] = []
    set_status(db, status)
    reevaluate(db, CONTEXT, LEAD, evaluation_steps(log), RevisionChange(0, 1))
    assert log == [] and status_of(db) == status


# ---- A.3: a reply after a terminal status ---------------------------------------------------------


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
def test_a_reply_after_a_terminal_status_is_recorded_with_a_review_and_no_status_change(
    db: sqlite3.Connection, status: str
) -> None:
    set_status(db, status)
    values = [ReplyValue("year_built", 1990, {})]
    change = record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=False)
    assert change.changed
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


def test_a_reply_to_a_live_lead_follows_its_round(db: sqlite3.Connection) -> None:
    set_status(db, "in_progress")
    values = [ReplyValue("year_built", 1990, {})]
    record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=False)
    assert effective_facts(db, LEAD)["year_built"].value == 1990
    assert open_blockers(db, LEAD) == []
    record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=True)
    assert [b.detail.cause for b in open_blockers(db, LEAD)] == ["late_reply"]


# ---- settled --------------------------------------------------------------------------------------


def add_lead(db: sqlite3.Connection, lead_id: str, status: str, *, run_id: str = "run-1") -> None:
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES (?, ?, 'web', '2026-06-29T07:00:00Z', ?, 0)",
        (lead_id, run_id, status),
    )
    db.commit()


def hold_blocker(db: sqlite3.Connection, lead_id: str) -> None:
    run_steps(db, CONTEXT, lead_id, [failing_step("fetch_data")])


def test_a_run_with_a_lead_that_has_not_run_its_steps_is_not_settled(
    db: sqlite3.Connection,
) -> None:
    assert not run_is_settled(db, "run-1")
    assert not settle_run(db, "run-1")
    assert db.execute("SELECT status FROM runs").fetchone() == ("processing",)
    set_status(db, "triaged")
    assert not run_is_settled(db, "run-1")


def test_a_run_is_settled_when_every_lead_is_terminal_blocked_or_has_run_its_steps(
    db: sqlite3.Connection,
) -> None:
    add_lead(db, "L-2", "quote_sent")
    add_lead(db, "L-3", "declined")
    add_lead(db, "L-4", "received")
    hold_blocker(db, "L-4")
    add_lead(db, "L-5", "triaged")
    run_steps(db, CONTEXT, "L-5", [logging_step([], "triage")])
    set_status(db, "in_progress")
    db.commit()
    assert run_is_settled(db, "run-1")
    assert settle_run(db, "run-1")
    db.commit()
    assert db.execute("SELECT status FROM runs").fetchone() == ("settled",)


def test_a_lead_of_another_run_does_not_keep_this_run_unsettled(db: sqlite3.Connection) -> None:
    set_status(db, "in_progress")
    add_lead(db, "L-2", "received", run_id="run-0")
    assert run_is_settled(db, "run-1")


def test_closing_the_last_blocker_of_an_unstarted_lead_makes_the_run_runnable_again(
    db: sqlite3.Connection,
) -> None:
    hold_blocker(db, LEAD)
    assert run_is_settled(db, "run-1")
    close_blocker(db, CONTEXT, open_blockers(db, LEAD)[0].id)
    assert not run_is_settled(db, "run-1")


# ---- the pool -----------------------------------------------------------------------------------


def test_run_leads_runs_every_lead_through_every_step(path: str, db: sqlite3.Connection) -> None:
    for number in range(2, 5):
        create_lead(db, CONTEXT, f"L-{number}", "web", "2026-06-29T07:00:00Z")
    db.commit()
    ids = [LEAD, "L-2", "L-3", "L-4"]
    log: list[str] = []
    lock = threading.Lock()

    def record(name: str) -> Step:
        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            with lock:
                log.append(f"{lead_id}:{name}")

        return Step(name, run)

    run_leads(path, make_context, ids, [record("triage"), record("evaluate")])
    for lead_id in ids:
        assert [entry for entry in log if entry.startswith(lead_id)] == [
            f"{lead_id}:triage",
            f"{lead_id}:evaluate",
        ]
        assert status_of(db, lead_id) == "in_progress"
    assert run_is_settled(db, "run-1")


@pytest.mark.slow
def test_never_more_than_four_leads_are_in_flight_and_ten_leads_all_complete(
    path: str, db: sqlite3.Connection
) -> None:
    ids = [LEAD, *(f"L-{n}" for n in range(2, 11))]
    for lead_id in ids[1:]:
        create_lead(db, CONTEXT, lead_id, "web", "2026-06-29T07:00:00Z")
    db.commit()
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def wait_for_a_provider(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.1)
        with lock:
            in_flight -= 1

    def write_facts(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        with unit_of_work(db):
            for number in range(5):
                observe(db, context, lead_id, f"k{number}", number, "submitted", {}, RULES)

    run_leads(
        path,
        make_context,
        ids,
        [Step("fetch_data", wait_for_a_provider), Step("write", write_facts)],
    )
    assert peak == MAX_LEADS_IN_FLIGHT == 4
    assert [status_of(db, lead_id) for lead_id in ids] == ["in_progress"] * 10
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 50
    assert len(workflow_events(db, EventType.fact_observed)) == 50
    assert all(len(effective_facts(db, lead_id)) == 5 for lead_id in ids)
    assert all(open_blockers(db, lead_id) == [] for lead_id in ids)


def workflow_events(db: sqlite3.Connection, event_type: EventType) -> list[object]:
    return [e for e in read_events(db) if e.type is event_type]
