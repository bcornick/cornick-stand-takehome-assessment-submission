# ABOUTME: How a model skill gets its answer (A.10, 7.7): one forced tool call to the Anthropic-format endpoint, served by the run mode from the live call, the live call and a recording, or the recording alone.
# ABOUTME: A model skill describes its call as a ForcedToolCall and receives the Exchange; the live call is absent when the environment holds no key.
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import ToolParam
from pydantic import ValidationError

from uwh.rules.models import StrictModel
from uwh.runtime.event_types import EventType, ModelCalled, ReplayMiss
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.jev_client import JevAccess
from uwh.runtime.modes import RecordingMiss, exchange_for_mode
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
    def tool(self) -> ToolParam:
        """The tool as the endpoint receives it."""
        return {
            "name": self.tool_name,
            "description": self.tool_description,
            "input_schema": self.tool_schema,
        }

    @property
    def recording_key(self) -> RecordingKey:
        return RecordingKey(
            self.skill, prompt_version(self.prompt_file, self.tool), input_hash(self.shown)
        )


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
    """What the run mode lets a model skill do. `live` is None when the environment holds no key, and
    `jev` is None when it holds no Jev key."""

    mode: RunMode
    recordings: Path
    live: LiveCall | None
    jev: JevAccess | None = None

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


def read_tool_input[Output: StrictModel](
    model: ModelAccess, call: ForcedToolCall, output: type[Output]
) -> tuple[Output | None, list[Exchange]]:
    """The tool input as `output`, with the exchange of each call made. A tool input that fails
    validation repeats the call once; a second failure, or a refusal, gives no output. The last
    exchange's stop reason tells a refusal from an invalid input."""
    exchanges: list[Exchange] = []
    for _ in range(2):
        exchange = model.exchange(call)
        exchanges.append(exchange)
        if exchange.stop_reason == "refusal":
            return None, exchanges
        try:
            return output.model_validate(exchange.tool_input), exchanges
        except ValidationError:
            continue
    return None, exchanges


def append_model_calls(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str | None,
    exchanges: Sequence[Exchange],
) -> None:
    """Write one `model_called` event for each exchange. The caller commits."""
    for exchange in exchanges:
        append_event(
            db,
            context,
            EventType.model_called,
            ModelCalled(
                skill=exchange.skill,
                prompt_version=exchange.prompt_version,
                input_hash=exchange.input_hash,
                tokens_in=exchange.tokens_in,
                tokens_out=exchange.tokens_out,
                stop_reason=exchange.stop_reason,
            ),
            lead_id=lead_id,
            model_id=exchange.model_id,
            request_id=exchange.request_id or None,
            prompt_versions={exchange.skill: exchange.prompt_version},
        )


def append_replay_miss(
    db: sqlite3.Connection, context: EventContext, lead_id: str | None, miss: RecordingMiss
) -> None:
    """Write the `replay_miss` event of a call that had no recording. The caller commits."""
    append_event(
        db,
        context,
        EventType.replay_miss,
        ReplayMiss(
            skill=miss.key.skill,
            prompt_version=miss.key.prompt_version,
            input_hash=miss.key.input_hash,
        ),
        lead_id=lead_id,
    )
