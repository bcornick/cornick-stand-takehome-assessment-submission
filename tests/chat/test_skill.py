# ABOUTME: Tests the chat turn's loop (section 11): the cap on calls, an answer that cites only references a lookup showed, a proposal stored through the command layer or a refusal that points to the open item, the repeat on an invalid tool input, and the events a turn writes.
# ABOUTME: The model is scripted call by call, since the tests are of our loop and not of the model; the committed chat cases are graded from recordings by the eval.
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest


from tests.chat.helpers import Script
from tests.runtime.helpers import RULESET, RUN_START, command_environment, events_of, insert_run
from uwh.api.views import ChatExchange, Citation
from uwh.chat.skill import (
    MAX_STEPS,
    NO_ANSWER_BEFORE_READING,
    ChatStep,
    FinalStep,
    UNREADABLE_STEP,
    TurnResult,
    forced_call,
    run_turn,
)
from uwh.runtime.event_types import BlockerDetail, EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.model import ModelAccess
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.proposals import open_proposals
from uwh.runtime.runs import RunEnvironment
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker
from uwh.runtime.workflow import create_lead
from uwh.skills.vertical import REFERENCE_MORNING

LEAD = "L-1"
SETUP = EventContext("run-1", "replay", "workflow", RULESET, RUN_START, REFERENCE_MORNING)
READ_EVENTS = {"action": "lead_events", "lead_id": LEAD}
DECLINE = {
    "action": "propose_command",
    "command_type": "decline_lead",
    "command_payload": {"lead_id": LEAD, "reason": "vacant"},
    "rationale": "The building is vacant.",
}


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    insert_run(db)
    create_lead(db, SETUP, LEAD, "web", "2026-06-29T07:00:00Z")
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


def turn_on(db: sqlite3.Connection, env: RunEnvironment, message: str) -> TurnResult:
    """A turn on the lead's conversation with no earlier exchange, its steps unwatched."""
    return run_turn(db, env, message, LEAD, [], lambda _line: None)


