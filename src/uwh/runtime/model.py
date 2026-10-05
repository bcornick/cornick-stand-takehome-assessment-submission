# ABOUTME: How a model skill gets its answer (A.10, 7.7): one forced tool call to the Anthropic-format endpoint, served by the run mode from the live call, the live call and a recording, or the recording alone.
# ABOUTME: A model skill describes its call as a ForcedToolCall and receives the Exchange; the live call is absent when the environment holds no key.
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from uwh.runtime.modes import exchange_for_mode
from uwh.runtime.recordings import Exchange, RecordingKey, input_hash, prompt_version
from uwh.settings import RunMode

# The reply a model skill reads is short; its tool input is a few hundred tokens.
MAX_OUTPUT_TOKENS = 1024


@dataclass(frozen=True)
class ForcedToolCall:
    """One structured model call: the skill's prompt, the content the model is shown, and the one
    tool whose input schema is the output the skill validates."""

    skill: str
    prompt_file: Path
    shown: Mapping[str, Any]
    tool_name: str
    tool_description: str
    tool_schema: dict[str, Any]

    @property
    def tool(self) -> dict[str, Any]:
        """The tool as the endpoint receives it."""
        return {
            "name": self.tool_name,
            "description": self.tool_description,
            "input_schema": self.tool_schema,
        }

    @property
    def recording_key(self) -> RecordingKey:
        return RecordingKey(self.skill, prompt_version(self.prompt_file, self.tool), input_hash(self.shown))


# Makes the live call for `call`, to be stored under `key`.
LiveCall = Callable[[ForcedToolCall, RecordingKey], Exchange]


def anthropic_call(client: anthropic.Anthropic, model_id: str) -> LiveCall:
    """The live call: a forced tool choice with thinking disabled and temperature 0. The SDK's
    `messages.create` has no temperature argument, so it travels in `extra_body` (A.10)."""

    def call(call: ForcedToolCall, key: RecordingKey) -> Exchange:
        response = client.messages.create(
            model=model_id,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=call.prompt_file.read_text(encoding="utf-8"),
            messages=[{"role": "user", "content": json.dumps(call.shown, ensure_ascii=False)}],
            tools=[call.tool],
            tool_choice={"type": "tool", "name": call.tool_name},
            thinking={"type": "disabled"},
            extra_body={"temperature": 0},
        )
        tool_input = next((b.input for b in response.content if b.type == "tool_use"), None)
        assert tool_input is None or isinstance(tool_input, dict)  # a tool input is a JSON object
        return Exchange(
            skill=key.skill,
            prompt_version=key.prompt_version,
            input_hash=key.input_hash,
            input=dict(call.shown),
            model_id=model_id,
            request_id=response._request_id or "",
            stop_reason=response.stop_reason or "",
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            tool_input=tool_input,
        )

    return call


@dataclass(frozen=True)
class ModelAccess:
    """What the run mode lets a model skill do. `live` is None when the environment holds no key."""

    mode: RunMode
    recordings: Path
    live: LiveCall | None

    @property
    def available(self) -> bool:
        """Replay needs no key; live and record need the live call."""
        return self.mode == "replay" or self.live is not None

    def exchange(self, call: ForcedToolCall) -> Exchange:
        """The exchange for the call, by the run mode. Raises RecordingMiss in replay when nothing is
        recorded for it. The caller checks `available` first."""
        key = call.recording_key

        def call_model() -> Exchange:
            assert self.live is not None  # `available` is checked before a call
            return self.live(call, key)

        return exchange_for_mode(self.mode, self.recordings, key, call_model)
