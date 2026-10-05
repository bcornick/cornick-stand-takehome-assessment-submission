# ABOUTME: The A.5 routes that answer 501, declared with their request and response models.
# ABOUTME: A route declared here answers 501 until its handler exists.
from typing import NoReturn

from fastapi import APIRouter, HTTPException

from uwh.api.views import (
    ChatRequest,
    ChatResponse,
    FixtureRepliesResponse,
    Item,
    LeadDetail,
    LeadEvents,
    ProposalView,
    QueueRow,
    ReplyRequest,
    ReplyResponse,
)

router = APIRouter()


def not_implemented(route: str) -> NoReturn:
    raise HTTPException(status_code=501, detail=f"{route} is not implemented")


@router.get("/api/leads")
def list_leads() -> list[QueueRow]:
    not_implemented("GET /api/leads")


@router.get("/api/leads/{id}")
def get_lead(id: str) -> LeadDetail:
    not_implemented("GET /api/leads/{id}")


@router.get("/api/leads/{id}/events")
def get_lead_events(id: str) -> LeadEvents:
    not_implemented("GET /api/leads/{id}/events")


@router.get("/api/items")
def list_items() -> list[Item]:
    not_implemented("GET /api/items")


@router.post("/api/replies")
def deliver_reply(reply: ReplyRequest) -> ReplyResponse:
    not_implemented("POST /api/replies")


@router.post("/api/replies/fixtures")
def deliver_fixture_replies() -> FixtureRepliesResponse:
    not_implemented("POST /api/replies/fixtures")


@router.get("/api/proposals")
def list_proposals() -> list[ProposalView]:
    not_implemented("GET /api/proposals")


@router.post("/api/chat")
def chat(request: ChatRequest) -> ChatResponse:
    not_implemented("POST /api/chat")
