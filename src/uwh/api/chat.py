# ABOUTME: The chat routes (A.5, section 11): POST /api/chat runs one chat turn and answers as a server-sent-events stream, GET /api/proposals lists the open cards, and a card is applied or dismissed.
# ABOUTME: A turn runs in a worker thread of its own, so a closed tab lets it finish; applying a card submits its command as the underwriter, the actor the REST transport binds.
import asyncio
import logging
import sqlite3
import threading
from collections.abc import AsyncIterable, Callable

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse

from uwh.api.runtime import Runtime, RuntimeDependency
from uwh.api.views import (
    AnswerEvent,
    ChatEvent,
    ChatRequest,
    CommandResponse,
    ErrorEvent,
    ProposalEvent,
    ProposalView,
    StepEvent,
)
from uwh.chat.examples import EXAMPLE_PROMPTS
from uwh.chat.skill import run_turn
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.proposals import Proposal, open_proposals, read_proposal, settle_proposal

logger = logging.getLogger(__name__)

# What a turn closes with in replay: nothing recorded answers a typed question.
NEEDS_LIVE_MODE = "Questions need live mode"


def _is_example(request: ChatRequest) -> bool:
    """An example prompt asked first in the queue conversation: the one turn replay has recordings for."""
    return request.message in EXAMPLE_PROMPTS and request.lead_id is None and not request.history


router = APIRouter()


def _view(card: Proposal) -> ProposalView:
    return ProposalView(proposal_id=card.id, lead_id=card.lead_id, payload=card.payload)


def _open_card(db: sqlite3.Connection, proposal_id: int) -> Proposal:
    card = read_proposal(db, proposal_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"no proposal {proposal_id}")
    if card.state != "open":
        raise HTTPException(status_code=409, detail=f"proposal {proposal_id} is {card.state}")
    return card


def _closing_event(
    runtime: Runtime, request: ChatRequest, on_step: Callable[[str], None]
) -> AnswerEvent | ProposalEvent | ErrorEvent:
    """Run the turn on a connection of this thread and say how it closed."""
    if runtime.env.mode == "replay" and not _is_example(request):
        return ErrorEvent(type="error", reason=NEEDS_LIVE_MODE)
    if not runtime.env.model.available:
        return ErrorEvent(type="error", reason="The assistant has no model key")
    with runtime.database() as db:
        try:
            turn = run_turn(
                db, runtime.env, request.message, request.lead_id, request.history, on_step
            )
        except RecordingMiss:
            # The examples were recorded on the day as first loaded; a day that has moved on misses.
            return ErrorEvent(type="error", reason=NEEDS_LIVE_MODE)
        except anthropic.APIError as error:
            return ErrorEvent(type="error", reason=f"The model call failed: {error}")
        if turn.proposal_id is not None:
            card = read_proposal(db, turn.proposal_id)
            assert card is not None  # the turn stored it
            return ProposalEvent(type="proposal", proposal_id=card.id, lead_id=card.lead_id)
    assert turn.answer is not None  # a turn with no card has an answer
    return AnswerEvent(type="answer", answer=turn.answer, citations=turn.citations)


# The handlers carry no docstring: FastAPI copies one into the OpenAPI document.
@router.post("/api/chat", response_class=EventSourceResponse)
async def chat(request: ChatRequest, runtime: RuntimeDependency) -> AsyncIterable[ChatEvent]:
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[ChatEvent] = asyncio.Queue()

    def emit(event: ChatEvent) -> None:
        loop.call_soon_threadsafe(events.put_nowait, event)

    def turn() -> None:
        closing: ChatEvent
        try:
            closing = _closing_event(
                runtime, request, lambda line: emit(StepEvent(type="step", summary=line))
            )
        except Exception as error:
            # The stream ends with a closing event whatever the turn raised.
            logger.exception("the chat turn failed")
            closing = ErrorEvent(type="error", reason=f"The assistant failed: {error}")
        emit(closing)

    threading.Thread(target=turn, name="chat-turn").start()
    while True:
        event = await events.get()
        yield event
        if not isinstance(event, StepEvent):
            return


@router.get("/api/proposals")
def list_proposals(runtime: RuntimeDependency) -> list[ProposalView]:
    with runtime.database() as db:
        return [_view(card) for card in open_proposals(db)]


@router.post("/api/proposals/{proposal_id}/apply")
def apply_proposal(proposal_id: int, runtime: RuntimeDependency) -> CommandResponse:
    with runtime.database() as db:
        card = _open_card(db, proposal_id)
        command = card.payload
        assert isinstance(command["type"], str) and isinstance(command["payload"], dict)
        result, _ = runtime.submit_as_underwriter(db, command["type"], command["payload"])
        if result.accepted:
            settle_proposal(db, proposal_id, "applied")
    return CommandResponse(accepted=result.accepted, event_id=result.event_id, reason=result.reason)


@router.post("/api/proposals/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: int, runtime: RuntimeDependency) -> None:
    with runtime.database() as db:
        _open_card(db, proposal_id)
        settle_proposal(db, proposal_id, "dismissed")
