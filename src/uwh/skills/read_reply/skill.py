# ABOUTME: The read_reply skill (10.4, A.9, A.10): one forced tool call reads a producer's reply against the asks of the open request, and code then locates each quote in the reply and drops what was not asked or does not fit the field.
# ABOUTME: The output is a reading or a typed abstention. A tool input that fails validation repeats the call once; a second failure, or a refusal, abstains.
from datetime import date
from pathlib import Path

from pydantic import Field, ValidationError

from uwh.rules.data_files import read_yaml
from uwh.rules.models import StrictModel
from uwh.rules.registry import Registry
from uwh.runtime.event_types import (
    AbstentionReason,
    Candidate,
    LocatedCandidate,
    ReplyClassification,
)
from uwh.runtime.model import ForcedToolCall, ModelAccess
from uwh.runtime.recordings import Exchange

TOOL_NAME = "record_reply_reading"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")

# A.9: a reply body is capped at this many characters.
MAX_BODY_CHARACTERS = 8000


class OpenAsk(StrictModel):
    """One question of the open request, as the model is shown it."""

    ask_id: str
    field: str  # the fact key the answer is for
    wording: str
    answer_type: str  # the registry's type kind
    options: list[str]  # the option strings of a select; empty otherwise


class ReadReplyInput(StrictModel):
    body: str = Field(max_length=MAX_BODY_CHARACTERS)
    asks: list[OpenAsk]


class ReplyReading(StrictModel):
    """What the model returns (A.9): its JSON schema is the input schema of the forced tool."""

    classification: ReplyClassification
    candidates: list[Candidate]


class Reading(StrictModel):
    classification: ReplyClassification
    candidates: list[LocatedCandidate]
    dropped: list[
        Candidate
    ]  # as the model returned them: quote not in the reply, field not asked, or a value that does not fit it


class Abstention(StrictModel):
    reason: AbstentionReason


def open_asks(ask_ids: list[str], registry: Registry) -> list[OpenAsk]:
    """The open asks of a request from its ask ids, each with its stored wording and answer type.

    Raises NotImplementedError for an ask that is not a registry field: reading a reply to a
    confirmation or a catalogue question is not built.
    """
    wording = read_yaml("wording.yaml")["fields"]
    asks = []
    for ask_id in ask_ids:
        if ask_id not in registry:
            raise NotImplementedError(f"reading a reply to the ask {ask_id} is not built")
        field = registry[ask_id]
        asks.append(
            OpenAsk(
                ask_id=ask_id,
                field=ask_id,
                wording=wording[ask_id],
                answer_type=field.kind,
                options=field.options,
            )
        )
    return asks


def _coerce(ask: OpenAsk, value: str | int | float | bool) -> str | int | float | bool | None:
    """The value in the form the ask's answer type stores, or None when it does not fit."""
    match ask.answer_type, value:
        case "toggle", bool():
            return value
        case _, bool():
            return None
        case "date", str():
            try:
                return date.fromisoformat(value).isoformat() if len(value) == 10 else None
            except ValueError:
                return None
        case "integer", int():
            return value
        case "integer", float() if value.is_integer():
            return int(value)
        case "integer", str() if value.removeprefix("-").isdigit():
            return int(value)
        case "decimal", int() | float():
            return value
        case "select", _:
            return str(value) if str(value) in ask.options else None
        case "text" | "address" | "email" | "tel", str() if value.strip():
            return value
    return None


def interpret(reading: ReplyReading, input: ReadReplyInput) -> Reading:
    """Locate each candidate's quote in the reply at its first occurrence and check its value against
    the ask. A candidate whose quote is not in the reply, whose field was not asked or whose value does
    not fit the field is dropped (10.4)."""
    asked = {ask.ask_id: ask for ask in input.asks}
    located: list[LocatedCandidate] = []
    dropped: list[Candidate] = []
    for candidate in reading.candidates:
        ask = asked.get(candidate.ask_id)
        start = input.body.find(candidate.quote)
        value = (
            None if ask is None or ask.field != candidate.field else _coerce(ask, candidate.value)
        )
        if start < 0 or value is None:
            dropped.append(candidate)
            continue
        located.append(
            LocatedCandidate(
                ask_id=candidate.ask_id,
                field=candidate.field,
                value=value,
                quote=candidate.quote,
                span_start=start,
                span_end=start + len(candidate.quote),
            )
        )
    return Reading(classification=reading.classification, candidates=located, dropped=dropped)


def forced_call(input: ReadReplyInput) -> ForcedToolCall:
    """The call: the model is shown the reply body and the open asks, nothing else."""
    return ForcedToolCall(
        skill="read_reply",
        prompt_file=_PROMPT_FILE,
        shown=input.model_dump(mode="json"),
        tool_name=TOOL_NAME,
        tool_schema=ReplyReading.model_json_schema(),
    )


def run(input: ReadReplyInput, model: ModelAccess) -> tuple[Reading | Abstention, list[Exchange]]:
    """Read the reply. Returns the reading or the abstention with the exchange of each call made."""
    call = forced_call(input)
    exchanges: list[Exchange] = []
    for _ in range(2):
        exchange = model.exchange(call)
        exchanges.append(exchange)
        if exchange.stop_reason == "refusal":
            return Abstention(reason="refusal"), exchanges
        try:
            reading = ReplyReading.model_validate(exchange.tool_input)
        except ValidationError:
            continue
        return interpret(reading, input), exchanges
    return Abstention(reason="invalid_tool_input"), exchanges
