# ABOUTME: Tests the build_quote_packet skill (10.5): every effect of a plan lands on its own line with its deadline in its section, money reads as dollars, no rule id reaches the producer, the not-evaluated notes follow, and a plan that holds a decline or anything open is refused.
# ABOUTME: The packet body is compared whole for a plan that holds one effect of each type, so a missing, merged or misplaced line fails.
from typing import Any

import pytest

from uwh.rules.models import ActionPlan, OpenChoice, RuleTrace, UndecidedPage
from uwh.skills.build_quote_packet.skill import (
    BuildQuotePacketInput,
    Coverage,
    OPENING,
    run,
)

COVERAGES = {
    "coverage_a": Coverage(label="Coverage A (Dwelling)", value=875000),
    "coverage_e": Coverage(label="Coverage E (Liability)", value="100000"),
}


def planned(effect: dict[str, Any], *, committed: bool = True) -> dict[str, Any]:
    return {
        "effect": effect,
        "trace": RuleTrace(board_path=["01:X"]).model_dump(),
        "committed": committed,
    }


def plan(*effects: dict[str, Any], **fields: Any) -> ActionPlan:
    return ActionPlan.model_validate(
        {"effects": [planned(e) for e in effects], "not_evaluated": [], **fields}
    )


def build(the_plan: ActionPlan) -> str:
    return run(
        BuildQuotePacketInput(lead_label="8924 Lakeview Blvd", plan=the_plan, coverages=COVERAGES)
    ).body


def test_every_effect_is_on_its_own_line_with_its_deadline_and_no_rule_id() -> None:
    body = build(
        plan(
            {"type": "surcharge", "rule": "S-1", "percent": 15, "deadline": "first_term"},
            {"type": "surcharge", "rule": "S-2", "percent": 25},
            {
                "type": "coverage_adjustment",
                "rule": "C-1",
                "field": "coverage_a",
                "proposed_value": 900000,
                "deadline": "underwriting_period",
            },
            {
                "type": "requirement",
                "rule": "R-1",
                "text": "Send the roof inspection.",
                "deadline": "within_30_days_of_bind",
            },
            {
                "type": "requirement",
                "rule": "R-2",
                "text": "Confirm the roof class.",
                "deadline": "first_term",
            },
            {
                "type": "requirement",
                "rule": "R-3",
                "text": "Confirm the siding.",
                "deadline": "underwriting_period",
            },
            {
                "type": "requirement",
                "rule": "R-4",
                "text": "Confirm the roof replacement.",
                "deadline": "within_60_days",
            },
            {"type": "exclusion_or_endorsement", "rule": "E-1", "text": "Liability is excluded."},
            {"type": "advisory", "rule": "A-1", "text": "Siding is vinyl."},
            {
                "type": "obligation",
                "rule": "O-1",
                "text": "Inspect the panel.",
                "owner": "underwriting",
                "trigger": "bind",
            },
            {"type": "no_action", "rule": "N-1"},
            {"type": "no_action", "rule": "N-2"},
            not_evaluated=[
                {
                    "ref": "plumbing",
                    "text": "The Plumbing page is not evaluated.",
                    "producer_text": "Plumbing was not reviewed for this quote.",
                }
            ],
        )
    )

    assert body == "\n\n".join(
        [
            OPENING,
            "Coverages as submitted\n- Coverage A (Dwelling): $875,000\n- Coverage E (Liability): $100,000",
            "Surcharges\n- 15% surcharge (for the first term)\n- 25% surcharge",
            "Coverage adjustments\n- Coverage A (Dwelling): submitted $875,000, proposed $900,000 (for the underwriting period)",
            "Requirements\n- Send the roof inspection. (within 30 days of bind)"
            "\n- Confirm the roof class. (within the first term)"
            "\n- Confirm the siding. (within the underwriting period)"
            "\n- Confirm the roof replacement. (within 60 days)",
            "Exclusions and endorsements\n- Liability is excluded.",
            "Advisories\n- Siding is vinyl.",
            "Obligations after binding\n- Inspect the panel. (owner: underwriting; when: bind)",
            "Not reviewed\n- Plumbing was not reviewed for this quote.",
        ]
    )


@pytest.mark.parametrize(
    "refused",
    [
        plan({"type": "decline", "rule": "D-1"}, proposed_decline=True),
        plan(undecided=[UndecidedPage(graph="fire_simulation", waits_on=["p_f"]).model_dump()]),
        plan(
            open_choices=[
                OpenChoice(
                    choice_id="I13.fire_fail", options=["decline"], prompt="p", show=[]
                ).model_dump()
            ]
        ),
        plan(catalogue_questions=["willing_to_mitigate"]),
    ],
)
def test_a_plan_with_a_decline_or_anything_open_is_refused(refused: ActionPlan) -> None:
    with pytest.raises(ValueError, match="nothing declined or open"):
        build(refused)
