# ABOUTME: Tests the narrative sentence of an event payload (section 11): one for each event type, with no `name: value` dump, no object repr and no JSON.
# ABOUTME: Every event type has a payload below, and a type the summary does not know fails the sentence check.
import re

import pytest

from uwh.api.event_summary import event_summary
from uwh.providers.models import ProviderResult
from uwh.rules.models import StrictModel
from uwh.runtime.event_types import (
    ApprovalRecorded,
    BlockerClosed,
    BlockerDetail,
    BlockerOpened,
    CommandRefused,
    ConflictClosed,
    ConflictOpened,
    DeliveryUnknown,
    DraftEdited,
    EventType,
    FactObserved,
    FactSelected,
    FaultInjected,
    IntentCreated,
    LeadReceived,
    MessageSent,
    ModelCalled,
    PlanBuilt,
    ProposalCreated,
    ProviderCalled,
    ReplayMiss,
    ReplyRead,
    ReplyReceived,
    RulingRecorded,
    RunStarted,
    SkillFallbackUsed,
    TriageCompleted,
)

DETAIL = BlockerDetail(resume_trigger="the producer replies", text="Waiting for the reply.")
PAYLOADS: dict[EventType, StrictModel] = {
    EventType.run_started: RunStarted(seed=42, lead_count=12),
    EventType.replay_miss: ReplayMiss(skill="chat", prompt_version="v", input_hash="h"),
    EventType.draft_edited: DraftEdited(
        intent_id="i",
        kind="routine_request",
        subject="s",
        body="b",
        payload_hash="h",
        reason="tone",
        lead_revision=1,
    ),
    EventType.proposal_created: ProposalCreated(proposal_id=3),
    EventType.lead_received: LeadReceived(source="web", received_at="2026-06-29T07:00:00Z"),
    EventType.fact_observed: FactObserved(
        observation_id=1,
        key="roof_year",
        value=2017,
        source="submitted",
        evidence={},
        status="accepted",
    ),
    EventType.fact_selected: FactSelected(
        key="roof_year", observation_id=1, value=2017, source="submitted", confirmed=False
    ),
    EventType.conflict_opened: ConflictOpened(
        validator="v", fields=["a", "b"], values={"a": 1}, question="Which one?"
    ),
    EventType.conflict_closed: ConflictClosed(
        validator="v", fields=["a", "b"], values={"a": 1}, observation_id=None
    ),
    EventType.triage_completed: TriageCompleted(
        fields={"a": {"value_status": "missing"}, "b": {"value_status": "present"}}
    ),
    EventType.provider_called: ProviderCalled(
        key="p_f",
        result=ProviderResult(status="found", value=0.1, source="fire", fetched_at="t"),
    ),
    EventType.plan_built: PlanBuilt(plan={"effects": []}, plan_hash="h"),
    EventType.blocker_opened: BlockerOpened(
        blocker_id=1, kind="producer_reply", owner="producer", detail=DETAIL
    ),
    EventType.blocker_closed: BlockerClosed(blocker_id=1, kind="producer_reply"),
    EventType.intent_created: IntentCreated(
        intent_id="i",
        round=1,
        kind="routine_request",
        recipient="p@example.com",
        subject="Questions",
        body="b",
        ask_ids=["a"],
        payload_hash="h",
    ),
    EventType.message_sent: MessageSent(intent_id="i", mailbox_id=4),
    EventType.delivery_unknown: DeliveryUnknown(intent_id="i"),
    EventType.reply_received: ReplyReceived(intent_id="i", body="Yes it is.", body_hash="h"),
    EventType.reply_read: ReplyRead(
        intent_id="i",
        body_hash="h",
        classification="answers_all",
        classified_by="model",
        jev_confidence=None,
        abstention=None,
        candidates=[],
        dropped=[],
    ),
    EventType.approval_recorded: ApprovalRecorded(
        item_id=1,
        item_kind="draft",
        intent_id="i",
        lead_revision=1,
        plan_hash="p",
        ruleset_hash="r",
        recipient=None,
        payload_hash=None,
        decision="approved",
        reason="fine",
    ),
    EventType.ruling_recorded: RulingRecorded(
        kind="decline",
        choice_id=None,
        option=None,
        reason="vacant",
        lead_revision=1,
        plan_hash="p",
        suppressed_rule_ids=[],
        refers_to_event_id=None,
    ),
    EventType.command_refused: CommandRefused(
        command_type="resolve_fact", command_payload={"key": "x"}, reason="not a field"
    ),
    EventType.skill_fallback_used: SkillFallbackUsed(
        skill="read_reply", status="unavailable", fallback="held for review"
    ),
    EventType.model_called: ModelCalled(
        skill="chat",
        prompt_version="v",
        input_hash="h",
        tokens_in=10,
        tokens_out=5,
        stop_reason="tool_use",
    ),
    EventType.fault_injected: FaultInjected(fault="send_twice"),
}


