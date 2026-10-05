# ABOUTME: Tests the command layer of 7.4 and A.11: the actor from the transport, the class rules, the skill manifest check, item resolution, one transaction per command with the lead's re-evaluation, the dispatch and mailbox re-check after the commit, and the handlers of resolve_fact, approve, reject, edit_draft and record_ruling.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and reads back events, approvals and blockers; skill folders are built under tmp_path.
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import JsonValue

from tests.runtime.helpers import ASKER, PLAN_HASH, RULESET, RUN_START
from tests.runtime.helpers import LEAD_ID as LEAD
from uwh.runtime.commands import CommandEnvironment, CommandResult, submit_command
from uwh.runtime.event_types import (
    Actor,
    ApprovalRecorded,
    BlockerDetail,
    BlockerKind,
    CommandRefused,
    DraftEdited,
    EventType,
    MessageKind,
    ReviewCause,
    RulingRecorded,
)
from uwh.runtime.events import EventContext, StoredEvent, read_events
from uwh.runtime.facts import (
    LedgerRules,
    ReplyValue,
    effective_facts,
    observe,
    observe_late_reply,
    observe_reply,
)
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.send import create_draft
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers
from uwh.runtime.workflow import Step, create_lead
from uwh.skills.vertical import COMMAND_CLASSES, REFERENCE_MORNING

