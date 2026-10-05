# ABOUTME: Tests the routing of a model exchange by run mode: live never reads a recording, record writes one, replay serves it, never calls the model and fails on a miss.
# ABOUTME: The model call is a plain function that counts its calls; recordings are real files under a temporary directory.
from pathlib import Path

import pytest

from uwh.runtime.modes import RecordingMiss, exchange_for_mode
from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    input_hash,
    read_recording,
    write_recording,
)

KEY = RecordingKey(skill="read_reply", prompt_version="a" * 64, input_hash=input_hash({"x": 1}))


def an_exchange(request_id: str) -> Exchange:
    return Exchange(
        skill=KEY.skill,
        prompt_version=KEY.prompt_version,
        input_hash=KEY.input_hash,
        input={"x": 1},
        model_id="deepseek-flash",
        request_id=request_id,
        stop_reason="tool_use",
        tokens_in=10,
        tokens_out=5,
        tool_input={"candidates": []},
    )


class Model:
    """The live model call: counts its calls and returns the exchange it is told to."""

    def __init__(self, request_id: str = "live") -> None:
        self.calls = 0
        self.request_id = request_id

    def __call__(self) -> Exchange:
        self.calls += 1
        return an_exchange(self.request_id)


def test_live_calls_the_model_and_neither_reads_nor_writes_a_recording(tmp_path: Path) -> None:
    assert exchange_for_mode("live", tmp_path, KEY, Model()).request_id == "live"
    assert list(tmp_path.rglob("*.json")) == []
    write_recording(tmp_path, KEY, an_exchange("recorded"))
    model = Model()
    served = exchange_for_mode("live", tmp_path, KEY, model)
    assert model.calls == 1
    assert served.request_id == "live"
    assert read_recording(tmp_path, KEY) == an_exchange("recorded")


def test_record_calls_the_model_and_writes_the_exchange_even_over_an_existing_one(
    tmp_path: Path,
) -> None:
    write_recording(tmp_path, KEY, an_exchange("old"))
    model = Model("new")
    served = exchange_for_mode("record", tmp_path, KEY, model)
    assert model.calls == 1
    assert served.request_id == "new"
    assert read_recording(tmp_path, KEY) == an_exchange("new")


def test_replay_serves_the_recording_and_never_calls_the_model(tmp_path: Path) -> None:
    write_recording(tmp_path, KEY, an_exchange("recorded"))
    model = Model()
    assert exchange_for_mode("replay", tmp_path, KEY, model) == an_exchange("recorded")
    assert model.calls == 0


def test_replay_miss_raises_carrying_the_key_and_never_calls_the_model(tmp_path: Path) -> None:
    model = Model()
    with pytest.raises(RecordingMiss) as raised:
        exchange_for_mode("replay", tmp_path, KEY, model)
    assert raised.value.key == KEY
    assert KEY.input_hash in str(raised.value)
    assert model.calls == 0
    assert list(tmp_path.rglob("*.json")) == []
