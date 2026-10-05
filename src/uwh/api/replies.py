# ABOUTME: POST /api/replies and POST /api/replies/fixtures (A.5, 10.4): deliver a reply as the inbound actor the transport binds, and deliver every stored fixture reply of the run.
# ABOUTME: Each returns after the reply has been read and its lead re-evaluated; a refused delivery is a response with its reason, as for a command.
import sqlite3
from pathlib import Path

from fastapi import APIRouter

from uwh.api.runtime import Runtime, RuntimeDependency
from uwh.api.views import FixtureRepliesResponse, ReplyRequest, ReplyResponse
from uwh.runtime.event_types import REQUEST_KINDS
from uwh.skills.read_reply.skill import MAX_BODY_CHARACTERS

router = APIRouter()


def _deliver(runtime: Runtime, db: sqlite3.Connection, reply: ReplyRequest) -> ReplyResponse:
    result = runtime.submit_as_inbound(db, "deliver_reply", reply.model_dump(mode="json"))
    return ReplyResponse(
        accepted=result.accepted,
        event_id=result.event_id if result.accepted else None,
        reason=result.reason,
        lead_id=reply.lead_id,
    )


def _fixture_reply(runtime: Runtime, db: sqlite3.Connection, fixture: Path) -> ReplyResponse:
    """Deliver the fixture, named for its lead, to the lead's latest sent request."""
    lead_id = fixture.stem
    placeholders = ", ".join("?" for _ in REQUEST_KINDS)
    row = db.execute(
        f"SELECT id FROM intents WHERE lead_id = ? AND state = 'sent' AND kind IN ({placeholders})"
        " ORDER BY round DESC LIMIT 1",
        (lead_id, *REQUEST_KINDS),
    ).fetchone()
    if row is None:
        return ReplyResponse(
            accepted=False,
            event_id=None,
            reason=f"lead {lead_id} has no sent request in this run",
            lead_id=lead_id,
        )
    body = fixture.read_text(encoding="utf-8")
    if len(body) > MAX_BODY_CHARACTERS:
        return ReplyResponse(
            accepted=False,
            event_id=None,
            reason=f"the fixture reply is longer than {MAX_BODY_CHARACTERS} characters",
            lead_id=lead_id,
        )
    return _deliver(runtime, db, ReplyRequest(lead_id=lead_id, intent_id=row[0], body=body))


# The handlers carry no docstring: FastAPI copies one into the OpenAPI document.
@router.post("/api/replies")
def deliver_reply(reply: ReplyRequest, runtime: RuntimeDependency) -> ReplyResponse:
    with runtime.database() as db:
        return _deliver(runtime, db, reply)


@router.post("/api/replies/fixtures")
def deliver_fixture_replies(runtime: RuntimeDependency) -> FixtureRepliesResponse:
    fixtures = sorted(Path(runtime.settings.fixture_replies_dir).glob("*.txt"))
    with runtime.database() as db:
        return FixtureRepliesResponse(
            replies=[_fixture_reply(runtime, db, fixture) for fixture in fixtures]
        )
