# ABOUTME: The event types of A.2 and one Pydantic payload model per type, named after it in PascalCase.
# ABOUTME: Payloads hold only what the event row's own columns do not; PAYLOAD_MODELS maps each type to its model.
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue


class EventType(StrEnum):
    run_started = "run_started"
    replay_miss = "replay_miss"
    draft_edited = "draft_edited"
    proposal_created = "proposal_created"
    lead_received = "lead_received"
    fact_observed = "fact_observed"
    fact_selected = "fact_selected"
    conflict_opened = "conflict_opened"
    conflict_closed = "conflict_closed"
    triage_completed = "triage_completed"
    provider_called = "provider_called"
    plan_built = "plan_built"
    blocker_opened = "blocker_opened"
    blocker_closed = "blocker_closed"
    intent_created = "intent_created"
    message_sent = "message_sent"
    delivery_unknown = "delivery_unknown"
    reply_received = "reply_received"
    reply_read = "reply_read"
    approval_recorded = "approval_recorded"
    ruling_recorded = "ruling_recorded"
    command_refused = "command_refused"
    setting_changed = "setting_changed"
    class_demoted = "class_demoted"
    rule_change_applied = "rule_change_applied"
    skill_fallback_used = "skill_fallback_used"
    model_called = "model_called"
    fault_injected = "fault_injected"


# Runtime-level value sets: section 7.3 observations, section 9.4 provider results, A.1 columns,
# section 8 skill statuses.
ObservationSource = Literal["submitted", "fetched", "derived", "assumed", "reply", "underwriter"]
ObservationStatus = Literal["accepted", "pending_review", "rejected"]
ProviderStatus = Literal["found", "not_found", "blocked", "unavailable"]
BlockerOwner = Literal["underwriter", "producer", "data_team"]
ApprovalItemKind = Literal["draft", "observation", "delivery_unknown", "no_contact_route", "review"]
ApprovalDecision = Literal["approved", "rejected"]
ProposalKind = Literal["rule_change", "command"]
SkillStatus = Literal["untested", "passing", "failing", "unavailable"]


class Payload(BaseModel):
    """Base of every event payload: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


class RunStarted(Payload):
    seed: int
    lead_count: int


class ReplayMiss(Payload):
    skill: str
    prompt_version: str
    input_hash: str


class DraftEdited(Payload):
    intent_id: str
    subject: str
    body: str
    payload_hash: str
    reason: str


class ProposalCreated(Payload):
    proposal_id: int
    kind: ProposalKind
    diff_hash: str | None  # a rule-change proposal carries its dry-run diff hash


class LeadReceived(Payload):
    source: str
    received_at: str


class FactObserved(Payload):
    observation_id: int
    key: str  # a registry field name, or a catalogue id prefixed `q:`
    value: JsonValue
    source: ObservationSource
    evidence: dict[str, Any]  # quoted span, provider name, derivation id or interpretation row id
    status: ObservationStatus


class FactSelected(Payload):
    """The effective fact for a key: enough to rebuild a lead's effective facts from these events."""

    key: str
    observation_id: int
    value: JsonValue
    source: ObservationSource
    confirmed: bool


class ConflictOpened(Payload):
    validator: str
    fields: list[str]
    values: dict[str, JsonValue]  # the reported values, as shown in the confirmation question
    question: str


class ConflictClosed(Payload):
    validator: str
    fields: list[str]
    values: dict[str, JsonValue]  # the values the validator will not open again
    observation_id: int | None  # the reply observation that restated the value, if one did


class TriageCompleted(Payload):
    # Field id -> its triage result (value status, requirement, resolution, depends_on), section 9.2.
    fields: dict[str, Any]


class ProviderCalled(Payload):
    key: str  # the field looked up
    status: ProviderStatus
    value: JsonValue
    source: str
    fetched_at: str
    is_stub: bool
    missing_inputs: list[str]  # the inputs a blocked result names; empty otherwise


