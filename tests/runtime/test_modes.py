# ABOUTME: Tests that the run mode is read once at startup and stamped on events, and that live and record never read a recording and replay never makes the model call.
# ABOUTME: The model call is a plain function that counts its calls; recordings are real files under a temporary directory.
import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

import uwh.runtime.modes as modes_module
import uwh.runtime.recordings as recordings_module
from uwh.runtime.event_types import EventType, ModelCalled
from uwh.runtime.events import EventContext, append_event, read_events
from uwh.runtime.modes import RecordingMiss, exchange_for_mode
from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    input_hash,
    read_recording,
    write_recording,
)
from uwh.runtime.store import open_store
from uwh.settings import Settings

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


class ModelDown(Exception):
    pass


def failing_model() -> Exchange:
    raise ModelDown("provider unavailable")


def test_live_calls_the_model_and_neither_reads_nor_writes_a_recording(tmp_path: Path) -> None:
    write_recording(tmp_path, KEY, an_exchange("recorded"))
    model = Model()
    served = exchange_for_mode("live", tmp_path, KEY, model)
    assert model.calls == 1
    assert served.request_id == "live"
    assert read_recording(tmp_path, KEY) == an_exchange("recorded")


def test_live_writes_nothing_when_no_recording_exists(tmp_path: Path) -> None:
    exchange_for_mode("live", tmp_path, KEY, Model())
    assert list(tmp_path.rglob("*.json")) == []


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


@pytest.mark.parametrize("mode", ["live", "record"])
def test_a_failing_live_call_propagates_and_is_not_answered_from_a_recording(
    tmp_path: Path, mode: str
) -> None:
    write_recording(tmp_path, KEY, an_exchange("recorded"))
    with pytest.raises(ModelDown):
        exchange_for_mode(mode, tmp_path, KEY, failing_model)  # type: ignore[arg-type]
    assert read_recording(tmp_path, KEY) == an_exchange("recorded")


def test_mode_is_read_once_and_a_later_environment_change_does_not_alter_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("RUN_MODE", "replay")
    settings = Settings.load()
    monkeypatch.setenv("RUN_MODE", "live")
    model = Model()
    with pytest.raises(RecordingMiss):
        exchange_for_mode(settings.run_mode, tmp_path, KEY, model)
    assert model.calls == 0


def test_modes_and_recordings_never_read_the_environment() -> None:
    for module in (modes_module, recordings_module):
        source = inspect.getsource(module)
        assert "environ" not in source and "getenv" not in source


def test_the_mode_from_settings_is_stamped_on_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("RUN_MODE", "record")
    settings = Settings.load()
    monkeypatch.setenv("RUN_MODE", "live")
    now = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    context = EventContext(
        run_id="run-1",
        mode=settings.run_mode,
        actor="workflow",
        ruleset_hash="r" * 64,
        real_ts=now,
        sim_ts=now,
    )
    db = open_store(str(tmp_path / "events.db"))
    served = exchange_for_mode(settings.run_mode, tmp_path, KEY, Model())
    append_event(
        db,
        context,
        EventType.model_called,
        ModelCalled(
            skill=served.skill,
            prompt_version=served.prompt_version,
            input_hash=served.input_hash,
            tokens_in=served.tokens_in,
            tokens_out=served.tokens_out,
            stop_reason=served.stop_reason,
        ),
        lead_id=None,
        model_id=served.model_id,
        request_id=served.request_id,
    )
    (stored,) = read_events(db)
    assert stored.mode == "record"
    assert (tmp_path / KEY.skill).is_dir()
