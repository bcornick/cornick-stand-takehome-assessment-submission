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
from uwh.api.views import BlockerOwner
from uwh.providers.models import ProviderResult
from uwh.runtime.event_types import (
    AbstentionReason,
    BlockerDetail,
    Candidate,
    ConflictOpened,
    LocatedCandidate,
    ReplyClassification,
)


class Abstention(StrictModel):
    """What a skill returns in place of a result. The reason is one of the two codes of A.10."""

    reason: AbstentionReason
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
    """`asks` is always the outstanding asks, so "nothing left to ask" and "cannot send now" stay
    apart (9.6 sends a quote packet only when no ask remains). `request` says what happens to them:

    - `send`: a request goes out; `message_class` and `round` are set (7.5: "the first request is
      round 1"; 10.1 gives the class).
    - `none`: `asks` is empty and nothing is sent.
    - `request_open`: 10.1 "One open request per lead. A second request is allowed only after a
      reply."; the asks wait for the reply.
    - `round_limit`: 10.1 "After two rounds the lead goes to the underwriter."; the asks stay for
      the underwriter, who closes the review by supplying the fact (A.11 `resolve_fact`).

    The limit itself is the skill's behaviour, not part of this contract."""

    asks: list[Ask]
    message_class: Literal["routine_request", "sensitive_request"] | None  # 10.1; set for `send`
    round: int | None  # `requests_sent + 1`; set for `send`
    request: Literal["send", "none", "request_open", "round_limit"]

    @model_validator(mode="after")
    def request_fits_asks_class_and_round(self) -> Self:
        if (self.request == "none") != (not self.asks):
            raise ValueError("request is none exactly when asks is empty")
        if (self.request == "send") != (self.message_class is not None):
            raise ValueError("message_class is set exactly when request is send")
        if (self.request == "send") != (self.round is not None):
            raise ValueError("round is set exactly when request is send")
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
    """9.6: the packet is built only when the plan holds no decline, no graph is undecided, no
    choice is open, no blocker is open and no ask remains. The skill refuses an input that breaks it."""

    plan: ActionPlan
    facts: dict[str, JsonValue]  # submitted values, for the coverages
    assumed: dict[str, JsonValue]  # facts tagged assumed
    outstanding_asks: list[Ask]  # the asks still to be answered
    open_blocker_kinds: list[str]  # the kind of each open blocker of the lead

    @model_validator(mode="after")
    def nothing_is_left_to_settle(self) -> Self:
        broken = []
        if self.plan.proposed_decline:
            broken.append("the plan is a proposed decline")
        if self.plan.undecided:
            broken.append("the plan has an undecided page")
        if self.plan.open_choices:
            broken.append("the plan has an open choice")
        if self.open_blocker_kinds:
            broken.append(f"an open blocker remains: {', '.join(self.open_blocker_kinds)}")
        if self.outstanding_asks:
            ids = ", ".join(ask.ask_id for ask in self.outstanding_asks)
            broken.append(f"an outstanding ask remains: {ids}")
        if broken:
            raise ValueError("a quote packet is not built when " + "; ".join(broken))
        return self


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
