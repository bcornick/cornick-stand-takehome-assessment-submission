# ABOUTME: Tests what read_reply's code does with a model's reading (A.9, 10.4): locating each quote in the reply, dropping what is not asked or does not fit the field, and the repeat then abstention on an invalid tool input.
# ABOUTME: The checks run on hand-made readings, since they test our code and not the model; the model's own reading of the fixture reply is tested in replay from the committed recording.
from pathlib import Path
from typing import Any

import pytest

from tests.api.helpers import FIXTURE_REPLIES, RECORDINGS, REGISTRY
from uwh.rules.registry import load_registry
from uwh.runtime.event_types import Candidate, LocatedCandidate
from uwh.runtime.model import ModelAccess
from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    input_hash,
    prompt_version,
    write_recording,
)
from uwh.skills.read_reply import skill
from uwh.skills.read_reply.skill import (
    Abstention,
    OpenAsk,
    ReadReplyInput,
    Reading,
    ReplyReading,
)


def asks_for(*fields: str) -> list[OpenAsk]:
    return skill.open_asks(list(fields), load_registry(str(REGISTRY)))


BODY = "We closed in July 2019 on 2019-07-12. The panel is a Square D. Panel again: Square D."
INPUT = ReadReplyInput(
    body=BODY, asks=asks_for("property_purchase_date", "electrical_panel_brand", "year_built")
)


def candidate(ask_id: str, value: str | int | float | bool, quote: str) -> Candidate:
    return Candidate(ask_id=ask_id, field=ask_id, value=value, quote=quote)


def reading(*candidates: Candidate) -> ReplyReading:
    return ReplyReading(classification="answers_some", candidates=list(candidates))


def test_a_quote_is_located_at_its_first_occurrence_and_the_value_is_normalised() -> None:
    result = skill.interpret(
        reading(
            candidate("electrical_panel_brand", "Square D", "Square D"),
            candidate("property_purchase_date", "2019-07-12", "2019-07-12"),
            candidate("year_built", "1987", "closed"),
        ),
        INPUT,
    )

    first_panel = BODY.index("Square D")
    assert result.dropped == []
    assert [(c.ask_id, c.value, c.span_start, c.span_end) for c in result.candidates] == [
        ("electrical_panel_brand", "Square D", first_panel, first_panel + len("Square D")),
        (
            "property_purchase_date",
            "2019-07-12",
            BODY.index("2019-07-12"),
            BODY.index("2019-07-12") + 10,
        ),
        ("year_built", 1987, BODY.index("closed"), BODY.index("closed") + len("closed")),
    ]
    assert all(BODY[c.span_start : c.span_end] == c.quote for c in result.candidates)


@pytest.mark.parametrize(
    ("invalid", "why"),
    [
        (candidate("electrical_panel_brand", "Square D", "Siemens"), "quote not in the reply"),
        (candidate("electrical_panel_brand", "Square D", "square d"), "quote is case sensitive"),
        (candidate("roof_material", "Slate", "Square D"), "field not asked"),
        (
            Candidate(
                ask_id="electrical_panel_brand",
                field="roof_material",
                value="Slate",
                quote="Square D",
            ),
            "field is not the ask's",
        ),
        (candidate("electrical_panel_brand", "Fuse Box", "Square D"), "not an option"),
        (candidate("property_purchase_date", "July 2019", "closed in July 2019"), "not a date"),
        (candidate("property_purchase_date", "2019-13-45", "2019"), "not a calendar date"),
        (candidate("year_built", "nineteen eighty", "closed"), "not an integer"),
        (candidate("year_built", True, "closed"), "a boolean is not an integer"),
    ],
)
def test_a_candidate_that_fails_a_check_is_dropped_and_returned_as_the_model_gave_it(
    invalid: Candidate, why: str
) -> None:
    result = skill.interpret(reading(invalid), INPUT)

    assert result.candidates == [], why
    assert result.dropped == [invalid], why


def test_the_other_candidates_of_a_reading_survive_a_dropped_one() -> None:
    kept = candidate("electrical_panel_brand", "Square D", "Square D")
    dropped = candidate("property_purchase_date", "2019-07-12", "closed on the 12th")

    result = skill.interpret(reading(dropped, kept), INPUT)

    assert [c.ask_id for c in result.candidates] == ["electrical_panel_brand"]
    assert result.dropped == [dropped]


def model_returning(
    tmp_path: Path, tool_input: dict[str, Any] | None
) -> tuple[ModelAccess, Exchange]:
    """A replay model whose one recording holds the tool input; replay serves it for every call."""
    call = skill.forced_call(INPUT)
    key = RecordingKey("read_reply", prompt_version(call.prompt_file), input_hash(call.shown))
    exchange = Exchange(
        skill=key.skill,
        prompt_version=key.prompt_version,
        input_hash=key.input_hash,
        input=dict(call.shown),
        model_id="deepseek-flash",
        request_id="req",
        stop_reason="tool_use" if tool_input is not None else "refusal",
        tokens_in=1,
        tokens_out=1,
        tool_input=tool_input,
    )
    write_recording(tmp_path, key, exchange)
    return ModelAccess("replay", tmp_path, None), exchange


def test_the_fixture_reply_of_lead_008_is_read_from_its_recording() -> None:
    body = (FIXTURE_REPLIES / "LEAD-00000042-008.txt").read_text(encoding="utf-8")
    asks = asks_for("property_purchase_date", "electrical_panel_brand")

    result, exchanges = skill.run(
        ReadReplyInput(body=body, asks=asks), ModelAccess("replay", RECORDINGS, None)
    )

    assert isinstance(result, Reading) and result.classification == "answers_all"
    assert result.dropped == []
    assert [(c.ask_id, c.value) for c in result.candidates] == [
        ("property_purchase_date", "2019-07-12"),
        ("electrical_panel_brand", "Square D"),
    ]
    for c in result.candidates:  # the spans are computed by code from the stored reply
        assert body[c.span_start : c.span_end] == c.quote
    assert len(exchanges) == 1


def test_an_invalid_tool_input_repeats_the_call_once_then_abstains(tmp_path: Path) -> None:
    model, _ = model_returning(tmp_path, {"classification": "maybe", "candidates": []})

    result, exchanges = skill.run(INPUT, model)

    assert result == Abstention(reason="invalid_tool_input")
    assert len(exchanges) == 2


def test_a_refusal_abstains_without_a_repeat(tmp_path: Path) -> None:
    model, _ = model_returning(tmp_path, None)

    result, exchanges = skill.run(INPUT, model)

    assert result == Abstention(reason="refusal")
    assert len(exchanges) == 1


def test_a_valid_tool_input_is_read_with_its_exchange(tmp_path: Path) -> None:
    tool_input = {
        "classification": "answers_some",
        "candidates": [
            {
                "ask_id": "electrical_panel_brand",
                "field": "electrical_panel_brand",
                "value": "Square D",
                "quote": "Square D",
            }
        ],
    }
    model, recorded = model_returning(tmp_path, tool_input)

    result, exchanges = skill.run(INPUT, model)

    assert isinstance(result, Reading) and result.classification == "answers_some"
    assert [type(c) for c in result.candidates] == [LocatedCandidate]
    assert exchanges == [recorded]
