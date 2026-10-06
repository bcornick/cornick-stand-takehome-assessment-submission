# ABOUTME: Tests what polish_message's code does with the model's two calls (10.2, A.10): the body built around the question block, the code check on the opening and closing, and the rejection of a rewrite by either check.
# ABOUTME: The checks run on hand-made exchanges, since they test our code and not the model; the model's own rewrite of lead 008's request is tested in replay from the committed recordings.
from pathlib import Path
from typing import Any

import pytest

from tests.api.helpers import RECORDINGS, REGISTRY
from uwh.rules.data_files import read_yaml
from uwh.rules.models import Ask, AskKind
from uwh.rules.registry import load_registry
from uwh.runtime.model import ForcedToolCall, ModelAccess
from uwh.runtime.recordings import Exchange, write_recording
from uwh.skills.polish_message import skill
from uwh.skills.polish_message.skill import (
    MAX_CLOSING_CHARACTERS,
    MAX_OPENING_CHARACTERS,
    Pieces,
    PolishInput,
    Rejected,
    Rewritten,
    code_check,
)
from uwh.skills.render_message import skill as render_message

# Lead 008's first request: two registry fields, asked to a producer.
WORDING = read_yaml("wording.yaml")["fields"]
ASKS = [
    Ask(
        ask_id=field,
        kind=AskKind.field_request,
        fields=[field],
        reason="The registry requires it to quote.",
        wording=WORDING[field],
    )
    for field in ("property_purchase_date", "electrical_panel_brand")
]
RENDERED = render_message.run(
    render_message.RenderMessageInput(
        registry=load_registry(str(REGISTRY)), lead_label="14 Oak St", asks=ASKS
    )
)
INPUT = PolishInput(rendered=RENDERED, recipient_kind="producer", round=1)
OPENING = "Thanks for sending this one over."
CLOSING = "Whenever you have them, one reply is fine."


def test_the_rendered_request_is_its_fixed_opening_then_the_question_block() -> None:
    assert RENDERED.body == f"{render_message.OPENING}\n\n{RENDERED.question_block}"
    assert "1. " in RENDERED.question_block
    assert render_message.OPENING not in RENDERED.question_block


def test_the_body_is_the_opening_then_the_question_block_as_rendered_then_the_closing() -> None:
    body = skill.build_body(Pieces(opening=OPENING, closing=CLOSING), RENDERED)

    assert body == f"{OPENING}\n\n{RENDERED.question_block}\n\n{CLOSING}"


@pytest.mark.parametrize(
    ("pieces", "rejection"),
    [
        (Pieces(opening="Could you help?", closing=CLOSING), "the opening holds a question mark"),
        (Pieces(opening=OPENING, closing="Is that all?"), "the closing holds a question mark"),
        (
            Pieces(opening="Hello.\n1. One thing first.", closing=CLOSING),
            "the opening holds a numbered line",
        ),
        (
            Pieces(opening=OPENING, closing="Thanks.\n  2) Also."),
            "the closing holds a numbered line",
        ),
        (
            Pieces(opening="x" * (MAX_OPENING_CHARACTERS + 1), closing=CLOSING),
            f"the opening is over {MAX_OPENING_CHARACTERS} characters",
        ),
        (
            Pieces(opening=OPENING, closing="x" * (MAX_CLOSING_CHARACTERS + 1)),
            f"the closing is over {MAX_CLOSING_CHARACTERS} characters",
        ),
    ],
)
def test_the_code_check_rejects_a_question_a_numbered_line_and_a_piece_over_its_cap(
    pieces: Pieces, rejection: str
) -> None:
    assert code_check(pieces) == rejection


def test_the_code_check_passes_pieces_at_their_caps_and_a_year_that_starts_a_sentence() -> None:
    at_caps = Pieces(
        opening="x" * MAX_OPENING_CHARACTERS,
        closing="2019 was a good year. " + "x" * (MAX_CLOSING_CHARACTERS - 22),
    )

    assert code_check(at_caps) is None


