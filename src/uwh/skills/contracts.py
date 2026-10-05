# ABOUTME: Input and output models of the seven skills of section 8, the shared typed abstention, the A.9 reply models and the section 10.5 quote packet.
# ABOUTME: Inputs carry values, never handles; each output is the skill's result or an Abstention.
from typing import Literal

from pydantic import JsonValue

from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    Ask,
    CoverageAdjustmentEffect,
    ExclusionOrEndorsementEffect,
    FieldTriage,
    PlannedEffect,
    RequirementEffect,
    StrictModel,
    SurchargeEffect,
)
from uwh.providers.models import ProviderResult
from uwh.runtime.event_types import (
    BlockerOwner,
    Candidate,
    ConflictOpened,
    LocatedCandidate,
    ObservationSource,
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
    blocked_fields: list[str]  # system-owned fields whose lookup is blocked or pending


class TriageFieldsResult(StrictModel):
    fields: dict[str, FieldTriage]  # field id -> triage


TriageFieldsOutput = TriageFieldsResult | Abstention


# resolve_data (9.3, 9.4).
class ResolvedObservation(StrictModel):
    key: str  # a registry field name
    value: JsonValue
    source: ObservationSource  # derived, fetched or assumed
    evidence: dict[str, JsonValue]  # provider name or derivation id


class BlockerRequest(StrictModel):
    kind: str
    owner: BlockerOwner
    detail: dict[str, JsonValue]


class ResolveDataInput(StrictModel):
    facts: dict[str, JsonValue]
    triage: dict[str, FieldTriage]
    provider_results: dict[str, ProviderResult]  # field -> the lookup the runtime made


class ResolveDataResult(StrictModel):
    observations: list[ResolvedObservation]
    ask_fields: list[str]  # fields left to ask, including the inputs a blocked lookup names
    catalogue_questions: list[str]  # catalogue ids, such as the combined knob-and-tube question
    blockers: list[BlockerRequest]


ResolveDataOutput = ResolveDataResult | Abstention


# evaluate_playbook (9.6).
class EvaluatePlaybookInput(StrictModel):
    facts: dict[str, JsonValue]  # usable facts only; a missing key is unknown
    answered_choices: dict[str, str]  # choice id -> option id
    suppressed_rules: list[str]


EvaluatePlaybookOutput = ActionPlan | Abstention


# plan_asks (10.2).
class PlanAsksInput(StrictModel):
    triage: dict[str, FieldTriage]
    resolved: ResolveDataResult
    plan: ActionPlan
    conflicts: list[ConflictOpened]  # open conflicts, each to be confirmed


class PlanAsksResult(StrictModel):
    asks: list[Ask]


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
