# ABOUTME: The Jev client (10.4): asks TypeSafe's Jev one choice question about a text and returns the probability of each option, served by the run mode from the live call, the live call and a recording, or the recording alone.
# ABOUTME: A recording is an Exchange under `recordings/jev/` keyed by the question's version and the hash of the shown input; the live call makes one request with no retry and raises JevUnavailable when Jev does not answer.
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx2

from uwh.runtime.hashing import canonical_json, sha256_hex
from uwh.runtime.modes import exchange_for_mode
from uwh.runtime.recordings import Exchange, RecordingKey, input_hash
from uwh.settings import RunMode

# The model alias the question is put to; the response names the model that answered.
JEV_MODEL = "jev-latest"
# The one question of a request is answered under this id.
QUESTION_ID = "answer"
ENDPOINT = "/v1/systemone"


class JevUnavailable(Exception):
    """Jev did not return the probabilities of a choice question: a transport failure, an error
    status or a response of another shape."""


@dataclass(frozen=True)
class ChoiceQuestion:
    """A choice question: what Jev decides and the options, each with its description."""

    skill: str
    instructions: str
    options: Mapping[str, str]

    @property
    def version(self) -> str:
        """The question version: a change to anything Jev is told changes it."""
        return sha256_hex(
            canonical_json(
                {"model": JEV_MODEL, "instructions": self.instructions, "options": self.options}
            )
        )


# Makes the live call for the question about `state`, to be stored under `key`.
type LiveCall = Callable[[ChoiceQuestion, str, RecordingKey], Exchange]


def jev_call(http: httpx2.Client) -> LiveCall:
    """The live call: one POST to the systemone endpoint, never retried. `http` carries the base URL,
    the bearer key and the timeout. The probabilities are stored as the exchange's `tool_input`."""

    def call(question: ChoiceQuestion, state: str, key: RecordingKey) -> Exchange:
        request = {
            "state": state,
            "model": JEV_MODEL,
            "questions": {
                QUESTION_ID: {
                    "type": "choice",
                    "instructions": question.instructions,
                    "criteria": dict(question.options),
                }
            },
        }
        try:
            response = http.post(ENDPOINT, json=request)
            response.raise_for_status()
            body = response.json()
            probabilities = body["answers"][QUESTION_ID]["probabilities"]
            return Exchange(
                skill=key.skill,
                prompt_version=key.prompt_version,
                input_hash=key.input_hash,
                input={"state": state, "options": dict(question.options)},
                model_id=body["model"],
                request_id=response.headers.get("x-request-id", ""),
                stop_reason="",
                tokens_in=body["usage"]["input_tokens"],
                tokens_out=body["usage"]["output_tokens"],
                tool_input={
                    "probabilities": {
                        option: float(probabilities[option]) for option in question.options
                    }
                },
            )
        except (httpx2.HTTPError, ValueError, KeyError, TypeError) as error:
            raise JevUnavailable(f"Jev gave no answer: {error!r}") from error

    return call


@dataclass(frozen=True)
class JevAccess:
    """What the run mode lets a skill ask of Jev. It exists only when the environment holds a Jev key."""

    mode: RunMode
    recordings: Path
    live: LiveCall

    def ask(self, question: ChoiceQuestion, state: str) -> Exchange:
        """The exchange for the question about `state`, by the run mode. Raises RecordingMiss in replay
        when nothing is recorded for it, and JevUnavailable when the live call gets no answer."""
        shown = {"state": state, "options": question.options}
        key = RecordingKey(question.skill, question.version, input_hash(shown))
        return exchange_for_mode(
            self.mode, self.recordings, key, lambda: self.live(question, state, key)
        )
