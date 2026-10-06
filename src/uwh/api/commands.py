# ABOUTME: POST /api/commands (A.5, A.11): submits a typed command as the underwriter, the actor the REST transport binds, and returns the A.11 response.
# ABOUTME: The Command model admits only the commands an underwriter submits itself: a workflow-only class never reaches the command layer, and neither does a proposal, which only the assistant makes.
from fastapi import APIRouter

from uwh.api.runtime import RuntimeDependency
from uwh.api.views import Command, CommandResponse

router = APIRouter()


# The handler carries no docstring: FastAPI copies one into the OpenAPI document.
@router.post("/api/commands")
def submit_command(command: Command, runtime: RuntimeDependency) -> CommandResponse:
    with runtime.database() as db:
        result, _ = runtime.submit_as_underwriter(
            db, command.type, command.payload.model_dump(mode="json")
        )
    return CommandResponse(accepted=result.accepted, event_id=result.event_id, reason=result.reason)