NOW = RUN_START + timedelta(minutes=5)
SETUP = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
RULES = LedgerRules()
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
    every_class = tmp_path / "skills" / "every_class"
    every_class.mkdir()
    declared = [c.name for c in COMMAND_CLASSES if "workflow" in c.actors]
    manifest = {**manifest, "name": "every_class", "command_classes": declared}
    (every_class / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    return tmp_path / "skills"


@pytest.fixture
def env(
    passes: Passes, skills_root: Path, mailbox: MailboxClient, leadgen: LeadgenClient
) -> CommandEnvironment:
    return CommandEnvironment(
        "replay", RULESET, RULES, passes.steps, skills_root, lambda: NOW, mailbox, leadgen
    )


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
    observe_reply(db, SETUP, LEAD, [ReplyValue("acreage", 3, {"quote": "3 acres"})], RULES)
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


# Section 7.4 table: who may submit each command class, written out here.
ALLOWED_ACTORS: dict[str, tuple[Actor, ...]] = {
    "fetch_data": ("workflow",),
    "send_routine_request": ("workflow",),
    "send_sensitive_request": ("workflow",),
    "send_quote_packet": ("workflow",),
    "send_decline_notice": ("workflow",),
    "deliver_reply": ("inbound", "underwriter"),
    "approve": ("underwriter",),
    "reject": ("underwriter",),
    "edit_draft": ("underwriter",),
    "resolve_fact": ("underwriter",),
    "decline_lead": ("underwriter",),
    "record_ruling": ("underwriter",),
    "propose_rule_change": ("underwriter",),
    "apply_rule_change": ("underwriter",),
    "change_setting": ("underwriter",),
    "emergency_stop": ("underwriter",),
    "start_run": ("underwriter",),
    "propose_command": ("assistant", "mcp_client"),
}


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("command_type", list(ALLOWED_ACTORS))
def test_the_gate_admits_exactly_the_pairs_of_the_7_4_table(
    db: sqlite3.Connection, env: CommandEnvironment, actor: Actor, command_type: str
) -> None:
    skill = "every_class" if actor == "workflow" else None
    if actor not in ALLOWED_ACTORS[command_type]:
        result = submit_command(db, env, actor, command_type, {}, skill=skill)
        assert_refused(db, result, f"{actor} may not submit {command_type}")
        return
    try:
        result = submit_command(db, env, actor, command_type, {}, skill=skill)
    except NotImplementedError:
        return
    # A handler may still refuse an empty payload; the gate has not.
    assert result.accepted or (result.reason or "").startswith("the payload needs")


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
    observe_late_reply(
        db,
        SETUP,
        LEAD,
        [ReplyValue("acreage", 9, {"quote": "9 acres"})],
        RULES,
        intent_id="i-1",
        cause="late_reply",
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
    observation_item = pending_observation(db)
    item_id = open_item(db, review("off_topic_reply", intent_id="i-1"))

    result = submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"})

    assert result.accepted
    assert [b.id for b in open_blockers(db, LEAD)] == [observation_item]
    (status,) = db.execute("SELECT status FROM observations WHERE source = 'reply'").fetchone()
    assert status == "pending_review"


def wait_on_producer(db: sqlite3.Connection, intent_id: str) -> int:
    detail = BlockerDetail(
        resume_trigger="the producer replies", intent_id=intent_id, text="Waiting."
    )
    blocker_id = open_blocker(db, SETUP, LEAD, "producer_reply", "producer", detail)
    db.commit()
    return blocker_id


@pytest.mark.parametrize("cause", ["unread_reply", "off_topic_reply", "declining_reply"])
def test_acknowledging_the_review_of_a_reply_closes_the_round_it_answered(
    db: sqlite3.Connection, env: CommandEnvironment, cause: ReviewCause
) -> None:
    observation_item = pending_observation(db)
    other_round = wait_on_producer(db, "i-2")
    this_round = wait_on_producer(db, "i-1")
    item_id = open_item(db, review(cause, intent_id="i-1"))

    result = submit_command(db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"})

    assert result.accepted
    assert [b.id for b in open_blockers(db, LEAD)] == [observation_item, other_round]
    assert this_round not in [b.id for b in open_blockers(db, LEAD)]
    (status,) = db.execute("SELECT status FROM observations WHERE source = 'reply'").fetchone()
    assert status == "pending_review"


def test_acknowledging_a_review_that_names_no_intent_closes_only_the_review(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    round_blocker = wait_on_producer(db, "i-1")
    item_id = open_item(db, review("unread_reply"))

    assert submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"}
    ).accepted

    assert [b.id for b in open_blockers(db, LEAD)] == [round_blocker]


def test_acknowledging_a_review_with_no_open_round_closes_only_the_review(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = open_item(db, review("unread_reply", intent_id="i-1"))

    assert submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"}
    ).accepted

    assert open_blockers(db, LEAD) == []


def test_acknowledging_a_late_reply_review_leaves_the_open_round_of_its_intent(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = late_reply_review(db)
    round_blocker = wait_on_producer(db, "i-1")

    assert submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"}
    ).accepted

    assert [b.id for b in open_blockers(db, LEAD)] == [round_blocker]


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


@pytest.mark.parametrize("cause", ["draft_held_by_stop", "draft_held_class_off"])
def test_approving_a_held_draft_with_its_hash_raises_and_writes_nothing(
    db: sqlite3.Connection, env: CommandEnvironment, cause: ReviewCause
) -> None:
    item_id = open_item(db, review(cause, intent_id="i-1"))
    before = len(read_events(db))
    payload = {"item_id": item_id, "reason": "ok", "artifact_hash": "h" * 64}

    with pytest.raises(NotImplementedError, match=cause):
        submit_command(db, env, "underwriter", "approve", payload)

    assert len(read_events(db)) == before
    assert len(open_blockers(db, LEAD)) == 1


@pytest.mark.parametrize("cause", ["draft_held_by_stop", "draft_held_class_off"])
def test_rejecting_a_held_draft_review_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment, cause: ReviewCause
) -> None:
    item_id = open_item(db, review(cause, intent_id="i-1"))

    result = submit_command(db, env, "underwriter", "reject", {"item_id": item_id, "reason": "no"})

    assert_refused(db, result, "resolve_fact, record_ruling or decline_lead")


# ---- drafts: approve, reject and edit_draft ----------------------------------------------------


RECIPIENT = "producer@example.com"


def make_draft(db: sqlite3.Connection, kind: MessageKind = "sensitive_request") -> str:
    """A draft of the kind in the `in_progress` lead; returns its intent id."""
    db.execute("UPDATE leads SET status = 'in_progress'")
    intent_id = create_draft(
        db, SETUP, ASKER, LEAD, kind, RECIPIENT, "Subject", "Body", ["acreage"]
    )
    db.commit()
    return intent_id


def item_of(db: sqlite3.Connection, intent_id: str) -> int:
    """The id of the item that reviews the draft."""
    (item,) = [b for b in open_blockers(db, LEAD) if b.detail.intent_id == intent_id]
    return item.id


def intent_state(db: sqlite3.Connection, intent_id: str) -> str:
    (state,) = db.execute("SELECT state FROM intents WHERE id = ?", (intent_id,)).fetchone()
    return str(state)


def current_hash(db: sqlite3.Connection, intent_id: str) -> str:
    (value,) = db.execute("SELECT payload_hash FROM intents WHERE id = ?", (intent_id,)).fetchone()
    return str(value)


def approve_payload(db: sqlite3.Connection, intent_id: str, item_id: int) -> dict[str, JsonValue]:
    return {"item_id": item_id, "reason": "ok", "artifact_hash": current_hash(db, intent_id)}


def test_stale_artifact_hash_refused(
    db: sqlite3.Connection, env: CommandEnvironment, mailbox: MailboxClient
) -> None:
    intent_id = make_draft(db)
    item_id = item_of(db, intent_id)
    shown = current_hash(db, intent_id)

    missing = submit_command(
        db, env, "underwriter", "approve", {"item_id": item_id, "reason": "ok"}
    )
    assert_refused(db, missing, "artifact_hash")
    wrong = {"item_id": item_id, "reason": "ok", "artifact_hash": "h" * 64}
    assert_refused(db, submit_command(db, env, "underwriter", "approve", wrong), "artifact_hash")
    edit = {"intent_id": intent_id, "subject": "New", "body": "Changed", "reason": "tone"}
    assert submit_command(db, env, "underwriter", "edit_draft", edit).accepted
    stale = {"item_id": item_id, "reason": "ok", "artifact_hash": shown}
    assert_refused(db, submit_command(db, env, "underwriter", "approve", stale), "artifact_hash")

    assert last_refusal(db).lead_id == LEAD
    assert db.execute("SELECT COUNT(*) FROM approvals").fetchone() == (0,)
    assert intent_state(db, intent_id) == "draft"
    assert mailbox.list_for_lead(LEAD) == []
    current = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, item_id)
    )
    assert current.accepted
    assert intent_state(db, intent_id) == "sent"


