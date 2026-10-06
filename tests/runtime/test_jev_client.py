# ABOUTME: Tests the Jev client (10.4): the run mode serves a choice question from the live call, the live call and a recording, or the recording alone, and the live call builds the documented request and reads the documented response.
# ABOUTME: The live call is exercised against an in-memory transport that returns the documented response shape; recordings are real files under a temporary directory.
import json
from pathlib import Path

import httpx2
import pytest

from uwh.runtime.jev_client import (
    ChoiceQuestion,
    JevAccess,
    JevUnavailable,
    JevLiveCall,
    jev_call,
)
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.recordings import Exchange, RecordingKey

QUESTION = ChoiceQuestion(
    skill="read_reply",
    instructions="Which kind of reply is this?",
    options={"yes": "agrees", "no": "refuses"},
)
STATE = "Yes, we agree."


def an_exchange(key: RecordingKey, yes: float) -> Exchange:
    return Exchange(
        skill=key.skill,
        prompt_version=key.prompt_version,
        input_hash=key.input_hash,
        input={},
        model_id="jev-1.13.0",
        request_id="",
        stop_reason="",
        tokens_in=3,
        tokens_out=2,
        tool_input={"probabilities": {"yes": yes, "no": 1 - yes}},
    )


class Jev:
    """The live call: counts its calls and answers 0.9 for yes."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, question: ChoiceQuestion, state: str, key: RecordingKey) -> Exchange:
        self.calls += 1
        return an_exchange(key, 0.9)


def test_record_calls_jev_once_and_replay_then_serves_the_recording_without_a_call(
    tmp_path: Path,
) -> None:
    live = Jev()

    recorded = JevAccess("record", tmp_path, live).ask(QUESTION, STATE)

    assert live.calls == 1
    replayed = JevAccess("replay", tmp_path, live).ask(QUESTION, STATE)
    assert live.calls == 1
    assert replayed == recorded
    assert replayed.tool_input == {"probabilities": {"yes": 0.9, "no": pytest.approx(0.1)}}
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_live_calls_jev_and_writes_nothing(tmp_path: Path) -> None:
    live = Jev()

    JevAccess("live", tmp_path, live).ask(QUESTION, STATE)

    assert live.calls == 1
    assert list(tmp_path.rglob("*.json")) == []


@pytest.mark.parametrize(
    ("question", "state"),
    [
        (QUESTION, "No, we refuse."),
        (
            ChoiceQuestion("read_reply", "Which kind of reply is this?", {"yes": "agrees"}),
            STATE,
        ),
        (ChoiceQuestion("read_reply", "Is this a reply?", QUESTION.options), STATE),
    ],
    ids=["another text", "another option set", "another question"],
)
def test_replay_with_no_recording_for_the_question_and_text_fails_closed(
    tmp_path: Path, question: ChoiceQuestion, state: str
) -> None:
    JevAccess("record", tmp_path, Jev()).ask(QUESTION, STATE)
    live = Jev()

    with pytest.raises(RecordingMiss):
        JevAccess("replay", tmp_path, live).ask(question, state)

    assert live.calls == 0


def transport_answering(status: int, body: object, seen: list[httpx2.Request]) -> JevLiveCall:
    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json=body)

    http = httpx2.Client(
        base_url="https://jev.example",
        headers={"Authorization": "Bearer k"},
        transport=httpx2.MockTransport(handle),
    )
    return jev_call(http)


DOCUMENTED_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "answer": {
            "type": "choice",
            "choice": "yes",
            "confidence": 0.78,
            "probabilities": {"no": 0.15, "yes": 0.85},
        }
    },
    "usage": {"input_tokens": 392, "output_tokens": 65},
}
KEY = RecordingKey("read_reply", "a" * 64, "b" * 64)


def test_the_live_call_posts_the_question_and_returns_the_probabilities() -> None:
    seen: list[httpx2.Request] = []

    exchange = transport_answering(200, DOCUMENTED_RESPONSE, seen)(QUESTION, STATE, KEY)

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://jev.example/v1/systemone"
    assert request.headers["Authorization"] == "Bearer k"
    assert json.loads(request.content) == {
        "state": STATE,
        "model": "jev-latest",
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": "Which kind of reply is this?",
                "criteria": {"yes": "agrees", "no": "refuses"},
            }
        },
    }
    assert exchange.tool_input == {"probabilities": {"yes": 0.85, "no": 0.15}}
    assert (exchange.model_id, exchange.tokens_in, exchange.tokens_out) == ("jev-1.13.0", 392, 65)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {"error": "rate limited"}),
        (200, {"model": "jev-1.13.0", "answers": {}, "usage": {}}),
        (
            200,
            DOCUMENTED_RESPONSE
            | {"answers": {"answer": {"type": "choice", "probabilities": {"yes": 1.0}}}},
        ),
    ],
    ids=["error status", "no answer", "an option missing"],
)
def test_the_live_call_is_unavailable_when_jev_gives_no_usable_answer(
    status: int, body: object
) -> None:
    with pytest.raises(JevUnavailable):
        transport_answering(status, body, [])(QUESTION, STATE, KEY)
