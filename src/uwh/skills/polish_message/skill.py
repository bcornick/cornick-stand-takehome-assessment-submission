# ABOUTME: The polish_message skill (10.2, A.10): two forced tool calls give a rendered request a conversational opening and closing, and judge them against the request; code builds the body around the question block and checks the pieces.
# ABOUTME: The output is the rewritten body or the rejection that names the check that stopped it. A tool input that fails validation repeats the call once; a second failure, or a refusal, rejects the rewrite.
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from uwh.rules.models import StrictModel
from uwh.runtime.model import ForcedToolCall, ModelAccess, read_tool_input
from uwh.runtime.recordings import Exchange
from uwh.skills.render_message.skill import RenderMessageOutput

REWRITE_TOOL = "write_opening_and_closing"
CHECK_TOOL = "record_check"
_REWRITE_PROMPT = Path(__file__).with_name("prompt.md")
_CHECK_PROMPT = Path(__file__).with_name("check.md")

# A.10: the length caps of the two pieces, in characters.
MAX_OPENING_CHARACTERS = 600
MAX_CLOSING_CHARACTERS = 300

_NUMBERED_LINE = re.compile(r"^\s*\d+[.)]", re.MULTILINE)


class PolishInput(StrictModel):
    rendered: RenderMessageOutput  # the request as `render_message` produced it
    recipient_kind: Literal["producer", "applicant"]
    round: int


# What the first call returns: its JSON schema is the input schema of the forced tool.
class Pieces(StrictModel):
    opening: str
    closing: str


# What the second call returns. The sentence is empty on a pass.
class Verdict(StrictModel):
    verdict: Literal["pass", "fail"]
    offending_sentence: str


class Rewritten(StrictModel):
    body: str


class Rejected(StrictModel):
    """The rewrite that was not used: the stage that stopped it and why."""

    check: Literal["rewrite", "code_check", "model_check"]
    detail: str


def build_body(pieces: Pieces, rendered: RenderMessageOutput) -> str:
    """The opening, the question block exactly as rendered, then the closing."""
    return f"{pieces.opening}\n\n{rendered.question_block}\n\n{pieces.closing}"


def code_check(pieces: Pieces) -> str | None:
    """The first rule the pieces break, or None: neither holds a question mark or a numbered line,
    and each is within its cap (10.2)."""
    for name, text, cap in (
        ("opening", pieces.opening, MAX_OPENING_CHARACTERS),
        ("closing", pieces.closing, MAX_CLOSING_CHARACTERS),
    ):
        if "?" in text:
            return f"the {name} holds a question mark"
        if _NUMBERED_LINE.search(text):
            return f"the {name} holds a numbered line"
        if len(text) > cap:
            return f"the {name} is over {cap} characters"
    return None


def rewrite_call(input: PolishInput) -> ForcedToolCall:
    """The first call: the model is shown the rendered request, the recipient kind, the number of questions and the round."""
    return ForcedToolCall(
        skill="polish_message",
        prompt_file=_REWRITE_PROMPT,
        shown={
            "request": input.rendered.body,
            "recipient_kind": input.recipient_kind,
            "ask_count": len(input.rendered.ask_ids),
            "round": input.round,
        },
        tool_name=REWRITE_TOOL,
        tool_description="Write the opening and the closing of the request.",
        tool_schema=Pieces.model_json_schema(),
    )


def check_call(input: PolishInput, pieces: Pieces) -> ForcedToolCall:
    """The second call: the model is shown the rendered request and the two pieces."""
    return ForcedToolCall(
        skill="polish_message",
        prompt_file=_CHECK_PROMPT,
        shown={
            "request": input.rendered.body,
            "opening": pieces.opening,
            "closing": pieces.closing,
        },
        tool_name=CHECK_TOOL,
        tool_description="Record whether the opening and the closing add anything to the request.",
        tool_schema=Verdict.model_json_schema(),
    )


def run(
    input: PolishInput, model: ModelAccess, record: Callable[[Sequence[Exchange]], None]
) -> Rewritten | Rejected:
    """Rewrite the request. Returns the rewritten body or the rejection. `record` is given the
    exchanges of each call as the call completes, so a later call that raises leaves the earlier one
    recorded. The check call is made only for pieces the code check passes."""
    pieces, exchanges = read_tool_input(model, rewrite_call(input), Pieces)
    record(exchanges)
    if pieces is None:
        return Rejected(check="rewrite", detail="the call abstained")
    broken = code_check(pieces)
    if broken is not None:
        return Rejected(check="code_check", detail=broken)
    verdict, checked = read_tool_input(model, check_call(input, pieces), Verdict)
    record(checked)
    if verdict is None:
        return Rejected(check="model_check", detail="the call abstained")
    if verdict.verdict == "fail":
        return Rejected(check="model_check", detail=verdict.offending_sentence)
    return Rewritten(body=build_body(pieces, input.rendered))
