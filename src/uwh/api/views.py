# ABOUTME: Request and response models of the app's HTTP routes (A.5, A.11, section 11), with the checks that tie a blocker, an item, a page and a proposed command to the architecture's rules.
# ABOUTME: Value sets are the Literal types of event_types and settings; the literals defined in this module belong to one view's own shape; no shape holds a model confidence (section 11).
from typing import Annotated, Any, Literal, Self

from pydantic import Field, JsonValue, ValidationError, model_validator

from uwh.rules.models import (
    ActionPlan,
    StrictModel,
)
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
    ProposalState,
    Status,
)
from uwh.settings import RunMode
from uwh.skills.read_reply.skill import MAX_BODY_CHARACTERS
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


class LeadDetail(StrictModel):
    """`GET /api/leads/{id}`. The rule traces are the plan's (`effects[].trace`,
    `declines_on_every_branch`); its open choices and `not_evaluated` notes are the plan's too."""

    lead_id: str
    label: str
    status: Status
    revision: int
    facts: list[FactView]
    plan: ActionPlan | None  # None until the lead has been triaged
    blockers: list[BlockerView]
    drafts: list[DraftView]  # every message of the lead, oldest first


# ---- events (A.1) --------------------------------------------------------------------------------


class EventRow(StrictModel):
    """One of a lead's events: its id, type, actor, simulated time and a one-line summary of its payload."""

    id: int
    type: EventType
    actor: Actor
    sim_ts: str
    summary: str


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
    """`POST /api/replies` and the `deliver_reply` payload; the body is capped at `MAX_BODY_CHARACTERS` (A.9)."""

    lead_id: str
    intent_id: str
    body: str = Field(max_length=MAX_BODY_CHARACTERS)


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
