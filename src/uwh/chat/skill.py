# ABOUTME: The chat skill (section 11, A.11): a bounded loop of forced tool calls in which the model looks something up, answers, or proposes a command, and code runs the lookups and submits `propose_command` as the assistant.
# ABOUTME: A turn is at most MAX_STEPS steps. An answer cites only reference numbers a lookup showed this turn, and a proposal executes nothing: the command layer stores a card or refuses it.
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import JsonValue, model_validator

from uwh.api.leads import open_items
from uwh.api.views import ChatExchange, Citation
from uwh.chat.tools import References, look_up, short_name
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

TOOL_NAME = "chat_step"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")

# Who the chat panel's commands and events are written as: the actor its manifest declares.
_ACTOR = load_manifest(Path(__file__).parent).actor

# The steps one turn may take: a few reads and the answer, or one proposal. The cap is fixed.
MAX_STEPS = 4

# What the assistant says to a directive that belongs to another control of the page.
_ELSEWHERE = {
    "start_run": "Loading leads is a demo control, bottom right.",
    "deliver_reply": "Paste the reply in the lead's full detail.",
}

# What the assistant says when a turn ends without an answer of the model's own.
NO_ANSWER_IN_STEPS = "I could not finish looking that up. Ask again with a narrower question."
UNREADABLE_STEP = "I could not read the assistant's reply. Ask again."


# The tool input of a chat step. `action` picks what the step does; the other fields belong to one action each.
class ChatStep(StrictModel):
    action: Literal[
        "lead_events",
        "lead_summary",
        "messages",
        "playbook_path",
        "current_draft",
        "queue_summary",
        "answer",
        "propose_command",
    ]
    lead_id: str | None = None
    answer: str | None = None
    citations: list[int] = []  # reference numbers from this turn's lookup results
    command_type: str | None = None
    command_payload: dict[str, str | int | float | bool] | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _has_what_its_action_needs(self) -> Self:
        needed: dict[str, tuple[str, ...]] = {
            "queue_summary": (),
            "answer": ("answer",),
            "propose_command": ("command_type", "command_payload", "rationale"),
        }
        missing = [
            name for name in needed.get(self.action, ("lead_id",)) if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"{self.action} needs {', '.join(missing)}")
        return self


@dataclass(frozen=True)
class TurnResult:
    """How a turn closed: with an answer and what it cites, or with the card a proposal created."""

    answer: str | None  # None exactly when the turn created a card
    citations: list[Citation]
    proposal_id: int | None


def forced_call(shown: dict[str, Any]) -> ForcedToolCall:
    """The call: the model is shown the message, the open lead, the conversation's last exchanges
    and what this turn has done so far."""
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
    decides (7.4): where the open item is, in the lead's conversation, and what it asks."""
    items = [item for item in open_items(db) if lead_id is None or item.lead_id == lead_id]
    if not items:
        return "That is your decision, and nothing is waiting on you now."
    where = " ".join(
        f"In the conversation of {short_name(item.lead_id)}: {item.detail.text}" for item in items
    )
    return f"That is your decision, made on the item itself. {where}"


def _propose(
    db: sqlite3.Connection, env: RunEnvironment, step: ChatStep, lead_id: str | None
) -> tuple[str | None, int | None]:
    """Submit the step's proposal as the assistant. Returns the card the command layer stored, or
    the answer when it refused: where the control for the command is, the open item to decide when
    the command is the underwriter's own, or why it refused."""
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
        return None, row[0]
    if step.command_type in _ELSEWHERE:
        return _ELSEWHERE[step.command_type], None
    if step.command_type is not None and not is_proposable(step.command_type):
        named = command_payload.get("lead_id")
        return _point_to_the_items(db, named if isinstance(named, str) else lead_id), None
    return f"I cannot propose that: {result.reason}.", None


def run_turn(
    db: sqlite3.Connection,
    env: RunEnvironment,
    message: str,
    lead_id: str | None,
    history: Sequence[ChatExchange],
    on_step: Callable[[str], None],
) -> TurnResult:
    """One chat turn. The model reads through the lookups until it answers or proposes, in at most
    MAX_STEPS steps; a step whose tool input is invalid repeats its call once, so a turn makes at most
    twice that many calls. `on_step` receives the line of each lookup as it completes. A replay with
    no recording for a call records the miss and raises RecordingMiss."""
    shown: dict[str, Any] = {
        "message": message,
        "lead_id": lead_id,
        "history": [exchange.model_dump() for exchange in history],
        "steps": [],
    }
    references = References()
    exchanges: list[Exchange] = []
    answer: str | None = NO_ANSWER_IN_STEPS
    cited: list[Citation] = []
    proposal_id = None
    try:
        for _ in range(MAX_STEPS):
            step, made = read_tool_input(env.model, forced_call(shown), ChatStep)
            exchanges += made
            if step is None:
                answer = UNREADABLE_STEP
                break
            if step.action == "answer":
                answer, cited = step.answer, references.resolve(step.citations)
                break
            if step.action == "propose_command":
                answer, proposal_id = _propose(db, env, step, lead_id)
                break
            lookup = look_up(db, step.action, step.lead_id, references)
            on_step(lookup.summary)
            shown["steps"] = [
                *shown["steps"],
                {"action": step.action, "lead_id": step.lead_id, "result": lookup.shown},
            ]
    except RecordingMiss as miss:
        with unit_of_work(db):
            append_replay_miss(db, _context(db, env), None, miss)
        raise
    finally:
        with unit_of_work(db):
            append_model_calls(db, _context(db, env), lead_id, exchanges)
    return TurnResult(answer, cited, proposal_id)
