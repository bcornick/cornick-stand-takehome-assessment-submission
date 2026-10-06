# ABOUTME: The chat skill (section 11, A.11): a bounded loop of forced tool calls in which the model looks something up, answers, or proposes a command, and code runs the read tools and submits `propose_command` as the assistant.
# ABOUTME: A turn is at most MAX_STEPS calls. An answer cites only event ids a tool showed this turn, and a proposal executes nothing: the command layer stores a card or refuses it.
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import JsonValue, ValidationError, model_validator

from uwh.chat.tools import READ_TOOLS
from uwh.rules.models import StrictModel
from uwh.runtime.commands import submit_command
from uwh.runtime.event_types import EventType, ModelCalled, ReplayMiss
from uwh.runtime.events import append_event
from uwh.runtime.model import ForcedToolCall
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.recordings import Exchange
from uwh.runtime.runs import RunEnvironment, command_context
from uwh.runtime.workflow import unit_of_work

TOOL_NAME = "chat_step"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")

# The calls one turn may make: a few reads and the answer, or one proposal. The cap is fixed; there is no retry loop.
MAX_STEPS = 4

# What the panel says when a turn ends without an answer of the model's own.
NO_ANSWER_IN_STEPS = "I could not finish looking that up. Ask again with a narrower question."
UNREADABLE_STEP = "I could not read the assistant's reply. Ask again."


# The tool input of a chat step. `action` picks what the step does; the other fields belong to one action each.
class ChatStep(StrictModel):
    action: Literal["lead_events", "lead_summary", "open_items", "answer", "propose_command"]
    lead_id: str | None = None
    answer: str | None = None
    cited_event_ids: list[int] = []
    command_type: str | None = None
    command_payload: dict[str, str | int | float | bool] | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _has_what_its_action_needs(self) -> Self:
        needed: dict[str, tuple[str, ...]] = {
            "lead_events": ("lead_id",),
            "lead_summary": ("lead_id",),
            "open_items": (),
            "answer": ("answer",),
            "propose_command": ("command_type", "command_payload", "rationale"),
        }
        missing = [name for name in needed[self.action] if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.action} needs {', '.join(missing)}")
        return self


@dataclass(frozen=True)
class TurnResult:
    answer: str
    cited_event_ids: list[int]
    proposal_id: int | None  # the card a proposal created
    exchanges: list[Exchange]


def forced_call(shown: dict[str, Any]) -> ForcedToolCall:
    """The call: the model is shown the message, the open lead and what this turn has done so far."""
    return ForcedToolCall(
        skill="chat",
        prompt_file=_PROMPT_FILE,
        shown=shown,
        tool_name=TOOL_NAME,
        tool_description="Look something up, answer the underwriter, or propose a command.",
        tool_schema=ChatStep.model_json_schema(),
    )


def _next_step(
    shown: dict[str, Any], env: RunEnvironment
) -> tuple[ChatStep | None, list[Exchange]]:
    """The model's next step with the exchange of each call made. A tool input that fails validation
    repeats the call once; a second failure, or a refusal, gives no step."""
    call = forced_call(shown)
    exchanges: list[Exchange] = []
    for _ in range(2):
        exchange = env.model.exchange(call)
        exchanges.append(exchange)
        if exchange.stop_reason == "refusal":
            return None, exchanges
        try:
            return ChatStep.model_validate(exchange.tool_input), exchanges
        except ValidationError:
            continue
    return None, exchanges


def _propose(db: sqlite3.Connection, env: RunEnvironment, step: ChatStep) -> tuple[str, int | None]:
    """Submit the step's proposal as the assistant. The answer says what the command layer did: the
    card it stored, or why it refused."""
    command_payload: dict[str, JsonValue] = dict(step.command_payload or {})
    result = submit_command(
        db,
        env,
        "assistant",
        "propose_command",
        {"type": step.command_type, "payload": command_payload, "rationale": step.rationale},
    )
    if not result.accepted:
        return f"I cannot propose that: {result.reason}.", None
    row = db.execute("SELECT id FROM proposals WHERE event_id = ?", (result.event_id,)).fetchone()
    return f"Proposed: {step.rationale} Review the card and apply it, or dismiss it.", row[0]


def _record_model_calls(
    db: sqlite3.Connection, env: RunEnvironment, lead_id: str | None, exchanges: list[Exchange]
) -> None:
    with unit_of_work(db):
        context = command_context(db, "assistant", env.mode, env.ruleset_hash, env.now())
        for exchange in exchanges:
            append_event(
                db,
                context,
                EventType.model_called,
                ModelCalled(
                    skill=exchange.skill,
                    prompt_version=exchange.prompt_version,
                    input_hash=exchange.input_hash,
                    tokens_in=exchange.tokens_in,
                    tokens_out=exchange.tokens_out,
                    stop_reason=exchange.stop_reason,
                ),
                lead_id=lead_id,
                model_id=exchange.model_id,
                request_id=exchange.request_id or None,
                prompt_versions={exchange.skill: exchange.prompt_version},
            )


def _record_miss(db: sqlite3.Connection, env: RunEnvironment, miss: RecordingMiss) -> None:
    with unit_of_work(db):
        append_event(
            db,
            command_context(db, "assistant", env.mode, env.ruleset_hash, env.now()),
            EventType.replay_miss,
            ReplayMiss(
                skill=miss.key.skill,
                prompt_version=miss.key.prompt_version,
                input_hash=miss.key.input_hash,
            ),
            lead_id=None,
        )


def run_turn(
    db: sqlite3.Connection, env: RunEnvironment, message: str, lead_id: str | None
) -> TurnResult:
    """One chat turn. The model reads through the tools until it answers or proposes, at most
    MAX_STEPS calls. A replay with no recording for a call records the miss and raises RecordingMiss."""
    steps: list[dict[str, JsonValue]] = []
    shown_ids: set[int] = set()
    exchanges: list[Exchange] = []
    answer, cited, proposal_id = NO_ANSWER_IN_STEPS, [], None
    try:
        for _ in range(MAX_STEPS):
            step, made = _next_step({"message": message, "lead_id": lead_id, "steps": steps}, env)
            exchanges += made
            if step is None:
                answer = UNREADABLE_STEP
                break
            if step.action == "answer":
                assert step.answer is not None  # an answer step has its answer
                answer = step.answer
                cited = [i for i in dict.fromkeys(step.cited_event_ids) if i in shown_ids]
                break
            if step.action == "propose_command":
                answer, proposal_id = _propose(db, env, step)
                break
            result = READ_TOOLS[step.action](db, step.lead_id or "")
            shown_ids.update(event["id"] for event in result.get("events", []))
            steps.append(
                {"action": step.action, "arguments": {"lead_id": step.lead_id}, "result": result}
            )
    except RecordingMiss as miss:
        _record_miss(db, env, miss)
        raise
    finally:
        _record_model_calls(db, env, lead_id, exchanges)
    return TurnResult(answer, cited, proposal_id, exchanges)
