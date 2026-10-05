# ABOUTME: The event types of A.2 and one Pydantic payload model per type, named after it in PascalCase.
# ABOUTME: Payloads hold only what the event row's own columns do not; PAYLOAD_MODELS maps each type to its model.
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


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


# The value sets of the A.1 columns and the event payloads: section 7.1 statuses and blocker kinds,
# section 7.3 observation sources, section 7.4 actors, A.1 owners, intent kinds and approval item
# kinds, A.11 review causes, section 9.4 provider results and section 8 skill statuses. The store
# builds its CHECK lists from these.
Status = Literal["received", "triaged", "in_progress", "quote_sent", "declined"]
# Ordered by priority, highest first (`uwh.skills.vertical.BLOCKER_KINDS_BY_PRIORITY` holds the order).
BlockerKind = Literal[
    "delivery_unknown", "underwriter_question", "underwriter_review", "data", "producer_reply"
]
BlockerOwner = Literal["underwriter", "producer", "data_team"]
# The intent kinds; each is one section 10.1 message class.
MessageKind = Literal["routine_request", "sensitive_request", "quote_packet", "decline_notice"]
ApprovalItemKind = Literal["draft", "observation", "delivery_unknown", "no_contact_route", "review"]
ObservationSource = Literal["submitted", "fetched", "derived", "assumed", "reply", "underwriter"]
Actor = Literal["workflow", "underwriter", "assistant", "mcp_client", "inbound"]
# What raised an `underwriter_review` item of item kind `review`.
ReviewCause = Literal[
    "late_reply",
    "unread_reply",
    "off_topic_reply",
    "declining_reply",
    "reply_after_terminal_status",
    "draft_held_by_stop",
    "draft_held_class_off",
    "round_limit",
    "identity_score_missing",
    "identity_score_unsupported",
]
ObservationStatus = Literal["accepted", "pending_review", "rejected"]
ProviderStatus = Literal["found", "not_found", "blocked", "unavailable"]
ApprovalDecision = Literal["approved", "rejected"]
ProposalKind = Literal["rule_change", "command"]
ProposalState = Literal["open", "applied", "dismissed"]
IntentState = Literal["draft", "dispatching", "sent", "unknown", "closed_unsent"]
RunStatus = Literal["processing", "settled"]
SkillStatus = Literal["untested", "passing", "failing", "unavailable"]
# A.10: the two codes a skill abstains with, and nothing else.
AbstentionReason = Literal["invalid_tool_input", "refusal"]
ReplyClassification = Literal["answers_all", "answers_some", "declines_to_answer", "off_topic"]
RulingKind = Literal["choice", "suppression", "decline", "withdrawal", "reopened_choice"]


class Payload(BaseModel):
    """Base of every event payload: unknown fields are an error."""

    # A defaulted field is always present in what the model serializes, so the generated client
    # types it as present rather than optional.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class RunStarted(Payload):
    seed: int
    lead_count: int


class ReplayMiss(Payload):
    skill: str
    prompt_version: str
    input_hash: str


class DraftEdited(Payload):
    intent_id: str
    kind: MessageKind  # the intent's kind after the edit (section 7.5)
    subject: str
    body: str
    payload_hash: str
    reason: str
    lead_revision: int  # the lead's revision when the edit was made


class ProposalCreated(Payload):
    """`diff_hash` is the dry-run diff hash: a rule change always has one, a command proposal has none."""

    proposal_id: int
    kind: ProposalKind
    diff_hash: str | None


class LeadReceived(Payload):
    source: str
    received_at: str


class FactObserved(Payload):
    observation_id: int
    key: str  # a registry field name, or a catalogue id prefixed `q:`
    value: JsonValue
    source: ObservationSource
    evidence: dict[
        str, JsonValue
    ]  # quoted span, provider name, derivation id or interpretation row id
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
    """Field id -> its triage result, section 9.2; each value follows `uwh.rules.models.FieldTriage`."""

    fields: dict[str, JsonValue]


class ProviderCalled(Payload):
    key: str  # the field looked up
    status: ProviderStatus
    value: JsonValue
    source: str
    fetched_at: str
    is_stub: bool
    missing_inputs: list[str]  # the inputs a blocked result names; empty otherwise


class PlanBuilt(Payload):
    """The action plan of section 9.6, an object that follows `uwh.rules.models.ActionPlan`, and its hash."""

    plan: dict[str, JsonValue]
    plan_hash: str


class BlockerDetail(Payload):
    """What a blocker carries beyond its kind and owner; also the shape of `blockers.detail_json`."""

    item_kind: ApprovalItemKind | None = None  # None for a blocker that is not a human item
    cause: ReviewCause | None = None  # what raised a review
    cause_persists: bool = (
        False  # a review whose cause persists is refused until the cause is removed
    )
    resume_trigger: str  # what resumes the lead (section 7.1)
    intent_id: str | None = None  # the draft a review is about; the request a reply waits on
    observation_id: int | None = None  # a pending observation
    choice_ids: list[str] = []  # the open choices of a question card (section 9.6)
    text: str  # the reason shown to the human reviewer (section 7.4)


