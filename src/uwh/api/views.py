# ABOUTME: Request and response models of the app's HTTP routes (A.5, A.11, section 11), with the checks that tie a blocker, an item and a page to the architecture's rules.
# ABOUTME: Value sets are the Literal types of event_types and settings; the literals defined in this module belong to one view's own shape; no shape holds a model confidence (section 11).
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from uwh.rules.models import (
    ActionPlan,
    NotEvaluatedNote,
    PlannedEffect,
    RuleTrace,
    StrictModel,
)
from uwh.providers.models import ProviderStatus
from uwh.rules.registry import FactField
from uwh.runtime.event_types import (
    Actor,
    BlockerDetail,
    BlockerKind,
    BlockerOwner,
    EventType,
    IntentState,
    MessageKind,
    ObservationSource,
    ObservationStatus,
    Status,
)
from uwh.settings import RunMode
from uwh.skills.read_reply.skill import MAX_BODY_CHARACTERS
from uwh.skills.vertical import refuse_unservable_blocker


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
    example_prompts: list[str]  # the questions the queue conversation offers as buttons


# ---- the queue (section 11) -------------------------------------------------------------------

QueueGroup = Literal["blocked_on_underwriter", "waiting_on_data_or_producer", "finished"]


class QueueRow(StrictModel):
    """One row per lead, in the order the response lists them. The one-sentence summary is
    `GET /api/run`'s `summary`, not part of this response."""

    lead_id: str
    label: str  # the property address, or the lead id when there is none
    status: Status
    primary_next_action: (
        BlockerKind | None
    )  # the highest-priority open blocker (7.1); None when terminal
    waits_on: BlockerOwner | None  # the owner of that blocker
    age_business_days: float  # in simulated time (7.6)
    service_level_breached: bool  # age against the assumed two-business-day service level
    effective_date: str | None  # the lead's effective date, None while missing
    ask_count: int  # the distinct asks put to the producer, across the lead's requests
    decision: str | None  # what the underwriter is asked to decide, in a few words; None otherwise
    request_round: int | None  # the round of the request to the producer that is out
    asked_at: str | None  # the simulated time that request went out
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
    event_id: int  # the event that recorded the observation


class BlockerView(StrictModel):
    """An open blocker. `item_id` is `blockers.id`, the id an `approve` or `reject` names.

    The conversation offers the actions for every open item (section 11), so the blocker carries
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
    ask_ids: list[str]  # the fields and questions the message asks; empty for a packet or a notice
    sent_at: str | None  # the simulated time the message went out


class PlanPage(StrictModel):
    """What the lead's stored plan holds for one playbook page."""

    key: str  # the graph's id, or the note's ref for a page with no graph
    effects: list[PlannedEffect]
    declines_on_every_branch: list[RuleTrace]
    waits_on: list[str]
    not_evaluated: list[NotEvaluatedNote]


class ChoiceReading(StrictModel):
    """What the playbook makes of one value shown with an open choice; `problem` marks a value that
    fails the page or declines."""

    text: str
    problem: bool


class LeadDetail(StrictModel):
    """`GET /api/leads/{id}`. The rule traces are the plan's (`effects[].trace`,
    `declines_on_every_branch`); its open choices and `not_evaluated` notes are the plan's too."""

    lead_id: str
    label: str
    status: Status
    summary: str  # the sentence the conversation opens with
    revision: int
    facts: list[FactView]
    plan: ActionPlan | None  # None until the lead has been triaged
    pages: list[PlanPage]  # the plan grouped by playbook page
    blockers: list[BlockerView]
    drafts: list[DraftView]  # every message of the lead, oldest first
    readings: dict[str, dict[str, ChoiceReading]]  # by open choice id, then by shown field key
    fields: list[
        FactField
    ]  # the keys `resolve_fact` accepts, with the label and type each is offered by
    missing_fields: list[
        str
    ]  # the registry fields the current triage found missing and still needs


# ---- events (A.1) --------------------------------------------------------------------------------


class EventMessage(StrictModel):
    """The words of a sent request (subject and body) or of a received reply (body only)."""

    subject: str | None
    body: str


class LookupView(StrictModel):
    """How a provider lookup went: its status and, when blocked, the inputs it lacked."""

    status: ProviderStatus
    missing_inputs: list[str]


class EventRow(StrictModel):
    """One of a lead's events: its id, type, run mode, actor, simulated time and a summary of its payload.
    `item_id` is the underwriter's item a blocker or approval event names (a wait on the producer or on
    data is no item), `choice_ids` the choices a question card opened with or the one a ruling
    answers, `fact_key` the key a fact event records, `message` the words of a sent request or a
    reply, and `lookup` how a `provider_called` row's lookup went; each is None or empty where the
    event has none."""

    id: int
    type: EventType
    mode: RunMode
    actor: Actor
    sim_ts: str
    summary: str
    item_id: int | None
    choice_ids: list[str]
    fact_key: str | None
    message: EventMessage | None
    lookup: LookupView | None


