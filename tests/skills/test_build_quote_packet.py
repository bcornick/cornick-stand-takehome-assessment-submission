# ABOUTME: Tests the build_quote_packet skill (10.5) guard and what stays out of the packet: a plan that holds a decline or anything open is refused, and an advisory for the underwriter alone is left out.
# ABOUTME: Each plan is built from real plan models; the packet body is the skill's own output.
from typing import Any

import pytest

from uwh.rules.models import ActionPlan, OpenChoice, RuleTrace, UndecidedPage
from uwh.skills.build_quote_packet.skill import BuildQuotePacketInput, Coverage, run

COVERAGES = {"coverage_a": Coverage(label="Coverage A (Dwelling)", value=875000)}


def plan(*effects: dict[str, Any], **fields: Any) -> ActionPlan:
    planned = [
        {"effect": e, "trace": RuleTrace(board_path=["01:X"]).model_dump(), "committed": True}
        for e in effects
    ]
    return ActionPlan.model_validate({"effects": planned, "not_evaluated": [], **fields})


def build(the_plan: ActionPlan) -> str:
    return run(
        BuildQuotePacketInput(lead_label="8924 Lakeview Blvd", plan=the_plan, coverages=COVERAGES)
    ).body


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


def test_an_advisory_for_the_underwriter_alone_is_left_out_of_the_packet() -> None:
    body = build(
        plan(
            {"type": "advisory", "rule": "A-1", "text": "Siding is vinyl."},
            {
                "type": "advisory",
                "rule": "PP-1",
                "text": "A decline was overridden.",
                "internal": True,
            },
        )
    )

    assert "Siding is vinyl." in body and "overridden" not in body
