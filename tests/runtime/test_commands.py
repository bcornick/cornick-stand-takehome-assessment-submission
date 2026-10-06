# ABOUTME: Tests the command layer of 7.4 and A.11: the actor from the transport, the class rules, the skill manifest check, one transaction per command with the lead's re-evaluation, the dispatch after the commit, and the effect of resolve_fact, approve, reject, edit_draft and record_ruling.
# ABOUTME: Each test opens a real database through open_store at a tmp_path file and reads back events, approvals and blockers; skill folders are built under tmp_path.
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests.runtime.helpers import (
    ASKER,
    NOW,
    PLAN_HASH,
    RECIPIENT,
    RULESET,
    RUN_START,
    command_environment,
    events_of,
    insert_run,
    state_of,
)
from tests.runtime.helpers import LEAD_ID as LEAD
from uwh.rules.models import ActionPlan, OpenChoice
from uwh.runtime.commands import CommandResult, submit_command
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
from uwh.runtime.events import EventContext, read_events
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
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.rulings import rulings_in_force
from uwh.runtime.send import create_draft
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers
from uwh.runtime.workflow import Step, create_lead, lead_revision_and_plan_hash
from uwh.skills.vertical import REFERENCE_MORNING

SETUP = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
RULES = LedgerRules()
ACTORS: tuple[Actor, ...] = ("workflow", "underwriter", "assistant", "inbound")

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
    "start_run": ("underwriter",),
    "propose_command": ("assistant",),
}
RESOLVE_ACREAGE = {"lead_id": LEAD, "key": "acreage", "value": 7, "reason": "called the producer"}


@pytest.fixture
def path(tmp_path: Path) -> str:
    return str(tmp_path / "app.db")


@pytest.fixture
def db(path: str) -> sqlite3.Connection:
    db = open_store(path)
    insert_run(db)
    create_lead(db, SETUP, LEAD, "web", "2026-06-29T07:00:00Z")
    db.execute("UPDATE leads SET plan_hash = ? WHERE lead_id = ?", (PLAN_HASH, LEAD))
    db.commit()
    return db


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
def env(
    tmp_path: Path,
    passes: Passes,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
) -> RunEnvironment:
    return command_environment(tmp_path, mailbox, leadgen, passes.steps)


def assert_refused(db: sqlite3.Connection, result: CommandResult, reason_part: str) -> None:
    assert not result.accepted
    assert result.reason is not None and reason_part in result.reason
    refusal = events_of(db, EventType.command_refused)[-1]
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
    blocker_id = open_blocker(db, SETUP, LEAD, kind, "underwriter", detail)
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


def wait_on_producer(db: sqlite3.Connection, intent_id: str) -> int:
    detail = BlockerDetail(
        resume_trigger="the producer replies", intent_id=intent_id, text="Waiting."
    )
    blocker_id = open_blocker(db, SETUP, LEAD, "producer_reply", "producer", detail)
    db.commit()
    return blocker_id


def decide(
    db: sqlite3.Connection, env: RunEnvironment, command: str, item_id: int, reason: str = "ok"
) -> CommandResult:
    return submit_command(db, env, "underwriter", command, {"item_id": item_id, "reason": reason})


# ---- the gate: actor and class --------------------------------------------------


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("command_type", list(ALLOWED_ACTORS))
def test_the_gate_admits_exactly_the_pairs_of_the_7_4_table(
    db: sqlite3.Connection, env: RunEnvironment, actor: Actor, command_type: str
) -> None:
    if actor not in ALLOWED_ACTORS[command_type]:
        result = submit_command(db, env, actor, command_type, {})
        assert_refused(db, result, f"{actor} may not submit {command_type}")
        return
    try:
        result = submit_command(db, env, actor, command_type, {})
    except NotImplementedError:
        return
    # A handler may still refuse an empty payload; the gate has not.
    assert result.accepted or (result.reason or "").startswith("the payload needs")


