# ABOUTME: Tests the lead workflow of 7.1: A.3 status transitions, ordered steps with a data blocker on failure, re-evaluation on a changed revision, the settled run of A.5, replies after a terminal status and the bounded lead pool of A.10.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and runs plain Python functions as steps; the pool tests use one connection per lead, as the runtime does.
import itertools
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_args

import pytest

from uwh.runtime.event_types import BlockerDetail, EventType, LeadReceived, Status
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
from uwh.runtime.waits import close_blocker, open_blocker, open_blockers, primary_next_action
from uwh.runtime.workflow import (
    Step,
    create_lead,
    reevaluate,
    record_reply,
    run_is_settled,
    run_leads,
    run_steps,
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


def logging_step(log: list[str], name: str) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        log.append(f"{name}:{status_of(db, lead_id)}")

    return Step(name, run)


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
        with pytest.raises(ValueError, match="cannot move"):
            transition(db, LEAD, target)
        assert status_of(db) == start
    assert len(read_events(db)) == events_before


@pytest.mark.parametrize("start", ["received", "triaged", "in_progress"])
def test_a_lead_that_is_not_terminal_can_be_declined(db: sqlite3.Connection, start: Status) -> None:
    set_status(db, start)
    transition(db, LEAD, "declined")
    assert status_of(db) == "declined"


def test_the_a3_table_lets_in_progress_reenter_itself_and_ends_at_the_terminal_statuses() -> None:
    assert ("in_progress", "in_progress") in TRANSITIONS
    assert {start for start, _ in TRANSITIONS}.isdisjoint(TERMINAL_STATUSES)


def test_a_transition_for_an_unknown_lead_is_refused(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="no lead"):
        transition(db, "L-9", "triaged")


# ---- steps in order -----------------------------------------------------------------------------


def observing_step(key: str, value: int = 1) -> Step:
    def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, key, value, "submitted", {}, RULES)

    return Step(key, run)


def test_a_leads_steps_run_in_the_given_order_and_each_sees_the_one_before(
    db: sqlite3.Connection,
) -> None:
    order: list[str] = []

    def writer(key: str) -> Step:
        def run(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
            order.append(f"{key} sees {sorted(effective_facts(db, lead_id))}")
            observe(db, context, lead_id, key, 1, "submitted", {}, RULES)

        return Step(key, run)

    run_steps(db, make_context, LEAD, [writer("a"), writer("b"), writer("c")])
    assert order == ["a sees []", "b sees ['a']", "c sees ['a', 'b']"]


def test_the_lead_is_triaged_once_its_first_step_completes_and_in_progress_once_all_have(
    db: sqlite3.Connection,
) -> None:
    seen: list[str] = []
    steps = [logging_step(seen, name) for name in ("triage", "resolve", "evaluate", "render")]
    run_steps(db, make_context, LEAD, steps)
    assert seen == ["triage:received", "resolve:triaged", "evaluate:triaged", "render:triaged"]
    assert status_of(db) == "in_progress"


def test_a_lead_with_one_step_ends_in_progress(db: sqlite3.Connection) -> None:
    run_steps(db, make_context, LEAD, [logging_step([], "triage")])
    assert status_of(db) == "in_progress"


def test_a_completed_pass_on_an_in_progress_lead_leaves_it_in_progress(
    db: sqlite3.Connection,
) -> None:
    set_status(db, "in_progress")
    seen: list[str] = []
    run_steps(db, make_context, LEAD, [logging_step(seen, "a"), logging_step(seen, "b")])
    assert seen == ["a:in_progress", "b:in_progress"]
    assert status_of(db) == "in_progress"


def test_a_step_that_raises_stops_the_lead_with_a_data_blocker_naming_the_step(
    db: sqlite3.Connection,
) -> None:
    seen: list[str] = []
    steps = [
        logging_step(seen, "triage"),
        failing_step("fetch_data"),
        logging_step(seen, "evaluate"),
    ]
    run_steps(db, make_context, LEAD, steps)
    assert seen == ["triage:received"]
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.owner) == ("data", "data_team")
    assert "fetch_data" in blocker.detail.text and "provider is down" in blocker.detail.text
    assert status_of(db) == "triaged"
    assert primary_next_action(db, LEAD) == blocker


