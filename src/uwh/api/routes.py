# ABOUTME: The A.5 routes that answer 501, declared with their request and response models.
# ABOUTME: Each route declared here answers 501 and names itself in the error; the models fix the shape of the answer the route will give.
from typing import NoReturn

from fastapi import APIRouter, HTTPException

from uwh.api.views import (
    ChatRequest,
    ChatResponse,
    ProposalView,
)

router = APIRouter()


def not_implemented(route: str) -> NoReturn:
    raise HTTPException(status_code=501, detail=f"{route} is not implemented")


@router.get("/api/proposals")
def list_proposals() -> list[ProposalView]:
    not_implemented("GET /api/proposals")


@router.post("/api/chat")
def chat(request: ChatRequest) -> ChatResponse:
    not_implemented("POST /api/chat")
