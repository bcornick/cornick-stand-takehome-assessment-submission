# ABOUTME: Tests the chat turn's loop (section 11): the cap on calls, an answer that cites only events a tool showed, a proposal stored through the command layer or refused by it, the repeat on an invalid tool input, and the events a turn writes.
# ABOUTME: The model is scripted call by call, since the tests are of our loop and not of the model; the committed chat cases are graded from recordings by the eval.
import sqlite3
from copy import deepcopy
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import uwh.chat

from tests.runtime.helpers import RULESET, RUN_START, command_environment, events_of, insert_run
from uwh.chat.skill import MAX_STEPS, NO_ANSWER_IN_STEPS, UNREADABLE_STEP, forced_call, run_turn
from uwh.runtime.event_types import EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.model import ModelAccess
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.proposals import open_proposals
from uwh.runtime.recordings import Exchange, RecordingKey
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.store import open_store
from uwh.runtime.workflow import create_lead
from uwh.skills.manifest import check_skill_folder
from uwh.skills.vertical import REFERENCE_MORNING

LEAD = "L-1"
READ_EVENTS = {"action": "lead_events", "lead_id": LEAD}
DECLINE = {
    "action": "propose_command",
    "command_type": "decline_lead",
    "command_payload": {"lead_id": LEAD, "reason": "vacant"},
    "rationale": "The building is vacant.",
}


class Script:
    """A model that returns the next scripted tool input on each call and records what it was shown."""

    def __init__(self, *tool_inputs: dict[str, Any]) -> None:
        self.tool_inputs = list(tool_inputs)
        self.shown: list[dict[str, Any]] = []

    def __call__(self, call: Any, key: RecordingKey) -> Exchange:
        self.shown.append(deepcopy(dict(call.shown)))
        return Exchange(
            skill=key.skill,
            prompt_version=key.prompt_version,
            input_hash=key.input_hash,
            input=dict(call.shown),
            model_id="scripted",
            request_id="",
            stop_reason="tool_use",
            tokens_in=10,
            tokens_out=5,
            tool_input=self.tool_inputs.pop(0),
        )


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    insert_run(db)
    setup = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
    create_lead(db, setup, LEAD, "web", "2026-06-29T07:00:00Z")
    db.commit()
    return db


@pytest.fixture
def scripted(
    tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient
) -> Callable[..., tuple[RunEnvironment, Script]]:
    def make(*tool_inputs: dict[str, Any]) -> tuple[RunEnvironment, Script]:
        script = Script(*tool_inputs)
        env = command_environment(tmp_path, mailbox, leadgen)
        return replace(env, model=ModelAccess("live", tmp_path, script)), script

    return make


def test_a_read_then_an_answer_cites_the_events_the_tool_showed(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    (received,) = read_events(db, lead_id=LEAD)
    env, script = scripted(
        READ_EVENTS,
        {"action": "answer", "answer": "It arrived by web.", "cited_event_ids": [received.id]},
    )

    turn = run_turn(db, env, "How did L-1 arrive?", LEAD)

    assert turn.answer == "It arrived by web." and turn.cited_event_ids == [received.id]
    assert script.shown[0]["steps"] == []
    (step,) = script.shown[1]["steps"]
    assert step["action"] == "lead_events" and step["result"]["events"][0]["id"] == received.id
    assert turn.proposal_id is None


def test_an_answer_cites_no_event_id_a_tool_did_not_show(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    (received,) = read_events(db, lead_id=LEAD)
    env, _ = scripted(
        READ_EVENTS,
        {
            "action": "answer",
            "answer": "x",
            "cited_event_ids": [received.id, 9999, received.id],
        },
    )

    assert run_turn(db, env, "q", LEAD).cited_event_ids == [received.id]


def test_a_question_writes_only_the_model_calls(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    before = len(read_events(db))
    env, _ = scripted(READ_EVENTS, {"action": "answer", "answer": "x", "cited_event_ids": []})

    run_turn(db, env, "q", LEAD)

    written = read_events(db)[before:]
    assert [e.type for e in written] == [EventType.model_called, EventType.model_called]
    assert {e.actor for e in written} == {"assistant"} and {e.lead_id for e in written} == {LEAD}


def test_a_turn_stops_at_the_cap_and_makes_no_further_call(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(*[READ_EVENTS] * (MAX_STEPS + 3))

    turn = run_turn(db, env, "q", LEAD)

    assert turn.answer == NO_ANSWER_IN_STEPS
    assert len(script.shown) == MAX_STEPS == len(turn.exchanges)
    assert len(script.tool_inputs) == 3


def test_a_proposal_stores_a_card_and_the_answer_points_to_it(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(DECLINE)

    turn = run_turn(db, env, "Decline L-1, it is vacant", LEAD)

    (card,) = open_proposals(db)
    assert turn.proposal_id == card.id and "The building is vacant." in turn.answer
    assert card.payload["type"] == "decline_lead"
    assert len(script.shown) == 1
    assert db.execute("SELECT status FROM leads").fetchone() == ("received",)


@pytest.mark.parametrize("command", ["approve", "reject", "send_quote_packet"])
def test_a_directive_to_approve_reject_or_send_is_refused_by_the_command_layer(
    db: sqlite3.Connection,
    scripted: Callable[..., tuple[RunEnvironment, Script]],
    command: str,
) -> None:
    env, _ = scripted(
        {**DECLINE, "command_type": command, "command_payload": {"item_id": 1, "reason": "ok"}}
    )

    turn = run_turn(db, env, "do it", LEAD)

    assert turn.proposal_id is None and command in turn.answer
    assert open_proposals(db) == []
    (refusal,) = events_of(db, EventType.command_refused)
    assert refusal.actor == "assistant"


def test_an_invalid_tool_input_repeats_the_call_once_and_then_gives_up(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted({"action": "answer"}, {"action": "answer"}, {"action": "answer"})

    turn = run_turn(db, env, "q", LEAD)

    assert turn.answer == UNREADABLE_STEP and len(script.shown) == 2
    assert len(script.tool_inputs) == 1


def test_a_recording_miss_in_replay_is_recorded_and_raised(
    db: sqlite3.Connection, tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient
) -> None:
    env = command_environment(tmp_path, mailbox, leadgen)

    with pytest.raises(RecordingMiss):
        run_turn(db, env, "q", LEAD)

    (miss,) = events_of(db, EventType.replay_miss)
    assert miss.payload.skill == "chat"  # type: ignore[attr-defined]


def test_the_model_is_shown_the_message_the_lead_and_nothing_else() -> None:
    call = forced_call({"message": "m", "lead_id": None, "steps": []})

    assert call.shown == {"message": "m", "lead_id": None, "steps": []}
    assert call.tool_name == "chat_step"


def test_the_chat_folder_is_a_complete_skill_folder_for_the_assistant() -> None:
    manifest = check_skill_folder(Path(uwh.chat.__file__).parent)

    assert (manifest.actor, manifest.command_classes) == ("assistant", ["propose_command"])
    assert manifest.model_skill and manifest.pass_threshold == 1.0