def test_a_lead_whose_first_step_fails_stays_received_and_can_be_evaluated_again(
    db: sqlite3.Connection,
) -> None:
    steps = [failing_step("triage")]
    run_steps(db, make_context, LEAD, steps)
    assert status_of(db) == "received"
    seen: list[str] = []
    change = resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "reason", RULES)
    db.commit()
    reevaluate(db, make_context, LEAD, [logging_step(seen, "triage")], change)
    assert seen == ["triage:received"]
    assert status_of(db) == "in_progress"


def test_a_failing_step_rolls_back_all_its_writes_and_keeps_the_steps_before_it(
    db: sqlite3.Connection,
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
    assert len(workflow_events(db, EventType.fact_observed)) == 1
    assert [b.kind for b in open_blockers(db, LEAD)] == ["data"]


def test_a_steps_writes_and_the_status_move_after_it_commit_together(
    path: str, db: sqlite3.Connection
) -> None:
    other = open_store(path)
    seen_inside: list[tuple[str, list[str]]] = []

    def write_and_look(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "acreage", 2, "submitted", {}, RULES)
        seen_inside.append((status_of(other), sorted(effective_facts(other, LEAD))))

    run_steps(db, make_context, LEAD, [Step("triage", write_and_look)])
    assert seen_inside == [("received", [])]
    assert (status_of(other), sorted(effective_facts(other, LEAD))) == (
        "in_progress",
        ["acreage"],
    )
    other.close()


def test_each_step_has_its_own_unit_with_its_own_context(db: sqlite3.Connection) -> None:
    ticks = itertools.count()

    def advancing_context() -> EventContext:
        moment = NOW + timedelta(minutes=next(ticks))
        return EventContext("run-1", "replay", "workflow", "r" * 64, moment, moment)

    run_steps(db, advancing_context, LEAD, [observing_step("a"), observing_step("b")])
    first, second = [e for e in read_events(db, lead_id=LEAD) if e.type is EventType.fact_observed]
    assert first.real_ts == NOW and second.real_ts == NOW + timedelta(minutes=1)
    assert first.sim_ts != second.sim_ts


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


def step_failure_blockers(db: sqlite3.Connection) -> list[str]:
    return [b.detail.text for b in open_blockers(db, LEAD) if b.detail.text.startswith("Step ")]


def test_a_repeat_failure_opens_no_second_step_failure_blocker(db: sqlite3.Connection) -> None:
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    run_steps(db, make_context, LEAD, [logging_step([], "triage"), failing_step("evaluate")])
    assert len(step_failure_blockers(db)) == 1
    assert len(workflow_events(db, EventType.blocker_opened)) == 1


def test_a_step_failure_blocker_is_opened_beside_another_data_blocker(
    db: sqlite3.Connection,
) -> None:
    open_blocker(
        db,
        CONTEXT,
        LEAD,
        "data",
        "data_team",
        BlockerDetail(resume_trigger="the provider returns", text="Provider is unavailable."),
    )
    db.commit()
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    assert len(open_blockers(db, LEAD)) == 2
    assert len(step_failure_blockers(db)) == 1


def test_a_completed_pass_closes_the_step_failure_blocker_and_leaves_other_blockers(
    db: sqlite3.Connection,
) -> None:
    other = open_blocker(
        db,
        CONTEXT,
        LEAD,
        "data",
        "data_team",
        BlockerDetail(resume_trigger="the provider returns", text="Provider is unavailable."),
    )
    db.commit()
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    run_steps(db, make_context, LEAD, [logging_step([], "triage")])
    assert [b.id for b in open_blockers(db, LEAD)] == [other]
    assert [e.type for e in read_events(db, lead_id=LEAD)][-1] is EventType.blocker_closed
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    assert len(step_failure_blockers(db)) == 1


def test_a_pass_that_fails_again_keeps_the_step_failure_blocker(db: sqlite3.Connection) -> None:
    run_steps(db, make_context, LEAD, [failing_step("triage")])
    run_steps(db, make_context, LEAD, [logging_step([], "triage"), failing_step("evaluate")])
    assert len(step_failure_blockers(db)) == 1
    assert workflow_events(db, EventType.blocker_closed) == []


# ---- re-evaluation ------------------------------------------------------------------------------


def evaluation_steps(log: list[str]) -> list[Step]:
    def evaluate(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        fact = effective_facts(db, lead_id).get("acreage")
        log.append(f"evaluate:{None if fact is None else fact.value}")

    return [logging_step(log, "triage"), Step("evaluate", evaluate)]


def test_an_accepted_fact_re_evaluates_the_lead_through_the_whole_sequence(
    db: sqlite3.Connection,
) -> None:
    log: list[str] = []
    steps = evaluation_steps(log)
    run_steps(db, make_context, LEAD, steps)
    assert log == ["triage:received", "evaluate:None"]
    change = resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "the producer phoned", RULES)
    assert change.changed
    reevaluate(db, make_context, LEAD, steps, change)
    assert log == ["triage:received", "evaluate:None", "triage:in_progress", "evaluate:7"]
    assert status_of(db) == "in_progress"


def test_a_change_of_nothing_does_not_re_evaluate_the_lead(db: sqlite3.Connection) -> None:
    log: list[str] = []
    steps = evaluation_steps(log)
    run_steps(db, make_context, LEAD, steps)
    reevaluate(db, make_context, LEAD, steps, RevisionChange(1, 1))
    assert len(log) == 2


def test_a_failing_step_in_the_callers_transaction_rolls_back_to_its_savepoint_and_the_callers_writes_commit(
    db: sqlite3.Connection, path: str
) -> None:
    run_steps(db, make_context, LEAD, [logging_step([], "triage")])
    seen_inside: list[list[str]] = []

    def write_then_fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "stories", 2, "submitted", {}, RULES)
        seen_inside.append(sorted(effective_facts(db, lead_id)))
        raise RuntimeError("the step fails")

    other = open_store(path)
    with unit_of_work(db):
        change = resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "reason", RULES)
        reevaluate(db, make_context, LEAD, [Step("evaluate", write_then_fail)], change)
        assert sorted(effective_facts(other, LEAD)) == []  # nothing is committed yet
    assert seen_inside == [["acreage", "stories"]]
    assert sorted(effective_facts(other, LEAD)) == ["acreage"]
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    (blocker,) = open_blockers(other, LEAD)
    assert (blocker.kind, blocker.owner) == ("data", "data_team")
    assert "evaluate" in blocker.detail.text and "the step fails" in blocker.detail.text
    other.close()


