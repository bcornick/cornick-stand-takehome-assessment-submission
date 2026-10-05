# ABOUTME: POST /api/commands (A.5, A.11): submits a typed command as the underwriter, the actor the REST transport binds, and returns the A.11 response.
# ABOUTME: The Command model admits only the commands an underwriter may submit, so a workflow-only class never reaches the command layer; a command whose handler is not built answers 501.
from fastapi import APIRouter, HTTPException

from uwh.api.runtime import RuntimeDependency
from uwh.api.views import Command, CommandResponse

router = APIRouter()


# The handler carries no docstring: FastAPI copies one into the OpenAPI document.
@router.post("/api/commands")
def submit_command(command: Command, runtime: RuntimeDependency) -> CommandResponse:
    with runtime.database() as db:
        try:
            result, _ = runtime.submit_as_underwriter(
                db, command.type, command.payload.model_dump(mode="json")
            )
        except NotImplementedError as error:
            raise HTTPException(status_code=501, detail=str(error)) from error
    return CommandResponse(accepted=result.accepted, event_id=result.event_id, reason=result.reason)