class BlockerOpened(Payload):
    blocker_id: int
    kind: BlockerKind
    owner: BlockerOwner
    detail: BlockerDetail


class BlockerClosed(Payload):
    blocker_id: int
    kind: BlockerKind


class IntentCreated(Payload):
    intent_id: str
    round: int
    kind: MessageKind
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


class Candidate(BaseModel):
    """A candidate observation as the model returned it (A.9)."""

    model_config = ConfigDict(extra="forbid")

    ask_id: str  # an ask id from the open intent: field name, catalogue id or validator id
    field: str  # the registry field or q: id the value is for; for a confirmation, one of its validator's fields
    value: str | int | float | bool
    quote: str = Field(min_length=1)  # the reply text the value was read from, copied exactly


class LocatedCandidate(Candidate):
    span_start: int  # computed by code, never by the model
    span_end: int  # body[span_start:span_end] == quote

    @model_validator(mode="after")
    def _span_fits_the_quote(self) -> "LocatedCandidate":
        # What the model can check without the reply body.
        if self.span_start < 0:
            raise ValueError("span_start is not negative")
        if self.span_end - self.span_start != len(self.quote):
            raise ValueError("the span is as long as the quote")
        return self


class ReplyRead(Payload):
    """A reading, or the abstention that took its place (section 10.4): exactly one of
    `classification` and `abstention` is set, and an abstention has no candidates."""

    intent_id: str  # the intent the reply answers
    body_hash: str  # the hash of the delivered reply body that was read
    classification: ReplyClassification | None
    abstention: AbstentionReason | None
    candidates: list[LocatedCandidate]
    dropped: list[Candidate]  # candidates whose quote is not in the reply, as returned

    @model_validator(mode="after")
    def _a_reading_or_an_abstention(self) -> "ReplyRead":
        if (self.classification is None) == (self.abstention is None):
            raise ValueError("a reply read holds exactly one of classification and abstention")
        if self.abstention is not None and (self.candidates or self.dropped):
            raise ValueError("an abstention has no candidates and none dropped")
        return self


class ApprovalRecorded(Payload):
    item_id: int  # the blocker the decision settles
    item_kind: ApprovalItemKind
    intent_id: str | None
    # The five frozen values of the approval binding (section 7.4). `ruleset_hash` shares its name
    # with an event row column on purpose: it is the ruleset the approval is bound to.
    lead_revision: int
    plan_hash: str
    ruleset_hash: str
    recipient: str | None
    payload_hash: str | None
    decision: ApprovalDecision
    reason: str


class RulingRecorded(Payload):
    """A human ruling. `refers_to_event_id` is the `ruling_recorded` event a withdrawal
    withdraws, or the choice ruling a reopening reopens; None otherwise."""

    kind: RulingKind
    choice_id: str | None
    option: str | None
    reason: str
    lead_revision: int  # the lead's revision when the ruling was recorded
    plan_hash: str  # the lead's plan hash at that moment (section 12)
    suppressed_rule_ids: list[str]
    refers_to_event_id: int | None

    @model_validator(mode="after")
    def _kind_has_its_parts(self) -> "RulingRecorded":
        if self.kind == "choice" and (self.choice_id is None or self.option is None):
            raise ValueError("a choice ruling needs choice_id and option")
        if self.kind == "suppression" and not self.suppressed_rule_ids:
            raise ValueError("a suppression ruling needs suppressed_rule_ids")
        if self.kind != "suppression" and self.suppressed_rule_ids:
            raise ValueError("only a suppression ruling holds suppressed_rule_ids")
        if self.kind in ("suppression", "decline", "withdrawal") and (
            self.choice_id is not None or self.option is not None
        ):
            raise ValueError(f"a {self.kind} ruling holds no choice_id or option")
        if (
            self.kind in ("choice", "suppression", "decline")
            and self.refers_to_event_id is not None
        ):
            raise ValueError(f"a {self.kind} ruling refers to no event")
        if self.kind in ("withdrawal", "reopened_choice") and self.refers_to_event_id is None:
            raise ValueError(f"a {self.kind} ruling needs refers_to_event_id")
        if self.kind == "reopened_choice" and self.choice_id is None:
            raise ValueError("a reopened_choice ruling needs choice_id")
        if self.kind == "reopened_choice" and self.option is not None:
            raise ValueError("a reopened_choice ruling holds no option")
        return self


class CommandRefused(Payload):
    command_type: str
    command_payload: dict[str, JsonValue]  # the payload as submitted
    reason: str


class SettingChanged(Payload):
    key: str
    value: JsonValue


class ClassDemoted(Payload):
    command_class: str
    reason: str


class RuleChangeApplied(Payload):
    """The event row's `ruleset_hash` holds the ruleset in force before the change;
    `applied_ruleset_hash` is the one the change produced."""

    proposal_id: int
    diff_hash: str
    applied_ruleset_hash: str


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
