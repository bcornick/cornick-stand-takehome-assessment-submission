# ABOUTME: The render_message skill (10.2, A.8): a request rendered in code from the asks, with the fixed opening, the field asks grouped by the registry's sections in registry order, then the additional questions, numbered through.
# ABOUTME: Deterministic. Confirmations go in the additional group; the subject names the property.
from uwh.rules.models import Ask, AskKind, StrictModel
from uwh.rules.registry import Registry

# A.8.
OPENING = (
    "Thank you for your submission. To complete the quote we need the items below. "
    "One reply covering all of them is ideal."
)
ADDITIONAL_QUESTIONS = "Additional questions"


class RenderMessageInput(StrictModel):
    registry: Registry
    lead_label: str  # the property address, or the lead id when there is none
    asks: list[Ask]


class RenderMessageOutput(StrictModel):
    subject: str
    body: str
    ask_ids: list[str]  # in the order the body numbers them


def run(input: RenderMessageInput) -> RenderMessageOutput:
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
                f"{len(ordered) + number}. {ask.wording}" for number, ask in enumerate(asks, 1)
            ]
            blocks.append("\n".join([heading, *lines]))
            ordered += asks
    return RenderMessageOutput(
        subject=f"Information needed for your quote: {input.lead_label}",
        body="\n\n".join(blocks),
        ask_ids=[ask.ask_id for ask in ordered],
    )
