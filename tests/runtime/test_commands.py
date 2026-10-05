# ABOUTME: Tests the command layer of 7.4 and A.11: the actor from the transport, the class rules, the skill manifest check, item resolution, one transaction per command with the lead's re-evaluation, and the handlers built so far.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and reads back events, approvals and blockers; skill folders are built under tmp_path.
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from uwh.runtime.commands import CommandEnvironment, CommandResult, submit_command
from uwh.runtime.event_types import (
    Actor,
    ApprovalRecorded,
    BlockerDetail,
    BlockerKind,
    CommandRefused,
    EventType,
    ReviewCause,
    RulingRecorded,
)
from uwh.runtime.events import EventContext, StoredEvent, read_events
from uwh.runtime.facts import LedgerRules, ReplyValue, effective_facts, observe, observe_reply
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers
from uwh.runtime.workflow import Step, create_lead
from uwh.skills.vertical import COMMAND_CLASSES, REFERENCE_MORNING

RULESET = "r" * 64
RUN_START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
NOW = RUN_START + timedelta(minutes=5)
SETUP = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
RULES = LedgerRules()
LEAD = "L-1"
PLAN_HASH = "p" * 64
ACTORS: tuple[Actor, ...] = ("workflow", "underwriter", "assistant", "mcp_client", "inbound")
HUMAN_ONLY = [c.name for c in COMMAND_CLASSES if c.actors == ("underwriter",)]


@pytest.fixture
def path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def db(path: str) -> sqlite3.Connection:
    db = open_store(path)
    db.execute(
        "INSERT INTO runs (run_id, seed, mode, started_at, status)"
        " VALUES ('run-1', 42, 'replay', '2026-10-05T12:00:00.000000Z', 'processing')"
    )
    add_lead(db, LEAD)
    return db


def add_lead(db: sqlite3.Connection, lead_id: str) -> None:
    create_lead(db, SETUP, lead_id, "web", "2026-06-29T07:00:00Z")
    db.execute("UPDATE leads SET plan_hash = ? WHERE lead_id = ?", (PLAN_HASH, lead_id))
    db.commit()


