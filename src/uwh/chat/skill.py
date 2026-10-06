# ABOUTME: The chat skill (section 11, A.11): a bounded loop of forced tool calls in which the model looks something up, answers, or proposes a command, and code runs the read tools and submits `propose_command` as the assistant.
# ABOUTME: A turn is at most MAX_STEPS steps. An answer cites only event ids a tool showed this turn, and a proposal executes nothing: the command layer stores a card or refuses it.
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import JsonValue, model_validator

from uwh.api.leads import open_items
from uwh.chat.tools import READ_TOOLS
from uwh.rules.models import StrictModel
from uwh.runtime.commands import submit_command
from uwh.runtime.events import EventContext
from uwh.runtime.model import (
    ForcedToolCall,
    append_model_calls,
    append_replay_miss,
    read_tool_input,
)
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.proposals import is_proposable
from uwh.runtime.recordings import Exchange
from uwh.runtime.runs import RunEnvironment, command_context
from uwh.runtime.workflow import unit_of_work
from uwh.skills.manifest import load_manifest
from uwh.skills.steps import lead_label

TOOL_NAME = "chat_step"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")

# Who the chat panel's commands and events are written as: the actor its manifest declares.
_ACTOR = load_manifest(Path(__file__).parent).actor

# The steps one turn may take: a few reads and the answer, or one proposal. The cap is fixed.
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


def _context(db: sqlite3.Connection, env: RunEnvironment) -> EventContext:
    return command_context(db, _ACTOR, env.mode, env.ruleset_hash, env.now())


def _point_to_the_items(db: sqlite3.Connection, lead_id: str | None) -> str:
    """What the answer says when the assistant was asked to decide something only the underwriter
    decides (7.4): where the open item is, in the lead's detail pane, and what it asks."""
    items = [item for item in open_items(db) if lead_id is None or item.lead_id == lead_id]
    if not items:
        return "That is your decision, and nothing is waiting on you now."
    where = " ".join(
        f"In lead {lead_label(db, item.lead_id)}'s detail pane: {item.detail.text}"
        for item in items
    )
    return f"That is your decision, made on the item itself. {where}"


def _propose(
    db: sqlite3.Connection, env: RunEnvironment, step: ChatStep, lead_id: str | None
) -> tuple[str, int | None]:
    """Submit the step's proposal as the assistant. The answer says what the command layer did: the
    card it stored, the open item to decide when the command is the underwriter's own, or why it
    refused."""
    command_payload: dict[str, JsonValue] = dict(step.command_payload or {})
    result = submit_command(
        db,
        env,
        _ACTOR,
        "propose_command",
        {"type": step.command_type, "payload": command_payload, "rationale": step.rationale},
    )
    if result.accepted:
        row = db.execute(
            "SELECT id FROM proposals WHERE event_id = ?", (result.event_id,)
        ).fetchone()
        return f"Proposed: {step.rationale} Review the card and apply it, or dismiss it.", row[0]
    if step.command_type is not None and not is_proposable(step.command_type):
        named = command_payload.get("lead_id")
        return _point_to_the_items(db, named if isinstance(named, str) else lead_id), None
    return f"I cannot propose that: {result.reason}.", None


def run_turn(
    db: sqlite3.Connection, env: RunEnvironment, message: str, lead_id: str | None
) -> TurnResult:
    """One chat turn. The model reads through the tools until it answers or proposes, in at most
    MAX_STEPS steps; a step whose tool input is invalid repeats its call once, so a turn makes at most
    twice that many calls. A replay with no recording for a call records the miss and raises
    RecordingMiss."""
    steps: list[dict[str, JsonValue]] = []
    shown_ids: set[int] = set()
    exchanges: list[Exchange] = []
    answer, cited, proposal_id = NO_ANSWER_IN_STEPS, [], None
    try:
        for _ in range(MAX_STEPS):
            step, made = read_tool_input(
                env.model,
                forced_call({"message": message, "lead_id": lead_id, "steps": steps}),
                ChatStep,
            )
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
                answer, proposal_id = _propose(db, env, step, lead_id)
                break
            result = READ_TOOLS[step.action](db, step.lead_id or "")
            shown_ids.update(event["id"] for event in result.get("events", []))
            steps.append(
                {"action": step.action, "arguments": {"lead_id": step.lead_id}, "result": result}
            )
    except RecordingMiss as miss:
        with unit_of_work(db):
            append_replay_miss(db, _context(db, env), None, miss)
        raise
    finally:
        with unit_of_work(db):
            append_model_calls(db, _context(db, env), lead_id, exchanges)
    return TurnResult(answer, cited, proposal_id, exchanges)
