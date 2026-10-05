# ABOUTME: Rules-core domain models: field triage, effects, deadlines, node results, rule traces, the action plan and asks.
# ABOUTME: Sections 9.2, 9.6, 9.7 and 10.2 fix the names; this module imports nothing from the rest of uwh.
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictModel(BaseModel):
    """Base of every contract model: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


# Section 9.2.
class ValueStatus(StrEnum):
    present = "present"
    missing = "missing"
    conflicting = "conflicting"
    unsupported = "unsupported"


class Requirement(StrEnum):
    required = "required"
    conditional_active = "conditional_active"
    conditional_inactive = "conditional_inactive"
    conditional_unknown = "conditional_unknown"
    bind_only = "bind_only"
    optional = "optional"


class Resolution(StrEnum):
    none = "none"
    derive = "derive"
    fetch = "fetch"
    assume = "assume"
    ask = "ask"
    ask_follow_on = "ask_follow_on"
    defer = "defer"
    verify = "verify"
    not_required = "not_required"
    blocked = "blocked"


class FieldTriage(StrictModel):
    value_status: ValueStatus
    requirement: Requirement
    resolution: Resolution
    depends_on: list[str]  # field ids


# Section 9.6: a typed enum, never converted from one to another.
class Deadline(StrEnum):
    within_60_days = "within_60_days"
    first_term = "first_term"
    underwriting_period = "underwriting_period"
    within_30_days_of_bind = "within_30_days_of_bind"
    duration_of_non_occupancy = "duration_of_non_occupancy"


# Section 9.6 effects. `type` is the discriminator and `rule` the rule id, as the A.6 example writes them.
class DeclineEffect(StrictModel):
    type: Literal["decline"]
    rule: str


class RequirementEffect(StrictModel):
    type: Literal["requirement"]
    rule: str
    text: str
    deadline: Deadline | None = None  # a requirement may carry no deadline


class SurchargeEffect(StrictModel):
    type: Literal["surcharge"]
    rule: str
    percent: int | float


class ExclusionOrEndorsementEffect(StrictModel):
    type: Literal["exclusion_or_endorsement"]
    rule: str
    text: str


class CoverageAdjustmentEffect(StrictModel):
    """A proposed value for a coverage field; the submitted value stays with the facts."""

    type: Literal["coverage_adjustment"]
    rule: str
    field: str
    proposed_value: str | int | float | bool


class AdvisoryEffect(StrictModel):
    type: Literal["advisory"]
    rule: str
    text: str


class ObligationEffect(StrictModel):
    """A post-bind obligation; recorded and never executed."""

    type: Literal["obligation"]
    rule: str
    text: str
    owner: str
    trigger: str


class NoActionEffect(StrictModel):
    type: Literal["no_action"]
    rule: str


Effect = Annotated[
    DeclineEffect
    | RequirementEffect
    | SurchargeEffect
    | ExclusionOrEndorsementEffect
    | CoverageAdjustmentEffect
    | AdvisoryEffect
    | ObligationEffect
    | NoActionEffect,
    Field(discriminator="type"),
]


class TraceBranch(StrictModel):
    """One alternative of a decline on every branch: the value assumed for the unknown input and the path that follows."""

    field: str  # the field or catalogue id that was unknown
    assumed_value: JsonValue
    board_path: list[str]  # root to this branch's outcome
    rule: str  # the decline's rule id on this branch


class RuleTrace(StrictModel):
    board_path: list[str]  # the concatenation of `board_path` values from root to outcome
    # Non-empty only for a decline reached as `declines_on_every_branch`.
    alternatives: list[TraceBranch] = []


# Section 9.6 node results.
class Decided(StrictModel):
    result: Literal["decided"]
    effects: list[Effect]


class Undecided(StrictModel):
    result: Literal["undecided"]
    waits_on: list[str] = Field(min_length=1)  # fields, catalogue ids or choice ids
    effects: list[Effect] = []  # effects of decided children of an `all_of`, which stay committed
    possible_effects: list[
        Effect
    ] = []  # effects beneath an unanswered choice: possible, not committed


class DeclinesOnEveryBranch(StrictModel):
    result: Literal["declines_on_every_branch"]
    trace: RuleTrace

    @model_validator(mode="after")
    def carries_alternatives(self) -> Self:
        if not self.trace.alternatives:
            raise ValueError("a decline on every branch carries one trace per branch")
        return self


NodeResult = Annotated[Decided | Undecided | DeclinesOnEveryBranch, Field(discriminator="result")]


# Section 10.2.
class AskKind(StrEnum):
    field_request = "field_request"
    follow_on_question = "follow_on_question"
    catalogue_question = "catalogue_question"
    confirmation = "confirmation"
    document_request = "document_request"


class Ask(StrictModel):
    ask_id: str  # a field name, a catalogue id or a validator id (A.9)
    kind: AskKind
    fields: list[
        str
    ]  # the field or catalogue id; a confirmation lists the fields its validator covers
    reason: str
    wording: str  # stored plain wording


# Section 9.6 action plan.
class PlannedEffect(StrictModel):
    effect: Effect
    trace: RuleTrace
    committed: bool  # False beneath an unanswered underwriter choice


class UndecidedPage(StrictModel):
    graph: str
    waits_on: list[str]


class OpenChoice(StrictModel):
    choice_id: str  # section 9.7
    options: list[str]  # option ids
    prompt: str  # A.6
    show: list[str]  # the fields shown with the choice (A.6)


class NotEvaluatedNote(StrictModel):
    ref: str  # an interpretation row id or a page id
    text: str


class ActionPlan(StrictModel):
    effects: list[
        PlannedEffect
    ] = []  # deduplicated by rule id; advisories, ladder rungs and suppression notes included
    declines_on_every_branch: list[RuleTrace] = []  # each trace carries its alternatives
    proposed_decline: bool = False
    undecided: list[UndecidedPage] = []
    open_choices: list[OpenChoice] = []
    catalogue_questions: list[str] = []  # catalogue ids, document requests included
    not_evaluated: list[NotEvaluatedNote] = []
