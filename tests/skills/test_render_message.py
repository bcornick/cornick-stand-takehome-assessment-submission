# ABOUTME: Tests the wording render_message gives a request: the stored wording of the applicant reads "you" when the applicant is the recipient and is kept for a producer.
# ABOUTME: The asks carry the stored wording of one field of the registry.
import pytest

from tests.api.helpers import REGISTRY
from uwh.rules.models import Ask, AskKind
from uwh.rules.registry import load_registry
from uwh.skills.render_message.skill import RenderMessageInput, run

DOB = Ask(
    ask_id="insured_dob",
    kind=AskKind.field_request,
    fields=["insured_dob"],
    reason="The registry requires it to quote.",
    wording="What is the applicant's date of birth?",
)
PANEL = Ask(
    ask_id="electrical_panel_brand",
    kind=AskKind.field_request,
    fields=["electrical_panel_brand"],
    reason="The registry requires it to quote.",
    wording="Who made the electrical panel?",
)


@pytest.mark.parametrize(
    ("to_applicant", "line"),
    [(True, "What is your date of birth?"), (False, "What is the applicant's date of birth?")],
    ids=["to the applicant", "to a producer"],
)
def test_a_request_says_you_to_the_applicant_and_keeps_the_wording_for_a_producer(
    to_applicant: bool, line: str
) -> None:
    rendered = run(
        RenderMessageInput(
            registry=load_registry(str(REGISTRY)),
            lead_label="14 Oak St",
            asks=[DOB],
            to_applicant=to_applicant,
        )
    )

    assert line in rendered.body


def test_one_ask_is_worded_in_the_singular_and_several_in_the_plural() -> None:
    def body(asks: list[Ask]) -> str:
        return run(
            RenderMessageInput(
                registry=load_registry(str(REGISTRY)), lead_label="14 Oak St", asks=asks
            )
        ).body

    one = body([DOB])
    two = body([DOB, PANEL])

    assert "one thing we still need" in one
    assert not any(word in one for word in ("items", "details", "covering the"))
    assert "the items below" in two
    assert "One reply covering all of them is ideal." in two
