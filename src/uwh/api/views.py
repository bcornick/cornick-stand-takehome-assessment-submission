# ABOUTME: Request and response models of the app's HTTP routes (A.5, A.11, section 11), with the checks that tie a blocker, an item, a page and a proposed command to the architecture's rules.
# ABOUTME: Value sets are the Literal types of event_types and settings; the literals defined in this module belong to one view's own shape; no shape holds a model confidence (section 11).
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import Field, JsonValue, ValidationError, model_validator

from uwh.rules.models import (
    ActionPlan,
    EveryBranchTrace,
    OpenChoice,
    PlannedEffect,
    StrictModel,
)
from uwh.runtime.event_types import (
    PAYLOAD_MODELS,
    Actor,
    ApprovalItemKind,
    BlockerDetail,
    BlockerKind,
    BlockerOwner,
    EventType,
    IntentState,
    MessageKind,
    ObservationSource,
    ObservationStatus,
    ProposalState,
    RequestKind,
    Status,
)
from uwh.settings import RunMode
from uwh.skills.vertical import refuse_unservable_blocker


# A.11: a proposal holds one of six HTTP commands: never approve, reject or another proposal.
ProposableCommandType = Literal[
    "deliver_reply",
    "edit_draft",
    "resolve_fact",
    "decline_lead",
    "record_ruling",
    "start_run",
]

# A fact's reported value as a command carries it.
FactValue = str | int | float | bool


# ---- the run (A.5, section 11) ----------------------------------------------------------------


class RunSummary(StrictModel):
    """The one-sentence summary's seven counts (section 11).

    `follow_ups_sent` counts every request sent to a producer, in any round. The four waiting
    counts count each lead once, by its primary next action: an underwriter review or question, a
    producer reply, a data blocker, or an unknown delivery.
    """

    quotes_sent: int
    follow_ups_sent: int
    declines_approved: int
    waiting_on_underwriter: int
    waiting_on_producer: int
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
    observation_id: int  # `observations.id`, which `BlockerDetail.observation_id` joins on
    is_stub: bool  # a stand-in value, shown as such (9.4)


# Section 9.6's three node results, and the page that was not evaluated.
PageResult = Literal["decided", "undecided", "declines_on_every_branch", "not_evaluated"]


class PlaybookPage(StrictModel):
    """One line of the playbook path checklist (section 11). `applies` is `unknown` when the
    page's `applies_when` rests on an unknown fact: the graph is undecided and contributes
    nothing (9.6). A page that does not apply has no result and no effects. `exception` marks
    what the exceptions-only toggle shows: an undecided page, a decline, a page that applies and
    was not evaluated, or any effect other than `no_action`."""

    graph: str  # a decision-graph id, as `UndecidedPage.graph`
    applies: Literal["yes", "no", "unknown"]
    result: PageResult | None
    waits_on: list[str]  # the fields, catalogue ids or choice ids an undecided page waits on
    effects: list[PlannedEffect]  # an `all_of` page holds several, on separate paths
    declines_on_every_branch: (
        EveryBranchTrace | None
    )  # the trace of that result, one branch per alternative
    exception: bool

    @model_validator(mode="after")
    def result_follows_applies(self) -> Self:
        if self.applies == "no" and (self.result is not None or self.effects):
            raise ValueError("a page whose applies is `no` has no result and no effects")
        if self.applies == "unknown" and self.result != "undecided":
            raise ValueError("a page whose applies is `unknown` is undecided")
        if self.applies == "unknown" and self.effects:
            raise ValueError("a page whose applies is `unknown` contributes no effects")
        if self.applies == "yes" and self.result is None:
            raise ValueError("a page that applies has a result")
        if (self.result == "undecided") != bool(self.waits_on):
            raise ValueError("waits_on is non-empty exactly when the page is undecided")
        if (self.result == "declines_on_every_branch") != (
            self.declines_on_every_branch is not None
        ):
            raise ValueError(
                "declines_on_every_branch is present exactly when that is the page's result"
            )
        expected = self.result in ("undecided", "declines_on_every_branch", "not_evaluated") or any(
            planned.effect.type != "no_action" for planned in self.effects
        )
        if self.exception != expected:
            raise ValueError(f"exception is {expected} for this page")
        return self


NoteKind = Literal["not_evaluated", "unevaluated_skill", "skill_fallback"]


class LeadNote(StrictModel):
    """A non-blocking note (section 11): a page or row not evaluated (4.1), or a skill that is
    unevaluated or on its fallback (section 8). `ref` is a row, page or skill id."""

    kind: NoteKind
    ref: str
    text: str


class BlockerView(StrictModel):
    """An open blocker. `item_id` is `blockers.id`, the id an `approve` or `reject` names.

    The detail pane offers the actions for every open item (section 11), so the blocker carries
    what its action needs: a pending observation's value (`observation`, required exactly for the
    item kind `observation`). The item kind and, for a review, the cause are in `detail`.
    """

    item_id: int
    kind: BlockerKind
    owner: BlockerOwner
    detail: BlockerDetail
    observation: FactView | None  # the pending observation of an `observation` item

    @model_validator(mode="after")
    def item_kind_fits_the_blocker(self) -> Self:
        refuse_unservable_blocker(self.kind, self.detail)
        self._observation_is_the_pending_one()
        return self

    def _observation_is_the_pending_one(self) -> None:
        if self.detail.item_kind != "observation":
            if self.observation is not None:
                raise ValueError("only an observation item carries an observation")
            return
        if self.observation is None:
            raise ValueError("an observation item carries its observation")
        if self.observation.status != "pending_review":
            raise ValueError("the observation of an item is pending_review")
        if self.detail.observation_id != self.observation.observation_id:
            raise ValueError("detail.observation_id is the observation's observation_id")


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
    actor: Actor
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
_REVIEW_ROWS: dict[ReviewItemName, tuple[BlockerKind, ApprovalItemKind]] = {
    "draft_request": ("underwriter_review", "draft"),
    "draft_quote_packet": ("underwriter_review", "draft"),
    "draft_decline_notice": ("underwriter_review", "draft"),
    "pending_observation": ("underwriter_review", "observation"),
    "delivery_unknown": ("delivery_unknown", "delivery_unknown"),
    "no_contact_route": ("underwriter_review", "no_contact_route"),
    "review_raised_by_event": ("underwriter_review", "review"),
    "review_cause_persists": ("underwriter_review", "review"),
}


