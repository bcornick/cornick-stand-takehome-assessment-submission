# ABOUTME: Tests the render_message skill (10.2, A.8) on the asks of lead 004's request: numbering runs through the registry's section groups in registry order, and a confirmation goes under "Additional questions".
# ABOUTME: The asks are lead 004's, with the stored wording; they are passed out of order to show the body follows the registry and not the input.
from tests.api.helpers import REGISTRY
from uwh.rules.models import Ask, AskKind
from uwh.rules.registry import load_registry
from uwh.skills.render_message.skill import OPENING, RenderMessageInput, run


def field_request(name: str, wording: str) -> Ask:
    return Ask(
        ask_id=name,
        kind=AskKind.field_request,
        fields=[name],
        reason="The registry requires it to quote.",
        wording=wording,
    )


LEAD_004_ASKS = [
    field_request("coverage_a", "What Coverage A (dwelling) amount is requested?"),
    field_request("property_purchase_date", "When was the property purchased?"),
    field_request("num_stories", "How many stories does the home have?"),
    field_request(
        "fire_department_type",
        "Is the fire department career, mostly career, mostly volunteer or volunteer?",
    ),
    Ask(
        ask_id="no_residents_in_primary_home",
        kind=AskKind.confirmation,
        fields=["no_residents_in_primary_home"],
        reason="Values reported for these fields conflict.",
        wording="The number of people living in the home is listed as 0. Can you confirm that number?",
    ),
]


def test_the_asks_are_numbered_through_the_section_groups_with_confirmations_last() -> None:
    rendered = run(
        RenderMessageInput(
            registry=load_registry(str(REGISTRY)),
            lead_label="14 Oak St",
            asks=list(reversed(LEAD_004_ASKS)),
        )
    )

    assert rendered.body == "\n\n".join(
        [
            OPENING,
            "Primary Coverages\n1. What Coverage A (dwelling) amount is requested?",
            "Property\n2. When was the property purchased?",
            "Construction\n3. How many stories does the home have?",
            "Protection\n4. Is the fire department career, mostly career, mostly volunteer or volunteer?",
            "Additional questions\n5. The number of people living in the home is listed as 0. Can you confirm that number?",
        ]
    )
    assert rendered.ask_ids == [
        "coverage_a",
        "property_purchase_date",
        "num_stories",
        "fire_department_type",
        "no_residents_in_primary_home",
    ]
    assert rendered.subject == "Information needed for your quote: 14 Oak St"
