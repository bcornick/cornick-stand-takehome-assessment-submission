# ABOUTME: Rules-core domain models: field triage, effects, deadlines, node results, rule traces, the action plan and asks.
# ABOUTME: Sections 9.2, 9.6, 9.7 and 10.2 fix the names; this module imports nothing from the rest of uwh.
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictModel(BaseModel):
    """Base of every contract model and event payload: unknown fields are an error."""

    # A defaulted field is always present in what the model serializes, so the generated client
    # types it as present rather than optional.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


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
    percent: Annotated[int, Field(strict=True)]  # a whole number, as A.6 writes it
    deadline: Deadline | None = None  # how long the modification applies (I56)


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
    deadline: Deadline | None = None  # how long the modification applies (I56)


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


class Assumption(StrictModel):
    """One unknown input and the case taken for it, in A.6's condition form."""

    field: str  # the registry field, derived input or catalogue id that was unknown
    when: dict[str, JsonValue]  # for example {"equals": true}, {"lt": 2000}, {"gt": 8, "lte": 12}


class TraceBranch(StrictModel):
    """One alternative of a decline on every branch: the cases taken for the unknown inputs and the path that follows."""

    assumed: list[Assumption] = Field(
        min_length=1
    )  # root to leaf; one alternative may rest on several
    board_path: list[str]  # root to this branch's outcome
    rule: str  # the decline's rule id on this branch


class RuleTrace(StrictModel):
    """Either one path or a set of alternatives, never both."""

    board_path: list[str]  # the concatenation of `board_path` values from root to outcome
    # Non-empty only for a decline reached as `declines_on_every_branch`; then `board_path` is empty
    # and each branch carries its own full path.
    alternatives: list[TraceBranch] = []
    # The underwriter choices answered on the path (A.11: rejecting a decline notice that followed
    # a choice reopens it); for alternatives, the choices answered above the first unknown.
    choice_ids: list[str] = []

    @model_validator(mode="after")
    def is_a_path_or_alternatives(self) -> Self:
        if bool(self.board_path) == bool(self.alternatives):
            raise ValueError("a trace holds exactly one of board_path and alternatives")
        return self


def _carries_alternatives(trace: RuleTrace) -> RuleTrace:
    if not trace.alternatives:
        raise ValueError("a decline on every branch carries one trace per branch")
    return trace


# The trace of a decline on every branch: it holds alternatives, one per branch.
EveryBranchTrace = Annotated[RuleTrace, AfterValidator(_carries_alternatives)]


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
    trace: EveryBranchTrace


NodeResult = Annotated[Decided | Undecided | DeclinesOnEveryBranch, Field(discriminator="result")]


# Section 10.2.
class AskKind(StrEnum):
    field_request = "field_request"
    follow_on_question = "follow_on_question"
    catalogue_question = "catalogue_question"
    confirmation = "confirmation"
    document_request = "document_request"


class Ask(StrictModel):
    """One typed ask (10.2).

    `ask_id` is a registry field name, a bare catalogue id (`kt_extent`) or a validator id.
    `fields` holds fact keys (A.1): a registry field name, or for a catalogue question the
    catalogue id prefixed `q:` (`q:kt_extent`). A confirmation lists the fields its validator covers.
    """

    ask_id: str  # a registry field name, a bare catalogue id or a validator id (A.9)
    kind: AskKind
    fields: list[str]  # fact keys: field names, `q:`-prefixed catalogue ids
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
    """The plan of section 9.6. The plan hash (A.4) is taken over `model_dump(mode="json")`, so
    equal plans hold every list in one stable order."""

    effects: list[
        PlannedEffect
    ] = []  # one per effect type and rule id; advisories, ladder rungs and suppression notes included
    declines_on_every_branch: list[EveryBranchTrace] = []  # each trace carries its alternatives
    # True exactly when the plan holds a committed decline effect, a decline on every branch, or
    # the underwriter's own decline.
    proposed_decline: bool = False
    underwriter_decline: str | None = None  # the reason of a `decline_lead` ruling (A.11)
    undecided: list[UndecidedPage] = []
    open_choices: list[OpenChoice] = []
    catalogue_questions: list[str] = []  # catalogue ids, document requests included
    not_evaluated: list[NotEvaluatedNote] = []

    @model_validator(mode="after")
    def declines_state_the_proposed_decline(self) -> Self:
        declines = (
            any(p.committed and isinstance(p.effect, DeclineEffect) for p in self.effects)
            or bool(self.declines_on_every_branch)
            or self.underwriter_decline is not None
        )
        if self.proposed_decline != declines:
            raise ValueError(
                "proposed_decline is true exactly when the plan holds a committed decline, "
                "a decline on every branch or the underwriter's decline"
            )
        return self

    @model_validator(mode="after")
    def effects_are_unique_by_type_and_rule(self) -> Self:
        seen: set[tuple[str, str]] = set()
        for planned in self.effects:
            key = (planned.effect.type, planned.effect.rule)
            if key in seen:
                raise ValueError(
                    f"effects hold one {key[0]} effect for rule {key[1]}, "
                    "deduplicated by effect type and rule id"
                )
            seen.add(key)
        return self

    @model_validator(mode="after")
    def lists_are_in_a_stable_order(self) -> Self:
        self.effects.sort(key=lambda p: (p.effect.rule, p.effect.type))
        self.declines_on_every_branch.sort(
            key=lambda t: (t.alternatives[0].rule, t.alternatives[0].board_path)
        )
        self.undecided = sorted(
            (
                page.model_copy(update={"waits_on": sorted(set(page.waits_on))})
                for page in self.undecided
            ),
            key=lambda page: page.graph,
        )
        self.open_choices.sort(key=lambda c: c.choice_id)
        self.catalogue_questions = sorted(set(self.catalogue_questions))
        self.not_evaluated.sort(key=lambda n: n.ref)
        return self
