# ABOUTME: Input and output models of the seven skills of section 8, the shared typed abstention, the A.9 reply models and the section 10.5 quote packet.
# ABOUTME: Inputs carry values, never handles; each output is the skill's result or an Abstention.
from typing import Literal, Self

from pydantic import JsonValue, model_validator

from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    Ask,
    CoverageAdjustmentEffect,
    ExclusionOrEndorsementEffect,
    FieldTriage,
    NotEvaluatedNote,
    ObligationEffect,
    PlannedEffect,
    RequirementEffect,
    StrictModel,
    SurchargeEffect,
)
from uwh.providers.models import ProviderResult
from uwh.runtime.event_types import (
    BlockerDetail,
    BlockerOwner,
    Candidate,
    ConflictOpened,
    LocatedCandidate,
    ReplyClassification,
)


class Abstention(StrictModel):
    """What a skill returns in place of a result. `read_reply` uses the codes `refusal` and `invalid_tool_input` (A.10)."""

    reason: str
    message: str


# triage_fields (9.2).
class TriageFieldsInput(StrictModel):
    facts: dict[str, JsonValue]  # the lead's effective facts; None means missing
    conflicting_fields: list[str]  # fields in an open conflict
    unsupported_fields: list[str]  # fields whose value the validators call unsupported
    # System-owned field -> the missing input fields its blocked lookup names (9.4). A lookup not
    # yet made is not in the mapping.
    blocked_lookups: dict[str, list[str]]


class TriageFieldsResult(StrictModel):
    fields: dict[str, FieldTriage]  # field id -> triage


TriageFieldsOutput = TriageFieldsResult | Abstention


# resolve_data (9.3, 9.4).
class ResolvedObservation(StrictModel):
    key: str  # a registry field name
    value: JsonValue
    source: Literal[
        "derived", "fetched", "assumed"
    ]  # the three ways 9.3 resolves a value without asking
    evidence: dict[str, JsonValue]  # provider name or derivation id


class BlockerRequest(StrictModel):
    kind: str
    owner: BlockerOwner
    detail: BlockerDetail


class AskField(StrictModel):
    field: str  # a registry field name
    reason: str  # why it is asked, for example the blocked lookup that names it as a missing input


class ResolveDataInput(StrictModel):
    facts: dict[str, JsonValue]
    triage: dict[str, FieldTriage]
    provider_results: dict[str, ProviderResult]  # field -> the lookup the runtime made


class ResolveDataResult(StrictModel):
    observations: list[ResolvedObservation]
    ask_fields: list[AskField]  # fields left to ask, including the inputs a blocked lookup names
    catalogue_questions: list[str]  # catalogue ids, such as the combined knob-and-tube question
    blockers: list[BlockerRequest]


ResolveDataOutput = ResolveDataResult | Abstention


# evaluate_playbook (9.6).
class EvaluatePlaybookInput(StrictModel):
    facts: dict[str, JsonValue]  # usable facts only; a missing key is unknown
    answered_choices: dict[str, str]  # choice id -> option id
    suppressed_rules: list[str]
    underwriter_decline: str | None = None  # the reason of a `decline_lead` ruling in force (A.11)


EvaluatePlaybookOutput = ActionPlan | Abstention


# plan_asks (10.2).
class PlanAsksInput(StrictModel):
    """`requests_sent` and `open_request` serve 10.1 and 7.5: one open request per lead, a second
    only after a reply, and rounds that number requests only."""

    triage: dict[str, FieldTriage]
    resolved: ResolveDataResult
    plan: ActionPlan
    conflicts: list[ConflictOpened]  # open conflicts, each to be confirmed
    requests_sent: (
        int  # requests this lead has had, each a round (7.5); packets and notices do not count
    )
    open_request: bool  # a request is unanswered (10.1: one open request per lead)


class PlanAsksResult(StrictModel):
    """`asks` is the asks of the request to send; it is empty when no request is sent: nothing is
    asked, a request is open, or the round limit is reached. `round` serves 7.5 ("the first request
    is round 1") and `round_limit_reached` serves 10.1 ("after two rounds the lead goes to the
    underwriter"); the limit is the skill's behaviour, not part of this contract."""

    asks: list[Ask]
    message_class: Literal["routine_request", "sensitive_request"] | None  # 10.1; None with no asks
    round: int | None  # `requests_sent + 1`; None when there is no request to send
    round_limit_reached: (
        bool  # the plan still asks and `requests_sent` is at the limit: no request is planned
    )

    @model_validator(mode="after")
    def has_a_class_exactly_when_it_asks(self) -> Self:
        if (self.message_class is None) != (not self.asks):
            raise ValueError("message_class is None exactly when asks is empty")
        if (self.round is None) != (self.message_class is None):
            raise ValueError("round is None exactly when message_class is None")
        if self.round_limit_reached and self.message_class is not None:
            raise ValueError("round_limit_reached plans no request: message_class is None")
        return self


PlanAsksOutput = PlanAsksResult | Abstention


# build_quote_packet (10.5). No field holds a price.
class CoverageLine(StrictModel):
    field: str
    value: JsonValue  # as submitted


class CoverageAdjustmentLine(CoverageAdjustmentEffect):
    submitted_value: JsonValue  # shown beside the proposed value


class QuotePacket(StrictModel):
    coverages: list[CoverageLine]
    coverage_adjustments: list[CoverageAdjustmentLine]
    surcharges: list[SurchargeEffect]  # one per line, each with its rule
    requirements: list[RequirementEffect]  # each with its deadline
    exclusions_and_endorsements: list[ExclusionOrEndorsementEffect]
    advisories: list[AdvisoryEffect]
    obligations: list[ObligationEffect]  # every effect of the plan appears in the packet
    notes: list[NotEvaluatedNote]  # the pages and rows the system does not evaluate (4.1)


class InternalCopy(StrictModel):
    assumptions: dict[str, JsonValue]
    rule_traces: list[PlannedEffect]
    approver: str | None = None


class BuildQuotePacketInput(StrictModel):
    plan: ActionPlan
    facts: dict[str, JsonValue]  # submitted values, for the coverages
    assumed: dict[str, JsonValue]  # facts tagged assumed


class BuildQuotePacketResult(StrictModel):
    packet: QuotePacket
    internal: InternalCopy


BuildQuotePacketOutput = BuildQuotePacketResult | Abstention


# render_message (10.2, A.8). The subject kinds are A.8's three.
class RenderMessageInput(StrictModel):
    kind: Literal["request", "quote_packet", "decline_notice"]
    lead_label: str  # the address or lead id in the subject
    audience: Literal["producer", "applicant"]  # a `direct_web` lead gets applicant wording (10.3)
    asks: list[Ask] = []
    packet: QuotePacket | None = None


class RenderMessageResult(StrictModel):
    subject: str
    body: str
    ask_ids: list[str]


RenderMessageOutput = RenderMessageResult | Abstention


# read_reply (A.9). `Candidate`, `LocatedCandidate` and `ReplyClassification` are the runtime's definitions, imported above.
class ReplyReading(StrictModel):
    """What the model returns; its JSON schema is the input schema of the forced tool."""

    classification: ReplyClassification
    candidates: list[Candidate]


class ReadReplyInput(StrictModel):
    body: str
    open_asks: list[Ask]  # the open intent's asks; values are extracted only for these


class ReadReplyResult(StrictModel):
    classification: ReplyClassification
    candidates: list[LocatedCandidate]
    dropped: list[
        Candidate
    ]  # candidates whose quote is not in the reply, as the model returned them


ReadReplyOutput = ReadReplyResult | Abstention
