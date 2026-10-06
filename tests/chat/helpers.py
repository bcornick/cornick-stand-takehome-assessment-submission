# ABOUTME: A scripted model for the chat tests: it returns the next tool input on each call and keeps what it was shown.
# ABOUTME: The tests are of our loop and routes, not of the model; the committed chat cases are graded from recordings by the eval.
from copy import deepcopy
from typing import Any

from uwh.runtime.recordings import Exchange, RecordingKey


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