@pytest.mark.parametrize("event_type", list(EventType))
def test_a_summary_is_one_plain_sentence(event_type: EventType) -> None:
    summary = event_summary(PAYLOADS[event_type])

    assert summary != "" and "\n" not in summary
    assert not re.search(r"(:.*){2}|[{}\[\]]|=|object at|\bNone\b", summary)


def _provider_called(key: str, **result: object) -> ProviderCalled:
    return ProviderCalled(
        key=key,
        result=ProviderResult(source="s", fetched_at="t", **result),  # type: ignore[arg-type]
    )


def _reply_read(classified_by: str, confidence: float | None) -> ReplyRead:
    return ReplyRead(
        intent_id="i",
        body_hash="h",
        classification="answers_all",
        classified_by=classified_by,  # type: ignore[arg-type]
        jev_confidence=confidence,
        abstention=None,
        candidates=[],
        dropped=[],
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (PAYLOADS[EventType.run_started], "Started the run with 12 leads from seed 42"),
        (PAYLOADS[EventType.lead_received], "Received the lead from web"),
        (PAYLOADS[EventType.fact_observed], "Recorded roof_year as 2017 (submitted)"),
        (
            PAYLOADS[EventType.fact_observed].model_copy(update={"status": "pending_review"}),
            "Recorded roof_year as 2017 (submitted), held for review",
        ),
        (PAYLOADS[EventType.fact_selected], "Using 2017 for roof_year (submitted)"),
        (
            TriageCompleted(
                fields={
                    "a": {"value_status": "missing"},
                    "b": {"value_status": "missing"},
                    "c": {"value_status": "present"},
                }
            ),
            "Triaged the fields: 2 missing",
        ),
        (
            TriageCompleted(
                fields={"a": {"value_status": "conflicting"}, "b": {"value_status": "missing"}}
            ),
            "Triaged the fields: 1 missing, 1 conflicting",
        ),
        (PAYLOADS[EventType.provider_called], "Fetched the fire probability: 0.1"),
        (
            _provider_called("p_f", status="unavailable", value=None),
            "The fire simulation failed, so you need to choose",
        ),
        (
            _provider_called("replacement_cost", status="not_found", value=None),
            "Could not fetch the replacement cost: the lookup was not found",
        ),
        (
            _provider_called("p_f", status="blocked", value=None, missing_inputs=["address"]),
            "Could not fetch the fire probability: it needs address",
        ),
        (PAYLOADS[EventType.blocker_opened], "Waiting on the producer. Waiting for the reply."),
        (
            PAYLOADS[EventType.intent_created],
            "Drafted a routine request to p@example.com with the subject Questions",
        ),
        (PAYLOADS[EventType.message_sent], "Sent the message to the producer"),
        (PAYLOADS[EventType.reply_received], "The producer replied"),
        (
            PAYLOADS[EventType.reply_read],
            "The model classified this reply. It answers every question asked; 0 answers found.",
        ),
        (PAYLOADS[EventType.approval_recorded], 'Approved a draft with the reason "fine"'),
        (PAYLOADS[EventType.command_refused], "Refused resolve fact. not a field."),
    ],
)
def test_a_summary_says_what_happened_in_words(payload: StrictModel, expected: str) -> None:
    assert event_summary(payload) == expected


@pytest.mark.parametrize(
    ("confidence", "meaning"),
    [(0.83, "at or above"), (0.70, "at or above"), (0.41, "below")],
)
def test_a_reply_classified_by_jev_shows_its_confidence_against_the_threshold(
    confidence: float, meaning: str
) -> None:
    summary = event_summary(_reply_read("jev", confidence))

    assert summary == (
        f"Jev classified this reply ({confidence:.2f}, {meaning} the 0.70 threshold). "
        "It answers every question asked; 0 answers found."
    )


def test_a_rewrite_the_model_wrote_is_said_in_the_summary_of_the_draft() -> None:
    created = PAYLOADS[EventType.intent_created].model_copy(update={"rewritten_by_model": True})  # type: ignore[attr-defined]

    assert event_summary(created) == (
        "Drafted a routine request to p@example.com with the subject Questions. "
        "The opening and closing were written by the model."
    )


def test_a_rejected_rewrite_says_which_check_rejected_it_and_that_the_rendered_request_is_used() -> (
    None
):
    rejected = SkillFallbackUsed(
        skill="polish_message",
        status="rejected",
        fallback="The rewrite of the request was rejected by the model check (it adds a deadline); "
        "the rendered request is used",
    )

    assert event_summary(rejected) == (
        "The rewrite of the request was rejected by the model check (it adds a deadline); "
        "the rendered request is used"
    )
