# ABOUTME: Jev's part of read_reply (10.4): the classification put to Jev as a choice question, and the confidence the interface computes from the returned probabilities.
# ABOUTME: Jev unavailable, and a replay with no Jev recording, answer nothing and are returned as the failure; the language model then classifies the reply.
from dataclasses import dataclass
from pathlib import Path

from uwh.runtime.event_types import ReplyClassification
from uwh.runtime.jev_client import ChoiceQuestion, JevAccess, JevUnavailable
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.recordings import Exchange
from uwh.skills.manifest import load_manifest

# What a reply is read with when Jev gives no answer; the text of the `skill_fallback_used` event.
FALLBACK = "the language model classifies the reply"

# The options are the four classifications of the model's tool schema.
QUESTION = ChoiceQuestion(
    skill="read_reply",
    instructions=(
        "A producer replied to an insurance underwriter's request for information about a property "
        "submission. Which kind of reply is this?"
    ),
    options={
        "answers_all": "The reply answers everything the request appears to ask.",
        "answers_some": "The reply answers part of what the request appears to ask and leaves the rest.",
        "declines_to_answer": "The reply refuses, or says the information cannot or will not be given.",
        "off_topic": "The reply does not respond to the request.",
    },
)


@dataclass(frozen=True)
class JevAnswer:
    """Jev's classification of a reply and its confidence: the probability of the top option."""

    classification: ReplyClassification
    confidence: float
    exchange: Exchange  # the call that answered, for the `model_called` event


# Why Jev gave no answer: nothing is recorded for the reply in replay, or the live call got none.
type JevFailure = RecordingMiss | JevUnavailable


def threshold() -> float:
    """The confidence at or above which Jev's classification is used: the manifest's `jev_threshold`."""
    value = load_manifest(Path(__file__).parent).jev_threshold
    assert value is not None  # read_reply's manifest sets it
    return value


def classify(body: str, jev: JevAccess) -> JevAnswer | JevFailure:
    """Jev's answer for the reply body, or the failure that left it without one."""
    try:
        exchange = jev.ask(QUESTION, body)
    except (RecordingMiss, JevUnavailable) as failure:
        return failure
    assert exchange.tool_input is not None  # a Jev exchange always holds its probabilities
    probabilities: dict[str, float] = exchange.tool_input["probabilities"]
    top = max(QUESTION.options, key=lambda option: probabilities[option])
    # `top` is one of the four classifications: the live call returns a probability for each option.
    return JevAnswer(
        classification=top,  # type: ignore[arg-type]
        confidence=probabilities[top],
        exchange=exchange,
    )