def test_a_read_then_an_answer_cites_what_the_lookup_showed(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    (received,) = read_events(db, lead_id=LEAD)
    env, script = scripted(
        READ_EVENTS, {"action": "answer", "answer": "It arrived by web.", "citations": [1]}
    )
    lines: list[str] = []

    turn = run_turn(db, env, "How did L-1 arrive?", LEAD, [], lines.append)

    assert turn.answer == "It arrived by web." and turn.proposal_id is None
    assert turn.citations == [
        Citation(
            number=1,
            lead_id=LEAD,
            kind="event",
            id=received.id,
            text="Event: Received the lead from web",
        )
    ]
    assert script.shown[0]["steps"] == []
    (step,) = script.shown[1]["steps"]
    (shown_event,) = step["result"]["events"]
    assert step["action"] == "lead_events" and shown_event["ref"] == 1 and "id" not in shown_event
    assert lines == ["Read the events of lead 1: 1 event"]


def test_a_citation_outside_this_turns_results_is_dropped(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, _ = scripted(READ_EVENTS, {"action": "answer", "answer": "x", "citations": [1, 99, 1]})

    assert [c.number for c in turn_on(db, env, "q").citations] == [1]


def test_a_question_writes_only_the_model_calls(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    before = len(read_events(db))
    env, _ = scripted(READ_EVENTS, {"action": "answer", "answer": "x"})

    turn_on(db, env, "q")

    written = read_events(db)[before:]
    assert [e.type for e in written] == [EventType.model_called, EventType.model_called]
    assert {e.actor for e in written} == {"assistant"} and {e.lead_id for e in written} == {LEAD}


def test_a_turn_that_still_gives_no_answer_on_the_final_call_reports_the_leads_it_read(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(*[READ_EVENTS] * (MAX_STEPS + 3))

    turn = turn_on(db, env, "q")

    assert turn.answer == "I read lead 1 and ran out of steps. Ask about fewer leads or one field."
    assert len(script.shown) == MAX_STEPS
    assert len(script.tool_inputs) == 3


def test_a_turn_that_read_nothing_says_so_when_it_runs_out_of_steps(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, _ = scripted(*[{"action": "queue_summary"}] * MAX_STEPS)

    assert turn_on(db, env, "q").answer == NO_ANSWER_BEFORE_READING


def test_the_last_allowed_step_is_shown_as_final_and_cannot_look_anything_up(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(
        *[READ_EVENTS] * (MAX_STEPS - 1),
        {"action": "answer", "answer": "Partly: it arrived by web.", "citations": [1]},
    )

    turn = turn_on(db, env, "q")

    assert [shown["final"] for shown in script.shown] == [False] * (MAX_STEPS - 1) + [True]
    assert turn.answer == "Partly: it arrived by web." and [c.number for c in turn.citations] == [1]
    last = forced_call({"final": True}, FinalStep).tool_schema
    assert last["properties"]["action"]["enum"] == ["answer", "propose_command"]
    open_call = forced_call({"final": False}, ChatStep).tool_schema
    assert "lead_events" in open_call["properties"]["action"]["enum"]


def test_a_repeated_lookup_runs_once_and_the_model_is_told_so(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(READ_EVENTS, READ_EVENTS, {"action": "answer", "answer": "x"})
    lines: list[str] = []

    run_turn(db, env, "q", LEAD, [], lines.append)

    assert lines == ["Read the events of lead 1: 1 event"]
    first, second = script.shown[2]["steps"]
    assert "events" in first["result"]
    assert second["result"] == {
        "repeated": True,
        "note": "You already have this result above. Answer from what you have.",
    }


def test_a_question_about_several_leads_yields_no_command(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(
        {"action": "queue_facts", "keys": ["state"]},
        {"action": "answer", "answer": "None.", "citations": [1]},
    )

    turn = run_turn(db, env, "Which leads are in Florida?", None, [], lambda _line: None)

    assert turn.proposal_id is None and open_proposals(db) == []
    (row,) = script.shown[1]["steps"][0]["result"]["leads"]
    assert row["lead_id"] == LEAD and list(row["facts"]) == ["state"]


def test_a_proposal_stores_a_card_and_the_answer_points_to_it(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(DECLINE)

    turn = turn_on(db, env, "Decline L-1, it is vacant")

    (card,) = open_proposals(db)
    assert turn.proposal_id == card.id and turn.answer is None
    assert card.payload["type"] == "decline_lead"
    assert len(script.shown) == 1
    assert db.execute("SELECT status FROM leads").fetchone() == ("received",)


@pytest.mark.parametrize("command", ["approve", "reject", "send_quote_packet"])
def test_a_directive_to_approve_reject_or_send_is_refused_and_the_answer_names_the_open_item(
    db: sqlite3.Connection,
    scripted: Callable[..., tuple[RunEnvironment, Script]],
    command: str,
) -> None:
    open_blocker(
        db,
        SETUP,
        LEAD,
        "underwriter_review",
        "underwriter",
        BlockerDetail(
            item_kind="no_contact_route", resume_trigger="a contact is given", text="No contact."
        ),
    )
    db.commit()
    env, _ = scripted(
        {**DECLINE, "command_type": command, "command_payload": {"item_id": 1, "reason": "ok"}}
    )

    turn = turn_on(db, env, "do it")

    assert turn.proposal_id is None and turn.answer is not None
    assert "No contact." in turn.answer and "conversation of lead 1" in turn.answer
    assert command not in turn.answer
    assert open_proposals(db) == []
    (refusal,) = events_of(db, EventType.command_refused)
    assert refusal.actor == "assistant"


def test_a_refused_directive_on_a_lead_with_no_open_item_says_nothing_is_waiting(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, _ = scripted({**DECLINE, "command_type": "approve", "command_payload": {"item_id": 1}})

    turn = turn_on(db, env, "do it")

    assert turn.answer is not None
    assert "nothing is waiting" in turn.answer and "approve" not in turn.answer


def test_a_proposal_the_command_layer_refuses_for_another_reason_gives_that_reason(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, _ = scripted({**DECLINE, "command_payload": {"lead_id": LEAD}, "rationale": ""})

    turn = turn_on(db, env, "decline it")

    assert turn.proposal_id is None and turn.answer is not None
    assert turn.answer.startswith("I cannot propose that: ")


def test_an_invalid_tool_input_repeats_the_call_once_and_then_gives_up(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted({"action": "answer"}, {"action": "answer"}, {"action": "answer"})

    turn = turn_on(db, env, "q")

    assert turn.answer == UNREADABLE_STEP and len(script.shown) == 2
    assert len(script.tool_inputs) == 1


def test_a_recording_miss_in_replay_is_recorded_and_raised(
    db: sqlite3.Connection, tmp_path: Path, mailbox: MailboxClient, leadgen: LeadgenClient
) -> None:
    env = command_environment(tmp_path, mailbox, leadgen)

    with pytest.raises(RecordingMiss):
        turn_on(db, env, "q")

    (miss,) = events_of(db, EventType.replay_miss)
    assert miss.payload.skill == "chat"  # type: ignore[attr-defined]


def test_the_model_is_shown_the_message_the_lead_the_history_and_nothing_else(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted({"action": "answer", "answer": "x"})
    earlier = ChatExchange(message="Is it vacant?", reply="The records do not say.")

    run_turn(db, env, "why?", None, [earlier], lambda _line: None)

    assert script.shown == [
        {
            "message": "why?",
            "lead_id": None,
            "history": [{"message": "Is it vacant?", "reply": "The records do not say."}],
            "steps": [],
            "final": False,
        }
    ]


def test_an_answer_names_leads_without_the_runs_seed(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(
        {
            "action": "answer",
            "answer": "LEAD-00000042-000 and 3948 Old Mill Rd (LEAD-00000042-004) wait on you.",
            "citations": [],
        }
    )

    turn = run_turn(db, env, "Which leads wait on me?", None, [], lambda _: None)

    assert turn.answer == "LEAD-000 and 3948 Old Mill Rd (LEAD-004) wait on you."


def test_an_answer_does_not_name_a_lead_with_no_address_twice(
    db: sqlite3.Connection, scripted: Callable[..., tuple[RunEnvironment, Script]]
) -> None:
    env, script = scripted(
        {
            "action": "answer",
            "answer": "LEAD-000 (LEAD-00000042-000) waits on you.",
            "citations": [],
        }
    )

    turn = run_turn(db, env, "Which leads wait on me?", None, [], lambda _: None)

    assert turn.answer == "LEAD-000 waits on you."
