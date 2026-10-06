# ABOUTME: The render_message skill (10.1, 10.2, A.8): a request rendered in code from the asks, with the fixed opening, the field asks grouped by the registry's sections in registry order, then the additional questions, numbered through; and the fixed decline notice.
# ABOUTME: Deterministic. Confirmations and catalogue questions go in the additional group; the subject names the property; the decline notice states no reason.
import re
from typing import Literal

from uwh.rules.models import Ask, AskKind, StrictModel
from uwh.rules.registry import Registry

# A.8.
OPENING = (
    "Thank you for your submission. To complete the quote we need the items below. "
    "One reply covering all of them is ideal."
)
ADDITIONAL_QUESTIONS = "Additional questions"
# 10.1: the decline notice is a fixed template; a message carries no decline reason.
DECLINE_NOTICE = (
    "Thank you for your submission. After review we are unable to offer coverage for this "
    "property. We appreciate the opportunity to consider it."
)


def _addressed_to_applicant(wording: str) -> str:
    """The stored wording, which speaks of the applicant to a producer, written to the applicant (10.3)."""
    return re.sub(r"\bthe applicant\b", "you", re.sub(r"\bthe applicant's\b", "your", wording))


class RenderMessageInput(StrictModel):
    kind: Literal["request", "decline_notice"] = "request"
    registry: Registry
    lead_label: str  # the property address, or the lead id when there is none
    asks: list[Ask]  # the asks of a request; a decline notice has none
    to_applicant: bool = (
        False  # the applicant is the recipient (a `direct_web` lead): wording says "you"
    )


class RenderMessageOutput(StrictModel):
    subject: str
    body: str
    ask_ids: list[str]  # in the order the body numbers them


def run(input: RenderMessageInput) -> RenderMessageOutput:
    if input.kind == "decline_notice":
        return RenderMessageOutput(
            subject=f"Regarding your submission: {input.lead_label}",
            body=DECLINE_NOTICE,
            ask_ids=[],
        )
    groups: dict[str, list[Ask]] = {field.section: [] for field in input.registry.values()}
    groups[ADDITIONAL_QUESTIONS] = []
    for ask in input.asks:
        if ask.kind in (AskKind.field_request, AskKind.follow_on_question):
            groups[input.registry[ask.ask_id].section].append(ask)
        else:
            groups[ADDITIONAL_QUESTIONS].append(ask)
    blocks = [OPENING]
    ordered: list[Ask] = []
    for heading, asks in groups.items():
        if asks:
            lines = [
                f"{len(ordered) + number}. "
                f"{_addressed_to_applicant(ask.wording) if input.to_applicant else ask.wording}"
                for number, ask in enumerate(asks, 1)
            ]
            blocks.append("\n".join([heading, *lines]))
            ordered += asks
    return RenderMessageOutput(
        subject=f"Information needed for your quote: {input.lead_label}",
        body="\n\n".join(blocks),
        ask_ids=[ask.ask_id for ask in ordered],
    )