def test_approving_a_draft_binds_the_five_values_and_sends_it(
    db: sqlite3.Connection, env: CommandEnvironment, mailbox: MailboxClient
) -> None:
    intent_id = make_draft(db)
    item_id = item_of(db, intent_id)

    result = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, item_id)
    )

    assert result.accepted
    approval = db.execute(
        "SELECT lead_id, item_kind, intent_id, lead_revision, plan_hash, ruleset_hash, recipient,"
        " payload_hash, actor, decision, reason, event_id FROM approvals"
    ).fetchone()
    assert approval == (
        LEAD,
        "draft",
        intent_id,
        0,
        PLAN_HASH,
        RULESET,
        RECIPIENT,
        current_hash(db, intent_id),
        "underwriter",
        "approved",
        "ok",
        result.event_id,
    )
    (event,) = [e for e in events_of(db, EventType.approval_recorded) if e.id == result.event_id]
    assert isinstance(event.payload, ApprovalRecorded)
    assert (event.payload.recipient, event.payload.payload_hash) == (
        RECIPIENT,
        current_hash(db, intent_id),
    )
    (message,) = mailbox.list_for_lead(LEAD)
    assert message["metadata"]["intent_id"] == intent_id
    assert [b.kind for b in open_blockers(db, LEAD)] == ["producer_reply"]


