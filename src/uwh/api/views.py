# ABOUTME: Request and response models of the app's HTTP routes (A.5, A.11, section 11); the OpenAPI file and the web client's types come from them.
# ABOUTME: Vertical vocabularies are typed from uwh.skills.vertical in one place, and no shape holds a model confidence (section 11).
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    JsonValue,
    ValidationError,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from uwh.rules.models import ActionPlan, OpenChoice, RuleTrace, StrictModel
from uwh.runtime.event_types import (
    PAYLOAD_MODELS,
    ApprovalItemKind,
    BlockerDetail,
    BlockerOwner,
    EventType,
    IntentState,
    ObservationSource,
    ObservationStatus,
    ProposalKind,
    ProposalState,
    SkillStatus,
)
from uwh.settings import RUN_MODES
from uwh.skills import vertical


@dataclass(frozen=True)
class Vocabulary:
    """Marks a `str` field as one of a registered vocabulary: checked on validation and an enum
    in the OpenAPI document, so the schema cannot drift from the registration."""

    values: tuple[str, ...]

    def __get_pydantic_core_schema__(
        self, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def check(value: str) -> str:
            if value not in self.values:
                raise ValueError(f"{value!r} is not one of {', '.join(self.values)}")
            return value

        return core_schema.no_info_after_validator_function(check, handler(source))

    def __get_pydantic_json_schema__(
        self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema["enum"] = list(self.values)
        return json_schema


# The vertical's vocabularies (section 7) and the settings' run modes.
Status = Annotated[str, Vocabulary(vertical.STATUSES)]
BlockerKind = Annotated[str, Vocabulary(vertical.BLOCKER_KINDS_BY_PRIORITY)]
MessageKind = Annotated[str, Vocabulary(vertical.MESSAGE_KINDS)]
AutonomyLevel = Annotated[str, Vocabulary(vertical.AUTONOMY_LEVELS)]
CommandClassName = Annotated[str, Vocabulary(tuple(c.name for c in vertical.COMMAND_CLASSES))]
RunMode = Annotated[str, Vocabulary(RUN_MODES)]

# A.11: workflow-only classes are submitted in process and are not accepted over HTTP.
HTTP_COMMAND_TYPES = tuple(c.name for c in vertical.COMMAND_CLASSES if c.actors != ("workflow",))
HttpCommandType = Annotated[str, Vocabulary(HTTP_COMMAND_TYPES)]

# A fact's reported value as a command carries it.
FactValue = str | int | float | bool


# ---- the run (A.5, section 11) ----------------------------------------------------------------


class RunSummary(StrictModel):
    """The one-sentence summary's six counts (section 11)."""

    quotes_sent: int
    follow_ups_sent: int
    declines_approved: int
    waiting_on_underwriter: int
    waiting_on_data: int
    delivery_unknown: int


class RunView(StrictModel):
    """`GET /api/run`; also the reply of `POST /api/run/start`. Before a run starts `run_id` and
    `sim_now` are null and the counts are zero."""

    run_id: str | None
    mode: RunMode
    seed: int
    sim_now: str | None  # simulated time (section 7.6), ISO timestamp
    first_pass_complete: bool  # the run has settled (A.5)
    summary: RunSummary


# ---- the queue (section 11) -------------------------------------------------------------------

QueueGroup = Literal["blocked_on_underwriter", "waiting_on_data_or_producer", "finished"]


class QueueRow(StrictModel):
    """One row per lead, in the order the response lists them. The one-sentence summary is
    `GET /api/run`'s `summary`, not part of this response."""

    lead_id: str
    status: Status
    primary_next_action: (
        BlockerKind | None
    )  # the highest-priority open blocker (7.1); None when terminal
    waits_on: BlockerOwner | None  # the owner of that blocker
    age_business_days: float  # in simulated time (7.6)
    service_level_breached: bool  # age against the assumed two-business-day service level
    effective_date: str | None  # the lead's effective date, None while missing
    ask_count: int
    group: QueueGroup  # the ordering group of section 11


# ---- the lead detail (A.5, A.11, section 11) ------------------------------------------------------


class FactView(StrictModel):
    """An effective fact with its source tag. `p_f` is a fact like any other."""

    key: str
    value: JsonValue
    source: ObservationSource
    status: ObservationStatus
    confirmed: bool
    evidence: dict[str, JsonValue]


PageResult = Literal["decided", "undecided", "not_evaluated"]


class PlaybookPage(StrictModel):
    """One line of the playbook path checklist (section 11). A page that does not apply has no result."""

    page: str  # a decision-graph page id
    applies: bool
    result: PageResult | None
    waits_on: list[str]  # the fields, catalogue ids or choice ids an undecided page waits on
    trace: RuleTrace | None  # the page's rule trace, when it is decided

    @model_validator(mode="after")
    def result_follows_applies(self) -> Self:
        if self.applies != (self.result is not None):
            raise ValueError("result is set exactly when the page applies")
        if (self.result == "undecided") != bool(self.waits_on):
            raise ValueError("waits_on is non-empty exactly when the page is undecided")
        if self.trace is not None and self.result != "decided":
            raise ValueError("only a decided page has a trace")
        return self


NoteKind = Literal["not_evaluated", "unevaluated_skill", "skill_fallback"]


class LeadNote(StrictModel):
    """A non-blocking note (section 11): a page or row not evaluated (4.1), or a skill that is
    unevaluated or on its fallback (section 8). `ref` is a row, page or skill id."""

    kind: NoteKind
    ref: str
    text: str


# A.11: the approvals item kinds of an `underwriter_review` blocker.
_REVIEW_ITEM_KINDS = ("draft", "observation", "no_contact_route", "review")


class BlockerView(StrictModel):
    """An open blocker. `item_id` is `blockers.id`, the id an `approve` or `reject` names."""

    item_id: int
    kind: BlockerKind
    item_kind: ApprovalItemKind | None  # None for a blocker that is not an approvals item
    owner: BlockerOwner
    detail: BlockerDetail

    @model_validator(mode="after")
    def item_kind_fits_the_blocker(self) -> Self:
        if self.item_kind != self.detail.item_kind:
            raise ValueError("item_kind is the detail's item_kind")
        if self.kind == "underwriter_review":
            if self.item_kind not in _REVIEW_ITEM_KINDS:
                raise ValueError(f"an underwriter_review item_kind is one of {_REVIEW_ITEM_KINDS}")
        elif self.kind == "delivery_unknown":
            if self.item_kind != "delivery_unknown":
                raise ValueError("a delivery_unknown blocker has the item_kind delivery_unknown")
        elif self.item_kind is not None:
            raise ValueError(f"a {self.kind} blocker has no item_kind")
        if self.item_kind == "draft" and self.detail.intent_id is None:
            raise ValueError("a draft review names its draft: detail.intent_id")
        if self.item_kind == "review" and self.detail.cause is None:
            raise ValueError("a review states its cause")
        if self.detail.cause_persists and self.item_kind != "review":
            raise ValueError("only a review holds a persistent cause")
        return self


class DraftView(StrictModel):
    """One of the lead's intents (A.1). A reply is accepted only for one in state `sent`."""

    intent_id: str
    payload_hash: str  # the hash an `approve` echoes as `artifact_hash`
    kind: MessageKind
    recipient: str
    subject: str
    body: str
    state: IntentState
    round: int


class OpenChoiceView(OpenChoice):
    """An open underwriter choice with the values of the fields it shows (section 11)."""

    shown_values: dict[str, JsonValue]  # field -> its effective value; None when missing


LinkKind = Literal["search", "map"]


class ExternalLink(StrictModel):
    """A search or map link where the board calls for a human look (section 11)."""

    kind: LinkKind
    label: str
    url: str


class LeadDetail(StrictModel):
    """`GET /api/leads/{id}`. The rule traces are the plan's (`effects[].trace`,
    `declines_on_every_branch`) and the playbook pages'."""

    lead_id: str
    mode: RunMode
    status: Status
    revision: int
    facts: list[FactView]
    plan: ActionPlan | None  # None until the lead has been triaged
    plan_hash: str | None
    playbook: list[PlaybookPage]
    notes: list[LeadNote]
    blockers: list[BlockerView]
    drafts: list[DraftView]
    open_choices: list[OpenChoiceView]
    next_action: str | None  # templated from the plan (section 11); None when terminal
    links: list[ExternalLink]


# ---- events (A.1) --------------------------------------------------------------------------------


class EventRow(StrictModel):
    """An `events` row. `payload` is an object that follows `PAYLOAD_MODELS[type]`; the row checks
    it, so the schema stays one object type rather than 28 row variants."""

    id: int
    run_id: str | None
    mode: RunMode
    lead_id: str | None  # None for a run-level event
    type: EventType
    payload: dict[str, JsonValue]
    actor: str
    ruleset_hash: str | None
    prompt_versions: dict[str, str] | None
    model_id: str | None
    request_id: str | None
    real_ts: str
    sim_ts: str

    @model_validator(mode="after")
    def payload_follows_its_type(self) -> Self:
        try:
            PAYLOAD_MODELS[self.type].model_validate(self.payload)
        except ValidationError as error:
            raise ValueError(f"the payload does not follow {self.type.value}: {error}") from None
        return self


class LeadEvents(StrictModel):
    lead_id: str
    events: list[EventRow]  # oldest first


# ---- items (section 11, A.11) --------------------------------------------------------------------

ReviewItemName = Literal[
    "draft_request",
    "draft_quote_packet",
    "draft_decline_notice",
    "pending_observation",
    "delivery_unknown",
    "no_contact_route",
    "review_raised_by_event",
    "review_cause_persists",
]

# A.11's item table: row -> (blocker kind, approvals item kind).
_REVIEW_ROWS: dict[str, tuple[str, str]] = {
    "draft_request": ("underwriter_review", "draft"),
    "draft_quote_packet": ("underwriter_review", "draft"),
    "draft_decline_notice": ("underwriter_review", "draft"),
    "pending_observation": ("underwriter_review", "observation"),
    "delivery_unknown": ("delivery_unknown", "delivery_unknown"),
    "no_contact_route": ("underwriter_review", "no_contact_route"),
    "review_raised_by_event": ("underwriter_review", "review"),
    "review_cause_persists": ("underwriter_review", "review"),
}


class ReviewItem(BlockerView):
    """An open review: `item` says which A.11 row it is, so the client knows what `approve` and
    `reject` do. A draft row carries the draft whose `payload_hash` an `approve` echoes."""

    type: Literal["review"]
    lead_id: str
    item: ReviewItemName
    draft: DraftView | None = None  # a held draft's review may carry it too
    observation: FactView | None = None  # the pending observation, for that row

    @model_validator(mode="after")
    def row_fits_the_blocker(self) -> Self:
        blocker_kind, item_kind = _REVIEW_ROWS[self.item]
        if (self.kind, self.item_kind) != (blocker_kind, item_kind):
            raise ValueError(f"{self.item} is a {blocker_kind} blocker with item_kind {item_kind}")
        if item_kind == "draft":
            if self.draft is None or self.draft.intent_id != self.detail.intent_id:
                raise ValueError("a draft item carries the draft its blocker reviews: draft")
        if self.item == "pending_observation" and (
            self.observation is None or self.observation.status != "pending_review"
        ):
            raise ValueError("a pending_observation item carries its pending observation")
        if item_kind == "review" and self.detail.cause_persists != (
            self.item == "review_cause_persists"
        ):
            raise ValueError("detail.cause_persists is true exactly for review_cause_persists")
        return self


class QuestionItem(BlockerView):
    """The lead's open choices as one card (section 11). `item_id` is the question blocker's id."""

    type: Literal["question"]
    lead_id: str
    choices: list[OpenChoiceView] = Field(min_length=1)

    @model_validator(mode="after")
    def card_is_a_question_blocker(self) -> Self:
        if self.kind != "underwriter_question":
            raise ValueError("a question item is an underwriter_question blocker")
        if [c.choice_id for c in self.choices] != self.detail.choice_ids:
            raise ValueError("the card holds the choices the blocker names")
        return self


Item = Annotated[ReviewItem | QuestionItem, Field(discriminator="type")]


# ---- commands (A.11) -----------------------------------------------------------------------------


class ApprovePayload(StrictModel):
    item_id: int
    artifact_hash: str | None = None  # the payload hash shown with a draft; omitted for other items
    reason: str


class RejectPayload(StrictModel):
    item_id: int
    reason: str = Field(min_length=1)


class EditDraftPayload(StrictModel):
    intent_id: str
    subject: str
    body: str
    reason: str


class RecordRulingPayload(StrictModel):
    lead_id: str
    choice_id: str
    option: str
    reason: str = Field(min_length=1)  # an underwriter choice requires a reason (9.6)


class ResolveFactPayload(StrictModel):
    lead_id: str
    key: str
    value: FactValue
    reason: str


class DeclineLeadPayload(StrictModel):
    lead_id: str
    reason: str = Field(min_length=1)  # the reason becomes the plan's trace


class ReplyRequest(StrictModel):
    """`POST /api/replies` and the `deliver_reply` payload; the body is capped at 8,000 characters (A.9)."""

    lead_id: str
    intent_id: str
    body: str = Field(max_length=8000)


DeliverReplyPayload = ReplyRequest


class ChangeSettingPayload(StrictModel):
    key: str  # `autonomy.<command_class>`, `emergency_stop` or `ruleset.active`
    value: JsonValue


class EmergencyStopPayload(StrictModel):
    engaged: bool


class StartRunPayload(StrictModel):
    seed: int


class ProposeRuleChangePayload(StrictModel):
    row_id: str
    param: str
    value: FactValue
    reason: str


class ApplyRuleChangePayload(StrictModel):
    proposal_id: int
    diff_hash: str


class ProposeCommandPayload(StrictModel):
    type: HttpCommandType
    payload: dict[str, JsonValue]
    rationale: str


class ApproveCommand(StrictModel):
    type: Literal["approve"]
    payload: ApprovePayload


class RejectCommand(StrictModel):
    type: Literal["reject"]
    payload: RejectPayload


class EditDraftCommand(StrictModel):
    type: Literal["edit_draft"]
    payload: EditDraftPayload


class RecordRulingCommand(StrictModel):
    type: Literal["record_ruling"]
    payload: RecordRulingPayload


class ResolveFactCommand(StrictModel):
    type: Literal["resolve_fact"]
    payload: ResolveFactPayload


class DeclineLeadCommand(StrictModel):
    type: Literal["decline_lead"]
    payload: DeclineLeadPayload


class DeliverReplyCommand(StrictModel):
    type: Literal["deliver_reply"]
    payload: DeliverReplyPayload


class ChangeSettingCommand(StrictModel):
    type: Literal["change_setting"]
    payload: ChangeSettingPayload


class EmergencyStopCommand(StrictModel):
    type: Literal["emergency_stop"]
    payload: EmergencyStopPayload


class StartRunCommand(StrictModel):
    type: Literal["start_run"]
    payload: StartRunPayload


class ProposeRuleChangeCommand(StrictModel):
    type: Literal["propose_rule_change"]
    payload: ProposeRuleChangePayload


class ApplyRuleChangeCommand(StrictModel):
    type: Literal["apply_rule_change"]
    payload: ApplyRuleChangePayload


class ProposeCommandCommand(StrictModel):
    type: Literal["propose_command"]
    payload: ProposeCommandPayload


# The commands `POST /api/commands` accepts: A.11's 13 rows, none of them workflow-only.
Command = Annotated[
    ApproveCommand
    | RejectCommand
    | EditDraftCommand
    | RecordRulingCommand
    | ResolveFactCommand
    | DeclineLeadCommand
    | DeliverReplyCommand
    | ChangeSettingCommand
    | EmergencyStopCommand
    | StartRunCommand
    | ProposeRuleChangeCommand
    | ApplyRuleChangeCommand
    | ProposeCommandCommand,
    Field(discriminator="type"),
]


class CommandResponse(StrictModel):
    accepted: bool
    event_id: int | None  # the event the command produced; None when refused
    reason: str | None  # why it was refused; None when accepted


# ---- replies (A.5, 10.4) ---------------------------------------------------------------------------


class ReplyResponse(CommandResponse):
    """Returned after the reply has been read and the lead re-evaluated, or refused."""

    lead_id: str


class FixtureRepliesResponse(StrictModel):
    replies: list[ReplyResponse]  # one per stored fixture reply, after all are processed


# ---- read views (A.5, A.11, sections 8, 11) -------------------------------------------------------------


class AutonomySetting(StrictModel):
    """The `autonomy.<command_class>` setting of a class autonomy applies to (7.4)."""

    command_class: CommandClassName
    level: AutonomyLevel
    default_level: AutonomyLevel
    locked: bool  # never `auto`


class SettingsView(StrictModel):
    autonomy: list[AutonomySetting]
    emergency_stop: bool
    ruleset_active: str | None  # the `ruleset.active` hash; None for the image's data


class SkillResult(StrictModel):
    """`skill_results.<name>` of the latest scored run row that matches the skill's digest (section 8)."""

    cases_passed: int
    cases_total: int
    passed: bool


class SkillView(StrictModel):
    name: str
    status: SkillStatus
    last_result: SkillResult | None  # None while the skill is untested
    threshold: float
    fallback: str
    rules_changed_since_eval: bool  # A.4: shown beside the status after a rule change


class ProposalView(StrictModel):
    """A `proposals` row (A.1). A command proposal's payload is `{type, payload, rationale}`."""

    proposal_id: int
    kind: ProposalKind
    payload: dict[str, JsonValue]
    diff_hash: str | None
    state: ProposalState
    actor: str
    event_id: int


# ---- chat (section 11) --------------------------------------------------------------------------------


class ChatRequest(StrictModel):
    """One chat turn; the server holds the conversation."""

    message: str


class ChatResponse(StrictModel):
    answer: str
    cited_event_ids: list[int]  # the events a read answer cites
    proposals: list[ProposalView]  # the `propose_command` cards the turn created
