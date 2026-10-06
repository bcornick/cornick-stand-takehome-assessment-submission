# ABOUTME: Tests read_reply's Jev cascade (10.4): Jev's classification is used at or above the manifest threshold and the language model's below it, with no Jev, or when Jev is unavailable.
# ABOUTME: The probability tables Jev returns are hand-built, since the tests are of our code's use of them; each is served through a recording, and the model's reading through its own.
from pathlib import Path
from typing import Any

import pytest

from tests.skills.test_read_reply import INPUT, model_returning
from uwh.runtime.jev_client import ChoiceQuestion, JevAccess, JevUnavailable
from uwh.runtime.model import ModelAccess
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.recordings import Exchange, RecordingKey, input_hash, write_recording
from uwh.skills.read_reply import jev, skill
from uwh.skills.read_reply.skill import Abstention, Reading

# The model reads the reply as off topic and finds one answer.
MODEL_READING: dict[str, Any] = {
    "classification": "off_topic",
    "candidates": [
        {
            "ask_id": "electrical_panel_brand",
            "field": "electrical_panel_brand",
            "value": "Square D",
            "quote": "Square D",
        }
    ],
}


def table(**probabilities: float) -> dict[str, float]:
    """A probability table over the four classifications; the options not named get 0."""
    return {option: probabilities.get(option, 0.0) for option in jev.QUESTION.options}


def jev_returning(tmp_path: Path, probabilities: dict[str, float]) -> JevAccess:
    """A replay Jev whose one recording, for the reply of INPUT, holds the probabilities."""
    shown = {"state": INPUT.body, "options": jev.QUESTION.options}
    key = RecordingKey("read_reply", jev.QUESTION.version, input_hash(shown))
    exchange = Exchange(
        skill=key.skill,
        prompt_version=key.prompt_version,
        input_hash=key.input_hash,
        input={},
        model_id="jev-1.13.0",
        request_id="",
        stop_reason="",
        tokens_in=1,
        tokens_out=1,
        tool_input={"probabilities": probabilities},
    )
    write_recording(tmp_path, key, exchange)

    def live(question: ChoiceQuestion, state: str, key: RecordingKey) -> Exchange:
        raise AssertionError("replay never calls Jev")

    return JevAccess("replay", tmp_path, live)


def with_jev(model: ModelAccess, access: JevAccess | None) -> ModelAccess:
    return ModelAccess(model.mode, model.recordings, model.live, access)


def read(tmp_path: Path, access: JevAccess | None) -> Reading:
    model = with_jev(model_returning(tmp_path / "model", MODEL_READING), access)
    result = skill.run(INPUT, model).result
    assert isinstance(result, Reading)
    return result


def test_the_manifest_sets_the_threshold_at_seven_tenths() -> None:
    assert jev.threshold() == 0.7


def test_jev_classifies_at_the_threshold_and_the_model_still_supplies_the_candidates(
    tmp_path: Path,
) -> None:
    access = jev_returning(tmp_path / "jev", table(answers_some=0.7, answers_all=0.3))

    result = read(tmp_path, access)

    assert (result.classification, result.classified_by, result.jev_confidence) == (
        "answers_some",
        "jev",
        0.7,
    )
    assert [c.ask_id for c in result.candidates] == ["electrical_panel_brand"]


def test_the_model_classifies_below_the_threshold_and_the_row_keeps_jevs_confidence(
    tmp_path: Path,
) -> None:
    access = jev_returning(tmp_path / "jev", table(answers_some=0.69, answers_all=0.31))

    result = read(tmp_path, access)

    assert (result.classification, result.classified_by, result.jev_confidence) == (
        "off_topic",
        "model",
        0.69,
    )


def test_the_model_classifies_when_there_is_no_jev(tmp_path: Path) -> None:
    result = read(tmp_path, None)

    assert (result.classification, result.classified_by, result.jev_confidence) == (
        "off_topic",
        "model",
        None,
    )


def test_the_model_classifies_when_jev_is_unavailable(tmp_path: Path) -> None:
    def down(question: ChoiceQuestion, state: str, key: RecordingKey) -> Exchange:
        raise JevUnavailable("down")

    result = read(tmp_path, JevAccess("live", tmp_path / "jev", down))

    assert (result.classification, result.classified_by, result.jev_confidence) == (
        "off_topic",
        "model",
        None,
    )


def test_a_replay_with_no_jev_recording_uses_the_model_and_returns_the_miss(
    tmp_path: Path,
) -> None:
    model = with_jev(
        model_returning(tmp_path / "model", MODEL_READING),
        JevAccess("replay", tmp_path / "empty", lambda question, state, key: pytest.fail("called")),
    )

    run = skill.run(INPUT, model)

    assert isinstance(run.result, Reading)
    assert (run.result.classification, run.result.classified_by) == ("off_topic", "model")
    assert isinstance(run.jev_failure, RecordingMiss)
    assert [e.model_id for e in run.exchanges] == ["deepseek-flash"]


def test_jevs_exchange_comes_first_among_the_exchanges_when_it_answers(tmp_path: Path) -> None:
    access = jev_returning(tmp_path / "jev", table(answers_some=0.9, answers_all=0.1))
    model = with_jev(model_returning(tmp_path / "model", MODEL_READING), access)

    run = skill.run(INPUT, model)

    assert [e.model_id for e in run.exchanges] == ["jev-1.13.0", "deepseek-flash"]
    assert run.jev_failure is None


def test_a_model_abstention_stands_whatever_jev_says(tmp_path: Path) -> None:
    access = jev_returning(tmp_path / "jev", table(answers_all=1.0))
    model = with_jev(model_returning(tmp_path / "model", None), access)

    assert isinstance(skill.run(INPUT, model).result, Abstention)