def test_approving_a_quote_packet_sends_it_and_the_lead_becomes_quote_sent(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    intent_id = make_draft(db, "quote_packet")
    item_id = item_of(db, intent_id)

    result = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, item_id)
    )

    assert result.accepted
    assert db.execute("SELECT status FROM leads").fetchone() == ("quote_sent",)


def test_approving_a_draft_item_whose_draft_is_gone_or_sent_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    detail = BlockerDetail(
        item_kind="draft", intent_id="i-1", resume_trigger="an approval", text="Review."
    )
    item_id = open_item(db, detail)
    payload = {"item_id": item_id, "reason": "ok", "artifact_hash": "h" * 64}

    assert_refused(db, submit_command(db, env, "underwriter", "approve", payload), "i-1")

    intent_id = make_draft(db)
    sent_item = item_of(db, intent_id)
    db.execute("UPDATE intents SET state = 'sent' WHERE id = ?", (intent_id,))
    db.commit()
    result = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, sent_item)
    )

    assert_refused(db, result, "not draft")


def test_rejecting_a_draft_request_returns_it_to_draft_with_the_reason_and_voids_its_approval(
    db: sqlite3.Connection, env: CommandEnvironment, mailbox: MailboxClient
) -> None:
    intent_id = make_draft(db)
    item_id = item_of(db, intent_id)
    db.execute(
        "INSERT INTO approvals (lead_id, item_kind, intent_id, lead_revision, plan_hash,"
        " ruleset_hash, recipient, payload_hash, actor, decision, reason)"
        " VALUES (?, 'draft', ?, 0, ?, ?, ?, ?, 'underwriter', 'approved', 'ok')",
        (LEAD, intent_id, PLAN_HASH, RULESET, RECIPIENT, current_hash(db, intent_id)),
    )
    db.commit()

    result = submit_command(
        db, env, "underwriter", "reject", {"item_id": item_id, "reason": "too vague"}
    )

    assert result.accepted
    assert intent_state(db, intent_id) == "draft"
    assert mailbox.list_for_lead(LEAD) == []
    assert [b.id for b in open_blockers(db, LEAD)] == [item_id]
    assert db.execute("SELECT item_kind, decision, reason FROM approvals").fetchall() == [
        ("draft", "rejected", "too vague")
    ]


