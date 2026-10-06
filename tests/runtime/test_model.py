# ABOUTME: Tests the helpers a model skill shares: the forced tool call that repeats once on an invalid tool input, and the `model_called` and `replay_miss` events a call leaves.
# ABOUTME: The model is scripted call by call, since the tests are of our helpers and not of the model.
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tests.runtime.helpers import MakeContext
from uwh.rules.models import StrictModel
from uwh.runtime.event_types import EventType, ModelCalled, ReplayMiss
from uwh.runtime.events import read_events
from uwh.runtime.model import (
    ForcedToolCall,
    ModelAccess,
    append_model_calls,
    append_replay_miss,
    read_tool_input,
)
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.recordings import Exchange, RecordingKey


class Greeting(StrictModel):
    word: str


def _call(tmp_path: Path) -> ForcedToolCall:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Greet.\n", encoding="utf-8")
    return ForcedToolCall(
        skill="greeter",
        prompt_file=prompt,
        shown={"who": "x"},
        tool_name="greet",
        tool_description="Greet.",
        tool_schema=Greeting.model_json_schema(),
    )


def _exchange(key: RecordingKey, tool_input: dict[str, Any] | None, stop: str) -> Exchange:
    return Exchange(
        skill=key.skill,
        prompt_version=key.prompt_version,
        input_hash=key.input_hash,
        input={"who": "x"},
        model_id="scripted",
        request_id="req-1",
        stop_reason=stop,
        tokens_in=10,
        tokens_out=5,
        tool_input=tool_input,
    )


def _model(tmp_path: Path, *replies: tuple[dict[str, Any] | None, str]) -> ModelAccess:
    queue = list(replies)

    def live(call: ForcedToolCall, key: RecordingKey) -> Exchange:
        tool_input, stop = queue.pop(0)
        return _exchange(key, tool_input, stop)

    return ModelAccess("live", tmp_path, live)


def test_a_valid_tool_input_is_read_in_one_call(tmp_path: Path) -> None:
    model = _model(tmp_path, ({"word": "hi"}, "tool_use"))

    reading, exchanges = read_tool_input(model, _call(tmp_path), Greeting)

    assert reading == Greeting(word="hi") and len(exchanges) == 1


def test_an_invalid_tool_input_repeats_the_call_once(tmp_path: Path) -> None:
    model = _model(tmp_path, ({"wrong": 1}, "tool_use"), ({"word": "hi"}, "tool_use"))

    reading, exchanges = read_tool_input(model, _call(tmp_path), Greeting)

    assert reading == Greeting(word="hi") and len(exchanges) == 2


def test_a_second_invalid_tool_input_gives_no_reading(tmp_path: Path) -> None:
    model = _model(
        tmp_path, ({"wrong": 1}, "tool_use"), ({"wrong": 2}, "tool_use"), ({"word": "hi"}, "x")
    )

    reading, exchanges = read_tool_input(model, _call(tmp_path), Greeting)

    assert reading is None and len(exchanges) == 2


def test_a_refusal_gives_no_reading_and_is_not_repeated(tmp_path: Path) -> None:
    model = _model(tmp_path, (None, "refusal"), ({"word": "hi"}, "tool_use"))

    reading, exchanges = read_tool_input(model, _call(tmp_path), Greeting)

    assert reading is None
    assert [e.stop_reason for e in exchanges] == ["refusal"]


def test_each_exchange_leaves_a_model_called_event(
    store: sqlite3.Connection, make_context: MakeContext, tmp_path: Path
) -> None:
    model = _model(tmp_path, ({"wrong": 1}, "tool_use"), ({"word": "hi"}, "tool_use"))
    _, exchanges = read_tool_input(model, _call(tmp_path), Greeting)

    append_model_calls(store, make_context(), "L-1", exchanges)

    events = read_events(store)
    assert [e.type for e in events] == [EventType.model_called] * 2
    payload = events[0].payload
    assert isinstance(payload, ModelCalled)
    assert (payload.skill, payload.tokens_in, payload.tokens_out) == ("greeter", 10, 5)
    assert events[0].lead_id == "L-1" and events[0].model_id == "scripted"


def test_a_recording_miss_leaves_a_replay_miss_event_with_its_key(
    store: sqlite3.Connection, make_context: MakeContext, tmp_path: Path
) -> None:
    model = ModelAccess("replay", tmp_path, None)
    with pytest.raises(RecordingMiss) as raised:
        read_tool_input(model, _call(tmp_path), Greeting)

    append_replay_miss(store, make_context(), None, raised.value)

    (event,) = read_events(store)
    assert event.type == EventType.replay_miss and event.lead_id is None
    assert isinstance(event.payload, ReplayMiss)
    assert event.payload.input_hash == raised.value.key.input_hash