# The message kinds of the draft each A.11 draft row holds.
_DRAFT_ROW_KINDS: dict[ReviewItemName, tuple[MessageKind, ...]] = {
    "draft_request": get_args(RequestKind),
    "draft_quote_packet": ("quote_packet",),
    "draft_decline_notice": ("decline_notice",),
}


class ReviewItem(BlockerView):
    """An open review: `item` says which A.11 row it is, so the client knows what `approve` and
    `reject` do. A draft row carries the draft whose `payload_hash` an `approve` echoes."""

    type: Literal["review"]
    lead_id: str
    item: ReviewItemName
    draft: DraftView | None = None

    @model_validator(mode="after")
    def row_fits_the_blocker(self) -> Self:
        blocker_kind, item_kind = _REVIEW_ROWS[self.item]
        if (self.kind, self.detail.item_kind) != (blocker_kind, item_kind):
            raise ValueError(f"{self.item} is a {blocker_kind} blocker with item_kind {item_kind}")
        if item_kind == "draft":
            if self.draft is None or self.draft.intent_id != self.detail.intent_id:
                raise ValueError("a draft item carries the draft its blocker reviews: draft")
            if self.draft.kind not in _DRAFT_ROW_KINDS[self.item]:
                raise ValueError(f"{self.item} holds a draft of kind {_DRAFT_ROW_KINDS[self.item]}")
        if self.item == "pending_observation" and self.observation is None:
            raise ValueError("a pending_observation item carries its pending observation")
        # The cause's flag (`BlockerView` checks it) picks the row.
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
    artifact_hash: str | None = Field(
        default=None,
        description=(
            "The payload hash shown with the draft. Required when the item is a draft or a "
            "review that holds a draft, and omitted otherwise. Which item it is, is known to "
            "the handler, so the schema leaves the field optional."
        ),
    )
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


class StartRunPayload(StrictModel):
    seed: int


# The payload models of the six commands a proposal can hold, by command type (A.11).
PROPOSABLE_PAYLOADS: dict[str, type[StrictModel]] = {
    "edit_draft": EditDraftPayload,
    "record_ruling": RecordRulingPayload,
    "resolve_fact": ResolveFactPayload,
    "decline_lead": DeclineLeadPayload,
    "deliver_reply": DeliverReplyPayload,
    "start_run": StartRunPayload,
}

ProposedPayload = (
    EditDraftPayload
    | RecordRulingPayload
    | ResolveFactPayload
    | DeclineLeadPayload
    | DeliverReplyPayload
    | StartRunPayload
)


class ProposeCommandPayload(StrictModel):
    """`{type, payload, rationale}` (A.11): `type` and `payload` together are one of the six
    proposable HTTP commands, never `approve`, `reject` or `propose_command`. The payload is read as
    the model of `type` before the union field sees it."""

    type: ProposableCommandType
    payload: ProposedPayload
    rationale: str

    @model_validator(mode="before")
    @classmethod
    def payload_is_the_models_of_its_type(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("type") in PROPOSABLE_PAYLOADS:
            model = PROPOSABLE_PAYLOADS[data["type"]]
            payload = data.get("payload")
            if isinstance(payload, dict):
                try:
                    payload = model.model_validate(payload)
                except ValidationError as error:
                    raise ValueError(
                        f"the payload is not a {data['type']} payload: {error}"
                    ) from None
                return {**data, "payload": payload}
        return data

    @model_validator(mode="after")
    def payload_is_not_another_commands(self) -> Self:
        if type(self.payload) is not PROPOSABLE_PAYLOADS[self.type]:
            raise ValueError(f"the payload is not a {self.type} payload")
        return self


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


class StartRunCommand(StrictModel):
    type: Literal["start_run"]
    payload: StartRunPayload


class ProposeCommandCommand(StrictModel):
    type: Literal["propose_command"]
    payload: ProposeCommandPayload


# The commands `POST /api/commands` accepts: A.11's nine rows, none of them workflow-only.
Command = Annotated[
    ApproveCommand
    | RejectCommand
    | EditDraftCommand
    | RecordRulingCommand
    | ResolveFactCommand
    | DeclineLeadCommand
    | DeliverReplyCommand
    | StartRunCommand
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


class ProposalView(StrictModel):
    """A `proposals` row (A.1). A command proposal's payload is `{type, payload, rationale}`."""

    proposal_id: int
    payload: dict[str, JsonValue]
    state: ProposalState
    actor: Actor
    event_id: int


# ---- chat (section 11) --------------------------------------------------------------------------------


class ChatRequest(StrictModel):
    """One chat turn; the server holds the conversation."""

    message: str


class ChatResponse(StrictModel):
    """One answer. Asked to approve or reject, the assistant creates no card and points the
    underwriter to the item instead (7.4, A.11): `item_ids` are the items the answer points to."""

    answer: str
    cited_event_ids: list[int]  # the events a read answer cites
    proposals: list[ProposalView]  # the `propose_command` cards the turn created
    item_ids: list[int]  # the items (`blockers.id`) the answer points the underwriter to