class PlanBuilt(Payload):
    plan: dict[str, Any]  # the action plan, section 9.6
    plan_hash: str


class BlockerOpened(Payload):
    blocker_id: int
    kind: str
    owner: BlockerOwner
    detail: dict[str, Any]


class BlockerClosed(Payload):
    blocker_id: int
    kind: str


class IntentCreated(Payload):
    intent_id: str
    round: int
    kind: str
    recipient: str
    subject: str
    body: str
    ask_ids: list[str]
    payload_hash: str


class MessageSent(Payload):
    intent_id: str
    mailbox_id: int


class DeliveryUnknown(Payload):
    intent_id: str


class ReplyReceived(Payload):
    intent_id: str
    body: str
    body_hash: str


class ReplyCandidate(Payload):
    """A candidate observation as the model returned it; the field names are A.9's `Candidate`."""

    ask_id: str
    field: str
    value: str | int | float | bool
    quote: str


class LocatedReplyCandidate(ReplyCandidate):
    """A candidate whose quote was found; the field names are A.9's `LocatedCandidate`."""

    span_start: int
    span_end: int


class ReplyRead(Payload):
    classification: str
    candidates: list[LocatedReplyCandidate]
    dropped: list[ReplyCandidate]  # candidates whose quote is not in the reply, as returned


class ApprovalRecorded(Payload):
    item_id: int  # the blocker the decision settles
    item_kind: ApprovalItemKind
    intent_id: str | None
    # The five frozen values of the approval binding (section 7.4).
    lead_revision: int
    plan_hash: str
    ruleset_hash: str
    recipient: str | None
    payload_hash: str | None
    decision: ApprovalDecision
    reason: str


class RulingRecorded(Payload):
    choice_id: str | None  # None for the ruling a rejected decline notice records
    option: str | None
    reason: str
    plan_hash: str  # the lead's plan hash at that moment (section 12)
    suppressed_rule_ids: list[str]


class CommandRefused(Payload):
    command_type: str
    reason: str


class SettingChanged(Payload):
    key: str
    value: JsonValue


class ClassDemoted(Payload):
    command_class: str
    reason: str


class RuleChangeApplied(Payload):
    proposal_id: int
    diff_hash: str
    new_ruleset_hash: str


class SkillFallbackUsed(Payload):
    skill: str
    status: SkillStatus
    fallback: str


class ModelCalled(Payload):
    skill: str
    prompt_version: str
    input_hash: str
    tokens_in: int
    tokens_out: int
    stop_reason: str


class FaultInjected(Payload):
    fault: str


PAYLOAD_MODELS: dict[EventType, type[Payload]] = {
    EventType.run_started: RunStarted,
    EventType.replay_miss: ReplayMiss,
    EventType.draft_edited: DraftEdited,
    EventType.proposal_created: ProposalCreated,
    EventType.lead_received: LeadReceived,
    EventType.fact_observed: FactObserved,
    EventType.fact_selected: FactSelected,
    EventType.conflict_opened: ConflictOpened,
    EventType.conflict_closed: ConflictClosed,
    EventType.triage_completed: TriageCompleted,
    EventType.provider_called: ProviderCalled,
    EventType.plan_built: PlanBuilt,
    EventType.blocker_opened: BlockerOpened,
    EventType.blocker_closed: BlockerClosed,
    EventType.intent_created: IntentCreated,
    EventType.message_sent: MessageSent,
    EventType.delivery_unknown: DeliveryUnknown,
    EventType.reply_received: ReplyReceived,
    EventType.reply_read: ReplyRead,
    EventType.approval_recorded: ApprovalRecorded,
    EventType.ruling_recorded: RulingRecorded,
    EventType.command_refused: CommandRefused,
    EventType.setting_changed: SettingChanged,
    EventType.class_demoted: ClassDemoted,
    EventType.rule_change_applied: RuleChangeApplied,
    EventType.skill_fallback_used: SkillFallbackUsed,
    EventType.model_called: ModelCalled,
    EventType.fault_injected: FaultInjected,
}