def test_a_failure_outside_a_step_in_the_callers_transaction_still_rolls_the_caller_back(
    db: sqlite3.Connection,
) -> None:
    with pytest.raises(RuntimeError, match="the caller fails"):
        with unit_of_work(db):
            resolve_fact(db, CONTEXT, LEAD, "acreage", 7, "reason", RULES)
            raise RuntimeError("the caller fails")
    assert effective_facts(db, LEAD) == {}


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
def test_a_terminal_lead_is_not_re_evaluated(db: sqlite3.Connection, status: str) -> None:
    log: list[str] = []
    set_status(db, status)
    reevaluate(db, make_context, LEAD, evaluation_steps(log), RevisionChange(0, 1))
    assert log == [] and status_of(db) == status


# ---- A.3: a reply after a terminal status ---------------------------------------------------------


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
def test_a_reply_after_a_terminal_status_is_recorded_with_a_review_and_no_status_change(
    db: sqlite3.Connection, status: str
) -> None:
    set_status(db, status)
    values = [ReplyValue("year_built", 1990, {})]
    change = record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=False, intent_id="I-1")
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
    record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=False, intent_id="I-1")
    assert effective_facts(db, LEAD)["year_built"].value == 1990
    assert open_blockers(db, LEAD) == []
    record_reply(db, CONTEXT, LEAD, values, RULES, round_closed=True, intent_id="I-1")
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
    run_steps(db, make_context, lead_id, [failing_step("fetch_data")])


