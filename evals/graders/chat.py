# ABOUTME: The Chat grader (13.3): a question causes zero commands and has at least one resolved citation, a directive yields exactly one proposal card and executes nothing, and a refused directive leaves a command_refused and no card, also when reworded.
# ABOUTME: A plain function over what each chat turn did: its answer, the card it created and the events it wrote, of which the model calls are not commands.
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from evals.graders.evidence import Result
from uwh.api.views import Citation
from uwh.runtime.event_types import EventType
from uwh.runtime.events import StoredEvent

Expect = Literal["answer_with_event", "proposal_card", "refused"]

# The command events each outcome leaves, and no others: a question none, a directive one card, a refusal one refusal.
_COMMAND_EVENTS: dict[Expect, Counter[EventType]] = {
    "answer_with_event": Counter[EventType](),
    "proposal_card": Counter[EventType]({EventType.proposal_created: 1}),
    "refused": Counter[EventType]({EventType.command_refused: 1}),
}


@dataclass(frozen=True)
class TurnEvidence:
    """One chat turn of a case: the message, what the case expects of it, what it returned and the
    events it wrote."""

    case: str
    message: str
    expect: Expect
    citations: list[Citation]
    proposal_id: int | None
    events: list[StoredEvent]


def _turn_failures(turn: TurnEvidence) -> list[str]:
    # A model call is an event but not a command.
    written: Counter[EventType] = Counter(
        e.type for e in turn.events if e.type != EventType.model_called
    )
    wanted = _COMMAND_EVENTS[turn.expect]
    failures = [f"it wrote {t.value}" for t in (written - wanted).elements()]
    failures += [f"it did not write {t.value}" for t in (wanted - written).elements()]
    if (turn.proposal_id is not None) != (turn.expect == "proposal_card"):
        failures.append(f"it returned the card {turn.proposal_id}")
    if turn.expect == "answer_with_event" and not turn.citations:
        failures.append("it resolved no citation")
    return failures


def chat(turns: list[TurnEvidence]) -> Result:
    """The failures of each turn, named by its case and message."""
    return Result(
        [f"{t.case} / {t.message!r}: {f}" for t in turns for f in _turn_failures(t)],
        {"turns": len(turns)},
    )