def test_the_actor_is_the_transports_and_a_payload_naming_one_is_refused(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    assert submit_command(db, env, "underwriter", "resolve_fact", RESOLVE_ACREAGE).accepted
    (observed,) = events_of(db, EventType.fact_observed)
    assert observed.actor == "underwriter"
    before = len(read_events(db))

    result = submit_command(
        db, env, "underwriter", "resolve_fact", {**RESOLVE_ACREAGE, "actor": "workflow"}
    )

    assert_refused(db, result, "actor")
    assert len(read_events(db)) == before + 1


def test_a_refusal_writes_one_command_refused_with_the_payload_and_changes_nothing_else(
    path: str, db: sqlite3.Connection, env: RunEnvironment
) -> None:
    item_id = pending_observation(db)
    before = len(read_events(db))
    payload = {"item_id": item_id, "reason": "ok"}

    result = submit_command(db, env, "assistant", "approve", payload)

    assert_refused(db, result, "assistant may not submit approve")
    other = open_store(path)
    try:
        assert len(read_events(other)) == before + 1  # committed, though no handler ran
        (refusal,) = events_of(other, EventType.command_refused)
    finally:
        other.close()
    assert isinstance(refusal.payload, CommandRefused)
    assert refusal.payload.command_payload == payload
    assert (refusal.actor, refusal.lead_id) == ("assistant", LEAD)
    assert [b.id for b in open_blockers(db, LEAD)] == [item_id]
    assert not db.in_transaction


def test_a_refusal_before_any_run_carries_the_pre_run_id_and_the_reference_morning(
    path: str, env: RunEnvironment
) -> None:
    db = open_store(path)

    result = submit_command(db, env, "assistant", "approve", {"item_id": 1})

    (refusal,) = events_of(db, EventType.command_refused)
    assert refusal.id == result.event_id
    assert (refusal.run_id, refusal.sim_ts, refusal.real_ts) == ("pre-run", REFERENCE_MORNING, NOW)
    db.close()


# ---- approve and reject by item kind ------------------------------------------------------------


def test_approving_an_observation_makes_it_the_fact_and_records_the_approval(
    db: sqlite3.Connection, env: RunEnvironment, passes: Passes
) -> None:
    item_id = pending_observation(db)

    result = decide(db, env, "approve", item_id, "the producer is right")

    assert result.accepted and result.reason is None
    assert effective_facts(db, LEAD)["acreage"].value == 3
    assert open_blockers(db, LEAD) == []
    (event,) = events_of(db, EventType.approval_recorded)
    assert event.id == result.event_id and event.actor == "underwriter"
    assert isinstance(event.payload, ApprovalRecorded)
    assert event.payload.item_kind == "observation"
    assert (event.payload.decision, event.payload.reason) == ("approved", "the producer is right")
    assert (event.payload.plan_hash, event.payload.ruleset_hash) == (PLAN_HASH, RULESET)
    (row,) = db.execute(
        "SELECT lead_id, item_kind, intent_id, lead_revision, plan_hash, ruleset_hash, recipient,"
        " payload_hash, actor, decision, reason, event_id FROM approvals"
    ).fetchall()
    assert row == (
        LEAD,
        "observation",
        None,
        1,
        PLAN_HASH,
        RULESET,
        None,
        None,
        "underwriter",
        "approved",
        "the producer is right",
        result.event_id,
    )
    assert passes.leads == [LEAD]


def test_rejecting_an_observation_keeps_the_existing_value(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    item_id = pending_observation(db)

    result = decide(db, env, "reject", item_id, "stale")

    assert result.accepted
    assert effective_facts(db, LEAD)["acreage"].value == 2
    assert open_blockers(db, LEAD) == []
    assert db.execute("SELECT decision, reason FROM approvals").fetchone() == ("rejected", "stale")


def test_approving_a_late_reply_review_rejects_the_reply_values_and_leaves_the_open_round(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
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
    round_blocker = wait_on_producer(db, "i-1")

    result = decide(db, env, "approve", item.id, "seen")

    assert result.accepted
    assert [b.id for b in open_blockers(db, LEAD)] == [round_blocker]
    assert db.execute("SELECT status FROM observations WHERE source = 'reply'").fetchone() == (
        "rejected",
    )
    assert effective_facts(db, LEAD)["acreage"].value == 2
    approval = db.execute("SELECT item_kind, intent_id, event_id FROM approvals").fetchone()
    assert approval == ("review", "i-1", result.event_id)


@pytest.mark.parametrize("cause", ["unread_reply", "off_topic_reply", "declining_reply"])
def test_acknowledging_the_review_of_a_reply_closes_the_round_it_answered_and_no_other(
    db: sqlite3.Connection, env: RunEnvironment, cause: ReviewCause
) -> None:
    observation_item = pending_observation(db)
    other_round = wait_on_producer(db, "i-2")
    wait_on_producer(db, "i-1")
    item_id = open_item(db, review(cause, intent_id="i-1"))

    assert decide(db, env, "approve", item_id).accepted

    assert [b.id for b in open_blockers(db, LEAD)] == [observation_item, other_round]
    assert db.execute("SELECT status FROM observations WHERE source = 'reply'").fetchone() == (
        "pending_review",
    )


@pytest.mark.parametrize(
    ("command", "detail", "kind", "reason_part"),
    [
        ("approve", review("round_limit", persists=True), "underwriter_review", "cause persists"),
        ("reject", review("round_limit", persists=True), "underwriter_review", "cause persists"),
        (
            "reject",
            review("unread_reply", intent_id="i-1"),
            "underwriter_review",
            "resolve_fact, record_ruling or decline_lead",
        ),
        (
            "approve",
            BlockerDetail(
                item_kind="no_contact_route", resume_trigger="a contact route", text="No route."
            ),
            "underwriter_review",
            "q:contact_email",
        ),
        (
            "approve",
            BlockerDetail(resume_trigger="a ruling", text="Pick.", choice_ids=["c1"]),
            "underwriter_question",
            "not an item to approve",
        ),
    ],
)
def test_a_decision_the_item_does_not_allow_is_refused_and_leaves_the_item_open(
    db: sqlite3.Connection,
    env: RunEnvironment,
    command: str,
    detail: BlockerDetail,
    kind: BlockerKind,
    reason_part: str,
) -> None:
    item_id = open_item(db, detail, kind)

    assert_refused(db, decide(db, env, command, item_id, "x"), reason_part)

    assert [b.id for b in open_blockers(db, LEAD)] == [item_id]


# ---- drafts: approve, reject and edit_draft -----------------------------------------------------


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


def current_hash(db: sqlite3.Connection, intent_id: str) -> str:
    (value,) = db.execute("SELECT payload_hash FROM intents WHERE id = ?", (intent_id,)).fetchone()
    return str(value)


def approve_payload(db: sqlite3.Connection, intent_id: str, item_id: int) -> dict[str, JsonValue]:
    return {"item_id": item_id, "reason": "ok", "artifact_hash": current_hash(db, intent_id)}


def test_stale_artifact_hash_refused(
    db: sqlite3.Connection, env: RunEnvironment, mailbox: MailboxClient
) -> None:
    intent_id = make_draft(db)
    item_id = item_of(db, intent_id)
    shown = current_hash(db, intent_id)

    assert_refused(db, decide(db, env, "approve", item_id), "artifact_hash")
    wrong = {"item_id": item_id, "reason": "ok", "artifact_hash": "h" * 64}
    assert_refused(db, submit_command(db, env, "underwriter", "approve", wrong), "artifact_hash")
    edit = {"intent_id": intent_id, "subject": "New", "body": "Changed", "reason": "tone"}
    assert submit_command(db, env, "underwriter", "edit_draft", edit).accepted
    stale = {"item_id": item_id, "reason": "ok", "artifact_hash": shown}
    assert_refused(db, submit_command(db, env, "underwriter", "approve", stale), "artifact_hash")

    assert db.execute("SELECT COUNT(*) FROM approvals").fetchone() == (0,)
    assert state_of(db, intent_id) == "draft"
    assert mailbox.list_for_lead(LEAD) == []
    current = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, item_id)
    )
    assert current.accepted
    assert state_of(db, intent_id) == "sent"


def test_approving_a_draft_binds_the_five_values_and_sends_it(
    db: sqlite3.Connection, env: RunEnvironment, mailbox: MailboxClient
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
    (message,) = mailbox.list_for_lead(LEAD)
    assert message["metadata"]["intent_id"] == intent_id
    assert [b.kind for b in open_blockers(db, LEAD)] == ["producer_reply"]


def test_approving_a_quote_packet_sends_it_and_the_lead_becomes_quote_sent(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    intent_id = make_draft(db, "quote_packet")

    result = submit_command(
        db, env, "underwriter", "approve", approve_payload(db, intent_id, item_of(db, intent_id))
    )

    assert result.accepted
    assert db.execute("SELECT status FROM leads").fetchone() == ("quote_sent",)


def test_rejecting_a_draft_returns_it_to_draft_voids_its_approval_and_sends_nothing(
    db: sqlite3.Connection, env: RunEnvironment, mailbox: MailboxClient
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

    result = decide(db, env, "reject", item_id, "too vague")

    assert result.accepted
    assert state_of(db, intent_id) == "draft"
    assert mailbox.list_for_lead(LEAD) == []
    assert [b.id for b in open_blockers(db, LEAD)] == [item_id]
    assert db.execute("SELECT item_kind, decision, reason FROM approvals").fetchall() == [
        ("draft", "rejected", "too vague")
    ]


def test_edit_draft_changes_the_draft_and_writes_draft_edited_as_the_underwriter(
    db: sqlite3.Connection, env: RunEnvironment
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


# ---- resolve_fact, record_ruling and the re-evaluation ------------------------------------------


@pytest.mark.parametrize(("status", "ran"), [("in_progress", [LEAD]), ("declined", [])])
def test_resolve_fact_records_the_fact_and_re_evaluates_a_lead_that_is_not_terminal(
    db: sqlite3.Connection, env: RunEnvironment, passes: Passes, status: str, ran: list[str]
) -> None:
    db.execute("UPDATE leads SET status = ?", (status,))
    db.commit()

    result = submit_command(db, env, "underwriter", "resolve_fact", RESOLVE_ACREAGE)

    assert result.accepted
    observed = [e for e in read_events(db) if e.id == result.event_id]
    assert [e.type for e in observed] == [EventType.fact_observed]
    assert effective_facts(db, LEAD)["acreage"].value == 7
    assert passes.leads == ran
    assert passes.actors == ["workflow"] * len(ran)


def test_a_failing_step_rolls_back_the_whole_re_evaluation_and_the_command_still_commits(
    path: str,
    db: sqlite3.Connection,
    tmp_path: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
) -> None:
    def write(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        observe(db, context, lead_id, "stories", 2, "submitted", {}, RULES)

    def fail(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise RuntimeError("provider is down")

    env = command_environment(
        tmp_path, mailbox, leadgen, (Step("write", write), Step("evaluate", fail))
    )

    assert submit_command(db, env, "underwriter", "resolve_fact", RESOLVE_ACREAGE).accepted

    other = open_store(path)
    assert sorted(effective_facts(other, LEAD)) == ["acreage"]
    assert other.execute("SELECT status FROM leads").fetchone() == ("received",)
    (blocker,) = open_blockers(other, LEAD)
    assert blocker.kind == "data" and "Step evaluate failed" in blocker.detail.text
    other.close()


def test_the_command_and_its_re_evaluation_commit_together(
    path: str,
    db: sqlite3.Connection,
    tmp_path: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
) -> None:
    other = open_store(path)
    seen_inside: list[list[EventType]] = []

    def look(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        seen_inside.append([e.type for e in read_events(other)])

    env = command_environment(tmp_path, mailbox, leadgen, (Step("look", look),))

    submit_command(db, env, "underwriter", "resolve_fact", RESOLVE_ACREAGE)

    assert EventType.fact_observed not in seen_inside[0]
    assert EventType.fact_observed in [e.type for e in read_events(other)]
    other.close()


@pytest.mark.parametrize("actor", ["underwriter", "assistant"])
def test_the_events_of_a_command_take_their_timestamps_inside_its_transaction(
    db: sqlite3.Connection,
    passes: Passes,
    tmp_path: Path,
    mailbox: MailboxClient,
    leadgen: LeadgenClient,
    actor: Actor,
) -> None:
    in_transaction: list[bool] = []

    def now() -> datetime:
        in_transaction.append(db.in_transaction)
        return NOW

    env = command_environment(tmp_path, mailbox, leadgen, passes.steps, now=now)

    submit_command(db, env, actor, "resolve_fact", RESOLVE_ACREAGE)

    assert in_transaction and all(in_transaction)


def open_choice(db: sqlite3.Connection) -> dict[str, JsonValue]:
    """An open choice on the lead's plan and its question card; returns the payload that answers it."""
    plan = ActionPlan(
        open_choices=[
            OpenChoice(
                choice_id="I13.fire_fail",
                options=["decline", "legacy_underwriting"],
                prompt="Decline, or legacy underwriting?",
                show=[],
            )
        ]
    )
    db.execute("UPDATE leads SET plan_json = ? WHERE lead_id = ?", (plan.model_dump_json(), LEAD))
    open_item(
        db,
        BlockerDetail(resume_trigger="a ruling", text="Pick.", choice_ids=["I13.fire_fail"]),
        "underwriter_question",
    )
    return {
        "lead_id": LEAD,
        "choice_id": "I13.fire_fail",
        "option": "legacy_underwriting",
        "reason": "r",
    }


def test_record_ruling_writes_the_ruling_with_actor_reason_and_the_plan_hash_and_re_evaluates(
    db: sqlite3.Connection, env: RunEnvironment, passes: Passes
) -> None:
    payload = open_choice(db)

    result = submit_command(db, env, "underwriter", "record_ruling", payload)

    assert result.accepted
    (event,) = events_of(db, EventType.ruling_recorded)
    assert event.id == result.event_id and event.actor == "underwriter"
    assert isinstance(event.payload, RulingRecorded)
    assert (event.payload.kind, event.payload.choice_id, event.payload.option) == (
        "choice",
        "I13.fire_fail",
        "legacy_underwriting",
    )
    assert (event.payload.reason, event.payload.plan_hash) == ("r", PLAN_HASH)
    assert passes.leads == [LEAD]
    # The ruling moves the lead revision, so a draft built before it is replaced.
    assert lead_revision_and_plan_hash(db, LEAD)[0] == 1


def test_a_ruling_with_an_option_the_choice_does_not_offer_is_refused(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    payload = {**open_choice(db), "option": "maybe"}

    assert_refused(db, submit_command(db, env, "underwriter", "record_ruling", payload), "maybe")

    assert events_of(db, EventType.ruling_recorded) == []


def test_decline_lead_records_the_decline_ruling_and_re_evaluates_the_lead(
    db: sqlite3.Connection, env: RunEnvironment, passes: Passes
) -> None:
    result = submit_command(
        db, env, "underwriter", "decline_lead", {"lead_id": LEAD, "reason": "reputational risk"}
    )

    assert result.accepted
    (event,) = events_of(db, EventType.ruling_recorded)
    assert isinstance(event.payload, RulingRecorded)
    assert (event.payload.kind, event.payload.reason) == ("decline", "reputational risk")
    assert rulings_in_force(db, LEAD).decline_reason == "reputational risk"
    assert passes.leads == [LEAD]


def test_decline_lead_is_refused_for_a_lead_that_is_already_final(
    db: sqlite3.Connection, env: RunEnvironment
) -> None:
    db.execute("UPDATE leads SET status = 'quote_sent'")
    db.commit()

    result = submit_command(
        db, env, "underwriter", "decline_lead", {"lead_id": LEAD, "reason": "too late"}
    )

    assert_refused(db, result, "already final")


@pytest.mark.parametrize(
    "key",
    ["acreage", "q:willing_to_mitigate", "q:contact_email"],
    ids=["field", "catalogue", "route"],
)
def test_resolve_fact_takes_a_registry_field_a_catalogue_answer_or_the_contact_email(
    db: sqlite3.Connection, env: RunEnvironment, key: str
) -> None:
    assert submit_command(
        db, env, "underwriter", "resolve_fact", {**RESOLVE_ACREAGE, "key": key}
    ).accepted


@pytest.mark.parametrize("key", ["acerage", "q:no_such_question", "wiring"])
def test_resolve_fact_refuses_a_key_that_is_not_a_registry_field_or_catalogue_id(
    db: sqlite3.Connection, env: RunEnvironment, key: str
) -> None:
    before = len(read_events(db))

    result = submit_command(db, env, "underwriter", "resolve_fact", {**RESOLVE_ACREAGE, "key": key})

    assert_refused(db, result, key)
    assert [e.type for e in read_events(db)[before:]] == [EventType.command_refused]
    assert effective_facts(db, LEAD) == {}