def test_a_run_with_a_received_or_triaged_lead_that_holds_no_blocker_is_not_settled(
    db: sqlite3.Connection,
) -> None:
    assert not run_is_settled(db, "run-1")
    set_status(db, "triaged")
    assert not run_is_settled(db, "run-1")


def test_a_run_is_settled_when_every_lead_is_terminal_blocked_or_in_progress(
    db: sqlite3.Connection,
) -> None:
    add_lead(db, "L-2", "quote_sent")
    add_lead(db, "L-3", "declined")
    add_lead(db, "L-4", "received")
    hold_blocker(db, "L-4")
    add_lead(db, "L-5", "received")
    run_steps(db, make_context, "L-5", [logging_step([], "triage")])
    set_status(db, "in_progress")
    assert run_is_settled(db, "run-1")


def test_a_lead_of_another_run_does_not_keep_this_run_unsettled(db: sqlite3.Connection) -> None:
    set_status(db, "in_progress")
    add_lead(db, "L-2", "received", run_id="run-0")
    assert run_is_settled(db, "run-1")


def test_closing_the_last_blocker_of_a_first_pass_lead_leaves_a_runnable_step_that_run_steps_runs(
    db: sqlite3.Connection,
) -> None:
    hold_blocker(db, LEAD)
    assert run_is_settled(db, "run-1")
    close_blocker(db, CONTEXT, open_blockers(db, LEAD)[0].id)
    db.commit()
    assert not run_is_settled(db, "run-1")
    run_steps(db, make_context, LEAD, [logging_step([], "triage")])
    assert run_is_settled(db, "run-1")


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


def test_every_failure_outside_a_step_is_reported_after_all_leads_finish(
    tmp_path: Path, db: sqlite3.Connection
) -> None:
    create_lead(db, CONTEXT, "L-2", "web", "2026-06-29T07:00:00Z")
    db.commit()
    unopenable = str(tmp_path / "missing" / "app.db")
    with pytest.raises(ExceptionGroup) as raised:
        run_leads(unopenable, make_context, [LEAD, "L-2"], [logging_step([], "triage")])
    assert [type(e) for e in raised.value.exceptions] == [sqlite3.OperationalError] * 2
    assert [e.__notes__ for e in raised.value.exceptions] == [["lead L-1"], ["lead L-2"]]


# Every step holds the database's write lock for its whole unit of work, so step bodies of different
# leads do not overlap. The bound of A.10 is on leads in flight: a lead is in flight from the start
# of its pass (its thread opens its connection) to the end of its last step, including while it
# waits for the lock between steps, so this test counts leads at pass level, not inside a step.
@pytest.mark.slow
def test_never_more_than_four_leads_are_in_flight_and_ten_leads_all_complete(
    path: str, db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = [LEAD, *(f"L-{n}" for n in range(2, 11))]
    for lead_id in ids[1:]:
        create_lead(db, CONTEXT, lead_id, "web", "2026-06-29T07:00:00Z")
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

    run_leads(path, make_context, ids, [pass_step(name) for name in step_names])
    assert len(peaks) == len(ids)
    assert max(peaks) <= 4
    assert in_flight == set()
    assert all(ran[lead_id] == step_names for lead_id in ids)
    assert [status_of(db, lead_id) for lead_id in ids] == ["in_progress"] * 10
    writes = len(ids) * len(step_names) * writes_per_step
    assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == writes
    assert len(workflow_events(db, EventType.fact_observed)) == writes
    assert all(
        len(effective_facts(db, lead_id)) == len(step_names) * writes_per_step for lead_id in ids
    )
    assert all(open_blockers(db, lead_id) == [] for lead_id in ids)


def workflow_events(db: sqlite3.Connection, event_type: EventType) -> list[object]:
    return [e for e in read_events(db) if e.type is event_type]