class LeadEvents(StrictModel):
    lead_id: str
    events: list[EventRow]  # oldest first


# ---- items (section 11, A.11) --------------------------------------------------------------------


class Item(StrictModel):
    """An open item an underwriter acts on: a review, a question card or an unknown delivery. The
    lead's detail carries what its action needs; this row says which lead to open."""

    item_id: int  # `blockers.id`
    lead_id: str
    kind: BlockerKind
    detail: BlockerDetail


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
    reason: str  # optional context; the rejection is the decision


class EditDraftPayload(StrictModel):
    intent_id: str
    subject: str
    body: str
    reason: str


class RecordRulingPayload(StrictModel):
    lead_id: str
    choice_id: str
    option: str
    reason: str  # optional context; the option chosen is the decision (9.6)


class ResolveFactPayload(StrictModel):
    lead_id: str
    key: str
    value: FactValue
    reason: str


class DeclineLeadPayload(StrictModel):
    lead_id: str
    reason: str = Field(min_length=1)  # the reason becomes the plan's trace


class ReplyRequest(StrictModel):
    """`POST /api/replies` and the `deliver_reply` payload; the body is capped at `MAX_BODY_CHARACTERS` (A.9)."""

    lead_id: str
    intent_id: str
    body: str = Field(max_length=MAX_BODY_CHARACTERS)


DeliverReplyPayload = ReplyRequest


class StartRunPayload(StrictModel):
    seed: int


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


# The commands `POST /api/commands` accepts: A.11's rows an underwriter submits, none of them workflow-only and none a proposal.
Command = Annotated[
    ApproveCommand
    | RejectCommand
    | EditDraftCommand
    | RecordRulingCommand
    | ResolveFactCommand
    | DeclineLeadCommand
    | DeliverReplyCommand
    | StartRunCommand,
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
    """A proposal card (A.1). A command proposal's payload is `{type, payload, rationale}`."""

    proposal_id: int
    lead_id: str | None  # the lead the proposed command names; None for a card about no lead
    payload: dict[str, JsonValue]


# ---- chat (section 11) --------------------------------------------------------------------------------


# A chat message is capped so a turn's prompt stays small.
MAX_CHAT_CHARACTERS = 2000


# How many earlier exchanges of the open conversation a message carries.
MAX_CHAT_HISTORY = 4


class ChatExchange(StrictModel):
    """An earlier message of the conversation and what it was answered with: the answer, a card's
    rationale or an error."""

    message: str = Field(max_length=MAX_CHAT_CHARACTERS)
    reply: str = Field(max_length=MAX_CHAT_CHARACTERS)


class ChatRequest(StrictModel):
    """One chat turn: the underwriter's message, the lead whose conversation is open when there is
    one, and the last exchanges of that conversation, oldest first."""

    lead_id: str | None = None
    message: str = Field(min_length=1, max_length=MAX_CHAT_CHARACTERS)
    history: list[ChatExchange] = Field(default=[], max_length=MAX_CHAT_HISTORY)


CitationKind = Literal["event", "fact", "message", "reply", "page", "lead"]


class Citation(StrictModel):
    """What a reference number of one chat turn stands for. `id` is an event id for an `event`, for a
    `fact` (the event that recorded it) and for a `reply` (its `reply_received` event), an intent id
    for a `message`, and a page key for a `page`."""

    number: int
    lead_id: str
    kind: CitationKind
    id: int | str
    text: str  # the source in one line, as the answer lists it: "Fact: Roof material"


class StepEvent(StrictModel):
    """A lookup of the turn has completed: what was read and what it held, in one line."""

    type: Literal["step"]
    summary: str


class AnswerEvent(StrictModel):
    """The turn closed with an answer. A directive the command layer refuses (an approval, a
    rejection, a send) closes this way too, with the reason and no card (7.4, A.11)."""

    type: Literal["answer"]
    answer: str
    citations: list[Citation]  # the cited references the turn's lookups showed


class ProposalEvent(StrictModel):
    """The turn closed with a card: `GET /api/proposals` holds it."""

    type: Literal["proposal"]
    proposal_id: int
    lead_id: str | None  # the lead the card sits on


class ErrorEvent(StrictModel):
    """The turn closed without an answer."""

    type: Literal["error"]
    reason: str


# One event of the `POST /api/chat` stream: any number of steps, then exactly one closing event.
ChatEvent = Annotated[
    StepEvent | AnswerEvent | ProposalEvent | ErrorEvent, Field(discriminator="type")
]