class Passes:
    """The workflow steps of the tests: one step that records the leads it ran on."""

    def __init__(self) -> None:
        self.leads: list[str] = []
        self.actors: list[str] = []
        self.steps = (Step("record", self.run),)

    def run(self, db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        self.leads.append(lead_id)
        self.actors.append(context.actor)


@pytest.fixture
def passes() -> Passes:
    return Passes()


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    folder = tmp_path / "skills" / "fetcher"
    folder.mkdir(parents=True)
    manifest = {
        "name": "fetcher",
        "version": "1",
        "purpose": "Looks up a value.",
        "trigger": "a lookup is needed",
        "command_classes": ["fetch_data"],
        "fallback": "none",
        "pass_threshold": 1.0,
    }
    (folder / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    return tmp_path / "skills"


@pytest.fixture
def env(passes: Passes, skills_root: Path) -> CommandEnvironment:
    return CommandEnvironment("replay", RULESET, RULES, passes.steps, skills_root, lambda: NOW)


def events_of(db: sqlite3.Connection, event_type: EventType) -> list[StoredEvent]:
    return [e for e in read_events(db) if e.type == event_type]


def last_refusal(db: sqlite3.Connection) -> StoredEvent:
    return events_of(db, EventType.command_refused)[-1]


def assert_refused(db: sqlite3.Connection, result: CommandResult, reason_part: str) -> None:
    assert not result.accepted
    assert result.reason is not None and reason_part in result.reason
    refusal = last_refusal(db)
    assert refusal.id == result.event_id
    assert isinstance(refusal.payload, CommandRefused)
    assert refusal.payload.reason == result.reason


def pending_observation(db: sqlite3.Connection) -> int:
    """A reply value that differs from a submitted one: pending, with its review open."""
    observe(db, SETUP, LEAD, "acreage", 2, "submitted", {}, RULES)
    observe_reply(
        db,
        SETUP,
        LEAD,
        [ReplyValue("acreage", 3, {"quote": "3 acres"})],
        RULES,
        round_closed=False,
        intent_id="i-1",
    )
    db.commit()
    (item,) = open_blockers(db, LEAD)
    assert item.detail.observation_id is not None
    return item.id


def open_item(
    db: sqlite3.Connection, detail: BlockerDetail, kind: BlockerKind = "underwriter_review"
) -> int:
    blocker_id = open_blocker(
        db,
        SETUP,
        LEAD,
        kind,
        "underwriter",
        detail,
    )
    db.commit()
    return blocker_id


def review(
    cause: ReviewCause, *, persists: bool = False, intent_id: str | None = None
) -> BlockerDetail:
    return BlockerDetail(
        item_kind="review",
        cause=cause,
        cause_persists=persists,
        resume_trigger="an underwriter decides",
        intent_id=intent_id,
        text="Needs a decision.",
    )


# ---- the actor and the class rules --------------------------------------------------------------


def test_the_actor_comes_from_the_transport_binding(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call"}

    result = submit_command(db, env, "underwriter", "resolve_fact", payload)

    assert result.accepted
    stored = [e for e in read_events(db) if e.type == EventType.fact_observed][-1]
    assert stored.actor == "underwriter"


def test_a_payload_key_named_actor_is_refused_and_writes_only_the_refusal(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    before = len(read_events(db))
    payload = {"lead_id": LEAD, "key": "acreage", "value": 2, "reason": "call", "actor": "workflow"}

    result = submit_command(db, env, "underwriter", "resolve_fact", payload)

    assert_refused(db, result, "actor")
    assert len(read_events(db)) == before + 1
    assert effective_facts(db, LEAD) == {}


@pytest.mark.parametrize("actor", [a for a in ACTORS if a != "underwriter"])
@pytest.mark.parametrize("command_type", HUMAN_ONLY)
def test_human_only_classes_refuse_every_other_actor(
    db: sqlite3.Connection, env: CommandEnvironment, actor: Actor, command_type: str
) -> None:
    result = submit_command(db, env, actor, command_type, {})

    assert_refused(db, result, f"{actor} may not submit {command_type}")


@pytest.mark.parametrize("actor", ["assistant", "mcp_client"])
def test_an_approve_from_the_assistant_or_mcp_writes_command_refused(
    db: sqlite3.Connection, env: CommandEnvironment, actor: Actor
) -> None:
    item_id = pending_observation(db)

    result = submit_command(db, env, actor, "approve", {"item_id": item_id, "reason": "ok"})

    assert_refused(db, result, f"{actor} may not submit approve")
    assert last_refusal(db).actor == actor
    assert open_blockers(db, LEAD)[0].id == item_id


@pytest.mark.parametrize("actor", ["assistant", "mcp_client"])
@pytest.mark.parametrize("command_type", [c.name for c in COMMAND_CLASSES])
def test_assistant_and_mcp_client_may_submit_only_propose_command(
    db: sqlite3.Connection, env: CommandEnvironment, actor: Actor, command_type: str
) -> None:
    if command_type == "propose_command":
        with pytest.raises(NotImplementedError, match="propose_command"):
            submit_command(db, env, actor, command_type, {})
    else:
        assert_refused(db, submit_command(db, env, actor, command_type, {}), "may not submit")


@pytest.mark.parametrize("command_type", [c.name for c in COMMAND_CLASSES])
def test_inbound_may_submit_only_deliver_reply(
    db: sqlite3.Connection, env: CommandEnvironment, command_type: str
) -> None:
    if command_type == "deliver_reply":
        with pytest.raises(NotImplementedError, match="deliver_reply"):
            submit_command(db, env, "inbound", command_type, {})
    else:
        assert_refused(db, submit_command(db, env, "inbound", command_type, {}), "may not submit")


def test_an_unknown_command_type_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    assert_refused(db, submit_command(db, env, "underwriter", "send_postcard", {}), "not a command")


def test_a_refusal_commits_in_its_own_transaction(
    path: str, db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    result = submit_command(db, env, "mcp_client", "approve", {})

    other = open_store(path)
    try:
        assert [e.id for e in events_of(other, EventType.command_refused)] == [result.event_id]
    finally:
        other.close()
    assert not db.in_transaction


def test_a_command_with_no_handler_raises_after_the_checks_and_writes_nothing(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    before = len(read_events(db))

    with pytest.raises(NotImplementedError, match="decline_lead"):
        submit_command(db, env, "underwriter", "decline_lead", {"lead_id": LEAD, "reason": "x"})

    assert len(read_events(db)) == before
    assert not db.in_transaction


# ---- the skill manifest -------------------------------------------------------------------------


def test_a_workflow_command_the_skill_manifest_declares_passes_the_checks(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    with pytest.raises(NotImplementedError, match="fetch_data"):
        submit_command(db, env, "workflow", "fetch_data", {}, skill="fetcher")


def test_a_class_absent_from_the_skill_manifest_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    result = submit_command(db, env, "workflow", "send_routine_request", {}, skill="fetcher")

    assert_refused(db, result, "does not declare send_routine_request")


def test_a_workflow_command_names_its_skill(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    assert_refused(db, submit_command(db, env, "workflow", "fetch_data", {}), "names the skill")


def test_a_skill_with_no_manifest_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    result = submit_command(db, env, "workflow", "fetch_data", {}, skill="missing")

    assert_refused(db, result, "manifest.yaml is missing")


# ---- before any run -----------------------------------------------------------------------------


def test_a_refusal_before_any_run_carries_the_pre_run_id_and_the_reference_morning(
    path: str, env: CommandEnvironment
) -> None:
    db = open_store(path)

    result = submit_command(db, env, "assistant", "approve", {"item_id": 1})

    refusal = last_refusal(db)
    assert refusal.id == result.event_id
    assert (refusal.run_id, refusal.sim_ts) == ("pre-run", REFERENCE_MORNING)
    assert refusal.real_ts == NOW
    db.close()


# ---- item resolution ----------------------------------------------------------------------------


def test_item_id_must_name_an_open_blocker(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    item_id = pending_observation(db)
    assert submit_command(
        db, env, "underwriter", "reject", {"item_id": item_id, "reason": "no"}
    ).accepted

    for command, missing in (("approve", 999), ("reject", item_id)):
        result = submit_command(
            db, env, "underwriter", command, {"item_id": missing, "reason": "x"}
        )
        assert_refused(db, result, f"item {missing} is not an open item")


def test_a_refusal_on_an_item_names_the_items_lead(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = open_item(db, review("round_limit", persists=True))

    submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "x"})

    assert last_refusal(db).lead_id == LEAD


def test_an_open_choice_is_not_approved_or_rejected(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    detail = BlockerDetail(resume_trigger="a ruling", text="Pick.", choice_ids=["c1"])
    item_id = open_item(db, detail, "underwriter_question")

    result = submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "x"})

    assert_refused(db, result, "not an item to approve")


# ---- approve and reject of an observation -------------------------------------------------------


def test_approving_an_observation_makes_it_the_fact_and_records_the_approval(
    db: sqlite3.Connection, env: CommandEnvironment, passes: Passes
) -> None:
    item_id = pending_observation(db)

    result = submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "the producer is right"}
    )

    assert result.accepted and result.reason is None
    assert effective_facts(db, LEAD)["acreage"].value == 3
    assert open_blockers(db, LEAD) == []
    (event,) = events_of(db, EventType.approval_recorded)
    assert event.id == result.event_id
    assert event.actor == "underwriter"
    assert isinstance(event.payload, ApprovalRecorded)
    assert event.payload.item_kind == "observation"
    assert (event.payload.decision, event.payload.reason) == ("approved", "the producer is right")
    assert (event.payload.plan_hash, event.payload.ruleset_hash) == (PLAN_HASH, RULESET)
    (row,) = db.execute(
        "SELECT lead_id, item_kind, intent_id, lead_revision, plan_hash, ruleset_hash, recipient,"
        " payload_hash, actor, decision, reason, event_id FROM approvals"
    ).fetchall()
    assert row == (
        LEAD, "observation", None, 1, PLAN_HASH, RULESET, None, None,
        "underwriter", "approved", "the producer is right", result.event_id,
    )  # fmt: skip
    assert passes.leads == [LEAD]


def test_rejecting_an_observation_keeps_the_existing_value(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = pending_observation(db)

    result = submit_command(
        db, env, "underwriter", "reject", {"item_id": item_id, "reason": "stale"}
    )

    assert result.accepted
    assert effective_facts(db, LEAD)["acreage"].value == 2
    assert open_blockers(db, LEAD) == []
    (decision, reason) = db.execute("SELECT decision, reason FROM approvals").fetchone()
    assert (decision, reason) == ("rejected", "stale")


def test_a_reject_needs_a_reason(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    item_id = pending_observation(db)

    result = submit_command(db, env, "underwriter", "reject", {"item_id": item_id, "reason": ""})

    assert_refused(db, result, "non-empty reason")
    assert len(open_blockers(db, LEAD)) == 1


def test_an_approve_of_an_item_with_no_draft_carries_no_artifact_hash(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = pending_observation(db)
    payload = {"item_id": item_id, "reason": "x", "artifact_hash": "h" * 64}

    result = submit_command(db, env, "underwriter", "approve", payload)

    assert_refused(db, result, "carries no artifact_hash")
    assert effective_facts(db, LEAD)["acreage"].value == 2
    assert db.execute("SELECT COUNT(*) FROM approvals").fetchone() == (0,)


def test_approving_a_lead_without_a_plan_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = pending_observation(db)
    db.execute("UPDATE leads SET plan_hash = NULL")
    db.commit()

    result = submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "x"})

    assert_refused(db, result, "has no plan")
    assert effective_facts(db, LEAD)["acreage"].value == 2


# ---- approve and reject of a review -------------------------------------------------------------


def late_reply_review(db: sqlite3.Connection) -> int:
    observe(db, SETUP, LEAD, "acreage", 2, "submitted", {}, RULES)
    observe_reply(
        db,
        SETUP,
        LEAD,
        [ReplyValue("acreage", 9, {"quote": "9 acres"})],
        RULES,
        round_closed=True,
        intent_id="i-1",
    )
    db.commit()
    (item,) = open_blockers(db, LEAD)
    assert item.detail.cause == "late_reply"
    return item.id


def test_approving_a_late_reply_review_acknowledges_it_and_rejects_the_reply_values(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = late_reply_review(db)

    result = submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "seen"}
    )

    assert result.accepted
    assert open_blockers(db, LEAD) == []
    (status,) = db.execute("SELECT status FROM observations WHERE source = 'reply'").fetchone()
    assert status == "rejected"
    assert effective_facts(db, LEAD)["acreage"].value == 2
    (item_kind, intent_id, event_id) = db.execute(
        "SELECT item_kind, intent_id, event_id FROM approvals"
    ).fetchone()
    assert (item_kind, intent_id, event_id) == ("review", "i-1", result.event_id)


def test_approving_an_event_review_that_is_not_a_late_reply_leaves_observations_alone(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = open_item(db, review("off_topic_reply", intent_id="i-1"))

    result = submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"})

    assert result.accepted
    assert open_blockers(db, LEAD) == []


def test_rejecting_an_event_review_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = open_item(db, review("unread_reply", intent_id="i-1"))

    result = submit_command(db, env, "underwriter", "reject", {"item_id": item_id, "reason": "no"})

    assert_refused(db, result, "resolve_fact, record_ruling or decline_lead")
    assert len(open_blockers(db, LEAD)) == 1


@pytest.mark.parametrize("command", ["approve", "reject"])
def test_a_review_whose_cause_persists_is_refused_both_ways(
    db: sqlite3.Connection, env: CommandEnvironment, command: str
) -> None:
    item_id = open_item(db, review("round_limit", persists=True))

    result = submit_command(db, env, "underwriter", command, {"item_id": item_id, "reason": "x"})

    assert_refused(db, result, "the cause persists")
    assert len(open_blockers(db, LEAD)) == 1


@pytest.mark.parametrize("command", ["approve", "reject"])
def test_a_no_contact_route_item_is_refused_both_ways(
    db: sqlite3.Connection, env: CommandEnvironment, command: str
) -> None:
    detail = BlockerDetail(
        item_kind="no_contact_route", resume_trigger="a contact route", text="No route."
    )
    item_id = open_item(db, detail)

    result = submit_command(db, env, "underwriter", command, {"item_id": item_id, "reason": "x"})

    assert_refused(db, result, "q:contact_email")


@pytest.mark.parametrize("command", ["approve", "reject"])
def test_a_draft_item_is_left_for_the_send_primitive_and_writes_nothing(
    db: sqlite3.Connection, env: CommandEnvironment, command: str
) -> None:
    detail = BlockerDetail(
        item_kind="draft", intent_id="i-1", resume_trigger="an approval", text="Review."
    )
    item_id = open_item(db, detail)
    before = len(read_events(db))

    with pytest.raises(NotImplementedError, match=command):
        submit_command(db, env, "underwriter", command, {"item_id": item_id, "reason": "x"})

    assert len(read_events(db)) == before
    assert len(open_blockers(db, LEAD)) == 1


# ---- resolve_fact and the re-evaluation ---------------------------------------------------------


def test_resolve_fact_returns_the_observation_event_and_re_evaluates_the_lead(
    db: sqlite3.Connection, env: CommandEnvironment, passes: Passes
) -> None:
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "called the producer"}

    result = submit_command(db, env, "underwriter", "resolve_fact", payload)

    assert result.accepted
    stored = {e.id: e for e in read_events(db)}[result.event_id]
    assert stored.type == EventType.fact_observed
    assert effective_facts(db, LEAD)["acreage"].value == 7
    assert passes.leads == [LEAD]
    assert passes.actors == ["workflow"]


def test_resolve_fact_on_an_unknown_lead_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    payload = {"lead_id": "L-9", "key": "acreage", "value": 7, "reason": "x"}

    assert_refused(db, submit_command(db, env, "underwriter", "resolve_fact", payload), "no lead")


def test_a_malformed_payload_is_refused(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    payload = {"lead_id": LEAD, "key": "acreage", "reason": "x"}

    assert_refused(
        db, submit_command(db, env, "underwriter", "resolve_fact", payload), "needs value"
    )


def test_a_terminal_lead_is_not_re_evaluated(
    db: sqlite3.Connection, env: CommandEnvironment, passes: Passes
) -> None:
    db.execute("UPDATE leads SET status = 'declined'")
    db.commit()
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "x"}

    assert submit_command(db, env, "underwriter", "resolve_fact", payload).accepted

    assert passes.leads == []


def test_a_failing_step_opens_the_data_blocker_and_the_commands_writes_commit(
    path: str, db: sqlite3.Connection, skills_root: Path
) -> None:
    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        db.execute("UPDATE leads SET source = 'written by the step'")
        raise RuntimeError("provider is down")

    env = CommandEnvironment(
        "replay", RULESET, RULES, (Step("evaluate", fail),), skills_root, lambda: NOW
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "x"}

    result = submit_command(db, env, "underwriter", "resolve_fact", payload)

    assert result.accepted
    other = open_store(path)
    try:
        assert effective_facts(other, LEAD)["acreage"].value == 7
        (blocker,) = open_blockers(other, LEAD)
        assert blocker.kind == "data"
        assert "Step evaluate failed" in blocker.detail.text
        (source,) = other.execute("SELECT source FROM leads").fetchone()
        assert source == "web"
    finally:
        other.close()


# ---- record_ruling ------------------------------------------------------------------------------


def question(db: sqlite3.Connection) -> None:
    detail = BlockerDetail(resume_trigger="a ruling", text="Pick.", choice_ids=["roof_age_basis"])
    open_item(db, detail, "underwriter_question")


def test_record_ruling_writes_the_ruling_with_actor_reason_and_the_plan_hash(
    db: sqlite3.Connection, env: CommandEnvironment, passes: Passes
) -> None:
    question(db)
    payload = {
        "lead_id": LEAD,
        "choice_id": "roof_age_basis",
        "option": "use_permit",
        "reason": "r",
    }

    result = submit_command(db, env, "underwriter", "record_ruling", payload)

    assert result.accepted
    (event,) = events_of(db, EventType.ruling_recorded)
    assert event.id == result.event_id and event.actor == "underwriter"
    assert isinstance(event.payload, RulingRecorded)
    assert (event.payload.kind, event.payload.choice_id, event.payload.option) == (
        "choice",
        "roof_age_basis",
        "use_permit",
    )
    assert (event.payload.reason, event.payload.plan_hash) == ("r", PLAN_HASH)
    assert passes.leads == [LEAD]


def test_record_ruling_for_a_choice_that_is_not_open_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    question(db)
    payload = {"lead_id": LEAD, "choice_id": "other", "option": "a", "reason": "r"}

    result = submit_command(db, env, "underwriter", "record_ruling", payload)

    assert_refused(db, result, "not an open choice")
    assert events_of(db, EventType.ruling_recorded) == []


def test_record_ruling_needs_a_reason(db: sqlite3.Connection, env: CommandEnvironment) -> None:
    question(db)
    payload = {"lead_id": LEAD, "choice_id": "roof_age_basis", "option": "a", "reason": ""}

    assert_refused(
        db, submit_command(db, env, "underwriter", "record_ruling", payload), "non-empty reason"
    )


def test_the_refused_payload_is_stored_as_submitted(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    payload = {"item_id": 4, "reason": "x"}

    submit_command(db, env, "assistant", "approve", payload)

    stored = last_refusal(db).payload
    assert isinstance(stored, CommandRefused)
    assert json.loads(stored.model_dump_json())["command_payload"] == payload
