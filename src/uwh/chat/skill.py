# ABOUTME: The chat skill (section 11, A.11): a bounded loop of forced tool calls in which the model looks something up, answers, or proposes a command, and code runs the lookups and submits `propose_command` as the assistant.
# ABOUTME: A turn is at most MAX_STEPS steps. An answer cites only reference numbers a lookup showed this turn, and a proposal executes nothing: the command layer stores a card or refuses it.
import re
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
from uwh.rules.registry import fact_fields
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
from uwh.skills.steps import without_seed

TOOL_NAME = "chat_step"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")

# Who the chat's commands and events are written as: the actor its manifest declares.
_ACTOR = load_manifest(Path(__file__).parent).actor

# The steps one turn may take: some reads and the answer, or one proposal. The last allowed step
# can only answer or propose. The cap is fixed.
MAX_STEPS = 8

# What the assistant says to a directive that belongs to another control of the page.
_ELSEWHERE = {
    "start_run": "Loading leads is a demo control, bottom right.",
    "deliver_reply": "Paste the reply in the lead's full detail.",
}

# What the assistant says when a turn ends without an answer of the model's own.
NO_ANSWER_BEFORE_READING = (
    "I ran out of steps before reading anything. Ask about one lead or one field."
)
UNREADABLE_STEP = "I could not read the assistant's reply. Ask again."

# What a lookup that has already run this turn shows in place of its result.
_REPEATED = {
    "repeated": True,
    "note": "You already have this result above. Answer from what you have.",
}


def _no_answer_after_reading(lead_names: list[str]) -> str:
    """What the assistant says when the final call gave no answer: the leads it did read."""
    if not lead_names:
        return NO_ANSWER_BEFORE_READING
    if len(lead_names) == 1:
        named = f"lead {lead_names[0]}"
    else:
        named = f"leads {', '.join(lead_names[:-1])} and {lead_names[-1]}"
    return f"I read {named} and ran out of steps. Ask about fewer leads or one field."


class _Reply(StrictModel):
    """The fields of a step that answers or proposes."""

    answer: str | None = None
    citations: list[int] = []  # reference numbers from this turn's lookup results
    command_type: str | None = None
    command_payload: dict[str, str | int | float | bool] | None = None
    rationale: str | None = None

    def _require(
        self, action: str, needed_by_action: dict[str, tuple[str, ...]], otherwise: tuple[str, ...]
    ) -> Self:
        missing = [
            name for name in needed_by_action.get(action, otherwise) if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"{action} needs {', '.join(missing)}")
        return self


_REPLY_NEEDS = {
    "answer": ("answer",),
    "propose_command": ("command_type", "command_payload", "rationale"),
}


# The tool input of a chat step. `action` picks what the step does; the other fields belong to one action each.
class ChatStep(_Reply):
    action: Literal[
        "lead_events",
        "lead_summary",
        "messages",
        "playbook_path",
        "current_draft",
        "queue_summary",
        "queue_facts",
        "answer",
        "propose_command",
    ]
    lead_id: str | None = None
    keys: list[str] = []  # the fact keys `queue_facts` shows; empty for the address fields

    @model_validator(mode="after")
    def _has_what_its_action_needs(self) -> Self:
        needed = {**_REPLY_NEEDS, "queue_summary": (), "queue_facts": ()}
        return self._require(self.action, needed, ("lead_id",))


# The tool input of the last allowed step: the model may only answer, in part if it must, or propose.
class FinalStep(_Reply):
    action: Literal["answer", "propose_command"]

    @model_validator(mode="after")
    def _has_what_its_action_needs(self) -> Self:
        return self._require(self.action, _REPLY_NEEDS, ())


@dataclass(frozen=True)
class TurnResult:
    """How a turn closed: with an answer and what it cites, or with the card a proposal created."""

    answer: str | None  # None exactly when the turn created a card
    citations: list[Citation]
    proposal_id: int | None


def forced_call(shown: dict[str, Any], step_schema: type[ChatStep | FinalStep]) -> ForcedToolCall:
    """The call: the model is shown the message, the open lead, the conversation's last exchanges
    and what this turn has done so far, and must reply with a `step_schema`."""
    return ForcedToolCall(
        skill="chat",
        prompt_file=_PROMPT_FILE,
        shown=shown,
        tool_name=TOOL_NAME,
        tool_description="Look something up, answer the underwriter, or propose a command.",
        tool_schema=step_schema.model_json_schema(),
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


# A lead with no address is labelled by its id, so "label (id)" names it twice once the seed is gone.
_NAMED_TWICE = re.compile(r"\b(LEAD-\d+) \(\1\)")


def _for_the_underwriter(answer: str) -> str:
    """The answer as the underwriter reads it: the model reads lead ids in full, the underwriter
    without the run's seed, and a lead once."""
    return _NAMED_TWICE.sub(r"\1", without_seed(answer))


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
        "final": False,
    }
    references = References(fact_fields(env.registry))
    exchanges: list[Exchange] = []
    answer: str | None = None
    read: list[str] = []  # the leads whose lookups ran, as the model named them
    seen: set[tuple[str, str | None, tuple[str, ...]]] = set()
    cited: list[Citation] = []
    proposal_id = None
    try:
        for number in range(1, MAX_STEPS + 1):
            shown["final"] = number == MAX_STEPS
            step, made = read_tool_input(
                env.model, forced_call(shown, FinalStep if shown["final"] else ChatStep), ChatStep
            )
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
            if shown["final"]:
                break
            asked = (step.action, step.lead_id, tuple(step.keys))
            if asked in seen:
                result = _REPEATED
            else:
                seen.add(asked)
                lookup = look_up(db, step.action, step.lead_id, step.keys, references)
                on_step(lookup.summary)
                result = lookup.shown
                if step.lead_id is not None and "error" not in result:
                    name = step.lead_id.rsplit("-", 1)[-1]
                    read += [] if name in read else [name]
            shown["steps"] = [
                *shown["steps"],
                {"action": step.action, "lead_id": step.lead_id, "result": result},
            ]
        if answer is None and proposal_id is None:
            answer = _no_answer_after_reading(read)
    except RecordingMiss as miss:
        with unit_of_work(db):
            append_replay_miss(db, _context(db, env), None, miss)
        raise
    finally:
        with unit_of_work(db):
            append_model_calls(db, _context(db, env), lead_id, exchanges)
    return TurnResult(None if answer is None else _for_the_underwriter(answer), cited, proposal_id)
