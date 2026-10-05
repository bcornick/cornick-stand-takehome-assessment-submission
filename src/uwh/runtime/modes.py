# ABOUTME: Serves one model exchange according to the run mode (7.7): live calls the model, record calls and writes, replay reads the recording and never calls.
# ABOUTME: The mode arrives as a value from Settings; no mode falls back to another, and a miss in replay raises RecordingMiss.
from collections.abc import Callable
from pathlib import Path

from uwh.runtime.recordings import Exchange, RecordingKey, read_recording, write_recording
from uwh.settings import RunMode


class RecordingMiss(Exception):
    """Replay found no recording for `key`; the caller fails closed and shows the error."""

    def __init__(self, key: RecordingKey) -> None:
        super().__init__(
            f"no recording for skill {key.skill}, prompt version {key.prompt_version}, "
            f"input hash {key.input_hash}"
        )
        self.key = key


def exchange_for_mode(
    mode: RunMode, directory: Path, key: RecordingKey, call_model: Callable[[], Exchange]
) -> Exchange:
    """The exchange for `key`: `call_model()` in live and record (record also writes it), the recording in replay.

    A call that raises propagates in every mode; no recording answers for it.
    """
    if mode == "replay":
        recorded = read_recording(directory, key)
        if recorded is None:
            raise RecordingMiss(key)
        return recorded
    if mode not in ("live", "record"):
        raise ValueError(f"unknown run mode {mode!r}")
    exchange = call_model()
    if mode == "record":
        write_recording(directory, key, exchange)
    return exchange
