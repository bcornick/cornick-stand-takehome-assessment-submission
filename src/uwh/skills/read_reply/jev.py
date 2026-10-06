# ABOUTME: Jev's part of read_reply (10.4): the classification put to Jev as a choice question, and the confidence the interface computes from the returned probabilities.
# ABOUTME: Jev unavailable is logged and answers nothing; a replay with no recording raises RecordingMiss through, as for the model.
import logging
from dataclasses import dataclass
from pathlib import Path

from uwh.runtime.event_types import ReplyClassification
from uwh.runtime.jev_client import ChoiceQuestion, JevAccess, JevUnavailable
from uwh.skills.manifest import load_manifest

logger = logging.getLogger(__name__)

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


def threshold() -> float:
    """The confidence at or above which Jev's classification is used: the manifest's `jev_threshold`."""
    value = load_manifest(Path(__file__).parent).jev_threshold
    assert value is not None  # read_reply's manifest sets it
    return value


def classify(body: str, jev: JevAccess) -> JevAnswer | None:
    """Jev's answer for the reply body, or None when Jev is unavailable."""
    try:
        exchange = jev.ask(QUESTION, body)
    except JevUnavailable:
        logger.warning("Jev is unavailable; the language model classifies the reply", exc_info=True)
        return None
    assert exchange.tool_input is not None  # a Jev exchange always holds its probabilities
    probabilities: dict[str, float] = exchange.tool_input["probabilities"]
    top = max(QUESTION.options, key=lambda option: probabilities[option])
    # `top` is one of the four classifications: the live call returns a probability for each option.
    return JevAnswer(classification=top, confidence=probabilities[top])  # type: ignore[arg-type]
