# ABOUTME: The chat panel's routes (A.5, section 11): POST /api/chat runs one chat turn, GET /api/proposals lists the open cards, and a card is applied or dismissed.
# ABOUTME: Applying a card submits its command as the underwriter, the actor the REST transport binds, and marks the card applied when the command is accepted.
import sqlite3

import anthropic
from fastapi import APIRouter, HTTPException

from uwh.api.runtime import RuntimeDependency
from uwh.api.views import ChatRequest, ChatResponse, CommandResponse, ProposalView
from uwh.chat.skill import run_turn
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.proposals import Proposal, open_proposals, read_proposal, settle_proposal

router = APIRouter()


def _view(card: Proposal) -> ProposalView:
    return ProposalView(proposal_id=card.id, payload=card.payload)


def _open_card(db: sqlite3.Connection, proposal_id: int) -> Proposal:
    card = read_proposal(db, proposal_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"no proposal {proposal_id}")
    if card.state != "open":
        raise HTTPException(status_code=409, detail=f"proposal {proposal_id} is {card.state}")
    return card


# The handlers carry no docstring: FastAPI copies one into the OpenAPI document.
@router.post("/api/chat")
def chat(request: ChatRequest, runtime: RuntimeDependency) -> ChatResponse:
    if not runtime.env.model.available:
        raise HTTPException(status_code=503, detail="the assistant is unavailable: no model key")
    with runtime.database() as db:
        try:
            turn = run_turn(db, runtime.env, request.message, request.lead_id)
        except RecordingMiss as miss:
            raise HTTPException(status_code=409, detail=str(miss)) from miss
        except anthropic.APIError as error:
            raise HTTPException(
                status_code=502, detail=f"the model call failed: {error}"
            ) from error
        card = None if turn.proposal_id is None else read_proposal(db, turn.proposal_id)
    return ChatResponse(
        answer=turn.answer,
        cited_event_ids=turn.cited_event_ids,
        proposal=None if card is None else _view(card),
    )


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