def exchange_for(call: ForcedToolCall, tool_input: dict[str, Any] | None) -> Exchange:
    key = call.recording_key
    return Exchange(
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


def model_returning(
    tmp_path: Path, pieces: dict[str, Any] | None, verdict: dict[str, Any] | None = None
) -> ModelAccess:
    """A replay model with the recording of the rewrite call and, when `verdict` is given, of the
    check call on those pieces. A rewrite the code rejects never reaches the check call."""
    rewrite = skill.rewrite_call(INPUT)
    write_recording(tmp_path, rewrite.recording_key, exchange_for(rewrite, pieces))
    if verdict is not None and pieces is not None:
        check = skill.check_call(INPUT, Pieces.model_validate(pieces))
        write_recording(tmp_path, check.recording_key, exchange_for(check, verdict))
    return ModelAccess("replay", tmp_path, None)


def run(input: PolishInput, model: ModelAccess) -> tuple[Rewritten | Rejected, list[Exchange]]:
    """`skill.run` with the exchanges it recorded."""
    exchanges: list[Exchange] = []
    return skill.run(input, model, exchanges.extend), exchanges


PASS = {"verdict": "pass", "offending_sentence": ""}
GOOD_PIECES = {"opening": OPENING, "closing": CLOSING}


def test_both_checks_passing_gives_the_rewritten_body(tmp_path: Path) -> None:
    result, exchanges = run(INPUT, model_returning(tmp_path, GOOD_PIECES, PASS))

    assert result == Rewritten(body=skill.build_body(Pieces(**GOOD_PIECES), RENDERED))
    assert len(exchanges) == 2


def test_a_code_check_failure_rejects_the_rewrite_without_the_model_check(tmp_path: Path) -> None:
    pieces = {"opening": "Could you send these today?", "closing": CLOSING}

    result, exchanges = run(INPUT, model_returning(tmp_path, pieces))

    assert result == Rejected(check="code_check", detail="the opening holds a question mark")
    assert len(exchanges) == 1  # the model check is not called on a rewrite the code rejects


def test_a_model_check_failure_names_the_offending_sentence(tmp_path: Path) -> None:
    # Hand-built: the closing adds a deadline, which the model check is to catch. This tests our
    # code after the model, not the model.
    pieces = {"opening": OPENING, "closing": "Please send these within 48 hours."}
    fail = {"verdict": "fail", "offending_sentence": "Please send these within 48 hours."}

    result, exchanges = run(INPUT, model_returning(tmp_path, pieces, fail))

    assert result == Rejected(check="model_check", detail="Please send these within 48 hours.")
    assert len(exchanges) == 2


@pytest.mark.parametrize(
    ("bad", "calls"),
    [({"opening": OPENING}, 2), (None, 1)],
    ids=["invalid input repeats once", "refusal does not repeat"],
)
def test_a_rewrite_call_that_abstains_rejects_the_rewrite(
    tmp_path: Path, bad: dict[str, Any] | None, calls: int
) -> None:
    result, exchanges = run(INPUT, model_returning(tmp_path, bad))

    assert isinstance(result, Rejected) and result.check == "rewrite"
    assert len(exchanges) == calls


def test_a_check_call_that_abstains_rejects_the_rewrite(tmp_path: Path) -> None:
    result, _ = run(INPUT, model_returning(tmp_path, GOOD_PIECES, {"verdict": "maybe"}))

    assert isinstance(result, Rejected) and result.check == "model_check"


def test_the_two_calls_are_recorded_under_different_prompt_versions() -> None:
    rewrite = skill.rewrite_call(INPUT).recording_key
    check = skill.check_call(INPUT, Pieces(**GOOD_PIECES)).recording_key

    assert rewrite.prompt_version != check.prompt_version


def test_the_rewrite_of_lead_008_is_read_from_its_recordings() -> None:
    result, exchanges = run(INPUT, ModelAccess("replay", RECORDINGS, None))

    assert isinstance(result, Rewritten)
    assert RENDERED.question_block in result.body
    assert len(exchanges) == 2
