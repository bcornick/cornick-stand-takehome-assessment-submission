# ABOUTME: The A.5 routes other than GET /api/run, declared with their request and response models; each answers 501.
# ABOUTME: `/mcp` is mounted outside OpenAPI and is not declared here.
from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, HTTPException

from uwh.api.views import (
    ChatRequest,
    ChatResponse,
    Command,
    CommandResponse,
    FixtureRepliesResponse,
    Item,
    LeadDetail,
    LeadEvents,
    ProposalView,
    QueueRow,
    ReplyRequest,
    ReplyResponse,
    RunView,
    SettingsView,
    SkillView,
)

router = APIRouter()


def not_implemented(route: str) -> NoReturn:
    raise HTTPException(status_code=501, detail=f"{route} is not implemented")


@router.post("/api/run/start")
def start_run(wait: bool = False) -> RunView:
    not_implemented("POST /api/run/start")


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


@router.post("/api/commands")
def submit_command(command: Command) -> CommandResponse:
    not_implemented("POST /api/commands")


@router.post("/api/replies")
def deliver_reply(reply: ReplyRequest) -> ReplyResponse:
    not_implemented("POST /api/replies")


@router.post("/api/replies/fixtures")
def deliver_fixture_replies() -> FixtureRepliesResponse:
    not_implemented("POST /api/replies/fixtures")


@router.get("/api/settings")
def get_settings() -> SettingsView:
    not_implemented("GET /api/settings")


@router.get("/api/skills")
def list_skills() -> list[SkillView]:
    not_implemented("GET /api/skills")


@router.get("/api/proposals")
def list_proposals() -> list[ProposalView]:
    not_implemented("GET /api/proposals")


@router.post("/api/chat")
def chat(request: ChatRequest) -> ChatResponse:
    not_implemented("POST /api/chat")


@router.get(
    "/api/events/stream",
    response_model=None,
    responses={
        200: {
            "description": "Server-sent events; each carries an event id.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_events(
    last_event_id: Annotated[str | None, Header()] = None,
) -> None:
    not_implemented("GET /api/events/stream")