def test_a_reject_of_a_draft_carries_no_artifact_hash(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    intent_id = make_draft(db)
    item_id = item_of(db, intent_id)
    payload = {"item_id": item_id, "reason": "no", "artifact_hash": current_hash(db, intent_id)}

    assert_refused(
        db, submit_command(db, env, "underwriter", "reject", payload), "carries no artifact_hash"
    )


def test_rejecting_a_draft_decline_notice_raises_and_writes_nothing(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    item_id = item_of(db, make_draft(db, "decline_notice"))
    before = len(read_events(db))

    with pytest.raises(NotImplementedError, match="decline notice"):
        submit_command(db, env, "underwriter", "reject", {"item_id": item_id, "reason": "x"})

    assert len(read_events(db)) == before
    assert len(open_blockers(db, LEAD)) == 1


def test_edit_draft_writes_draft_edited_and_changes_the_draft(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    intent_id = make_draft(db, "routine_request")
    payload = {"intent_id": intent_id, "subject": "New", "body": "Changed", "reason": "tone"}

    result = submit_command(db, env, "underwriter", "edit_draft", payload)

    assert result.accepted
    (event,) = events_of(db, EventType.draft_edited)
    assert event.id == result.event_id and event.actor == "underwriter" and event.lead_id == LEAD
    assert isinstance(event.payload, DraftEdited)
    assert (event.payload.kind, event.payload.reason) == ("sensitive_request", "tone")
    assert event.payload.payload_hash == current_hash(db, intent_id)


def test_edit_draft_of_a_draft_that_has_left_draft_is_refused_and_names_its_lead(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    intent_id = make_draft(db)
    db.execute("UPDATE intents SET state = 'dispatching' WHERE id = ?", (intent_id,))
    db.commit()
    payload = {"intent_id": intent_id, "subject": "New", "body": "Changed", "reason": "late"}

    result = submit_command(db, env, "underwriter", "edit_draft", payload)

    assert_refused(db, result, "not draft")
    assert last_refusal(db).lead_id == LEAD
    assert events_of(db, EventType.draft_edited) == []


def test_edit_draft_of_no_intent_is_refused(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    payload = {"intent_id": "nope", "subject": "New", "body": "Changed", "reason": "x"}

    assert_refused(db, submit_command(db, env, "underwriter", "edit_draft", payload), "nope")


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
    path: str,
    db: sqlite3.Connection,
    skills_root: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
) -> None:
    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        db.execute("UPDATE leads SET source = 'written by the step'")
        raise RuntimeError("provider is down")

    env = CommandEnvironment(
        "replay",
        RULESET,
        RULES,
        (Step("evaluate", fail),),
        skills_root,
        lambda: NOW,
        mailbox,
        leadgen,
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


def test_a_failing_step_rolls_back_the_whole_re_evaluation_and_the_command_still_commits(
    db: sqlite3.Connection, skills_root: Path, mailbox: MailboxClient, leadgen: LeadgenClient
) -> None:
    def write(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "stories", 2, "submitted", {}, RULES)

    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    steps = (Step("write", write), Step("evaluate", fail))
    env = CommandEnvironment(
        "replay", RULESET, RULES, steps, skills_root, lambda: NOW, mailbox, leadgen
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "x"}

    assert submit_command(db, env, "underwriter", "resolve_fact", payload).accepted

    assert sorted(effective_facts(db, LEAD)) == ["acreage"]
    assert db.execute("SELECT status FROM leads").fetchone() == ("received",)
    (blocker,) = open_blockers(db, LEAD)
    assert blocker.kind == "data" and "Step evaluate failed" in blocker.detail.text


def test_the_command_and_its_re_evaluation_commit_together(
    path: str,
    db: sqlite3.Connection,
    skills_root: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
) -> None:
    other = open_store(path)
    seen_inside: list[list[EventType]] = []

    def look(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        seen_inside.append([e.type for e in read_events(other)])

    env = CommandEnvironment(
        "replay", RULESET, RULES, (Step("look", look),), skills_root, lambda: NOW, mailbox, leadgen
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "x"}

    submit_command(db, env, "underwriter", "resolve_fact", payload)

    assert EventType.fact_observed not in seen_inside[0]
    assert EventType.fact_observed in [e.type for e in read_events(other)]
    other.close()


@pytest.mark.parametrize("accepted", [True, False])
def test_the_events_of_a_command_take_their_timestamps_inside_its_transaction(
    db: sqlite3.Connection,
    passes: Passes,
    skills_root: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
    accepted: bool,
) -> None:
    in_transaction: list[bool] = []

    def now() -> datetime:
        in_transaction.append(db.in_transaction)
        return NOW

    env = CommandEnvironment(
        "replay", RULESET, RULES, passes.steps, skills_root, now, mailbox, leadgen
    )
    payload = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "x"}

    submit_command(db, env, "underwriter" if accepted else "assistant", "resolve_fact", payload)

    assert in_transaction and all(in_transaction)


def test_a_command_submitted_inside_a_transaction_is_an_error(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    db.execute("BEGIN")

    with pytest.raises(RuntimeError, match="transaction"):
        submit_command(db, env, "underwriter", "resolve_fact", {})

    db.rollback()


def test_a_refusal_names_a_lead_only_when_the_lead_exists(
    db: sqlite3.Connection, env: CommandEnvironment
) -> None:
    unknown = {"lead_id": "NOPE", "key": "acreage", "value": 7, "reason": "x"}
    known = {"lead_id": LEAD, "key": "acreage", "reason": "x"}

    submit_command(db, env, "underwriter", "resolve_fact", unknown)
    assert last_refusal(db).lead_id is None
    submit_command(db, env, "underwriter", "resolve_fact", known)
    assert last_refusal(db).lead_id == LEAD


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
