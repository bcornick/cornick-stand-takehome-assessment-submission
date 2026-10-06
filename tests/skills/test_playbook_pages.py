# ABOUTME: Tests the properties of the playbook pages that the evaluate_playbook case tables do not state: what a choice shows and the choice a trace names, the board edges a fire simulation trace follows, a decline on every branch, an overridden decline, and the quote packet of a plan.
# ABOUTME: Each test starts from lead 008's facts, a lead that none of these pages applies to, and changes only the values named; a None value makes the fact unknown.
from pydantic import JsonValue

from tests.skills.helpers import lead_008
from uwh.rules.graphs import evaluate_graph, load_graphs
from uwh.rules.models import ActionPlan, Rulings
from uwh.skills.build_quote_packet import skill as build_quote_packet
from uwh.skills.build_quote_packet.skill import BuildQuotePacketInput
from uwh.skills.evaluate_playbook.skill import EvaluatePlaybookInput, run

# The facts that make the Occupancy page apply on a home unoccupied for some months, with a primary
# policy with Stand.
UNOCCUPIED = {"months_unoccupied": 1, "has_primary_policy_with_stand": True}
PIER = {"foundation_type": "Piers"}
# Lead 003's legacy checklist values: vegetation too close, steep slope, a neighbour at 14 feet,
# not Chapter 7A compliant, and a road access its blocked lookup leaves unknown.
LEAD_003_FIRE = {
    "p_f": 0.79,
    "vegetation_clearance": "Too Close",
    "slope_angle_deg": 30.0,
    "min_distance_to_neighbor_ft": 14,
    "is_7a_compliant": False,
    "road_access": None,
}
LEGACY = Rulings(choices={"I13.fire_fail": "legacy_underwriting"})


def plan_for(rulings: Rulings | None = None, **changes: JsonValue) -> ActionPlan:
    return run(EvaluatePlaybookInput(facts=lead_008(**changes), rulings=rulings or Rulings()))


def test_a_ruled_choice_is_named_on_the_trace_of_the_outcome_it_leads_to() -> None:
    two_months = {**UNOCCUPIED, "months_unoccupied": 2}

    open_plan = plan_for(**two_months)
    ruled = plan_for(Rulings(choices={"I07.two_months": "over_60_days"}), **two_months)

    assert open_plan.open_choices[0].show == ["months_unoccupied"]
    assert ruled.effects[0].trace.choice_ids == ["I07.two_months"]


def test_a_failed_fire_simulation_offers_decline_or_legacy_underwriting_with_the_legacy_values() -> (
    None
):
    plan = plan_for(**LEAD_003_FIRE)

    (choice,) = plan.open_choices
    assert (choice.choice_id, choice.options) == (
        "I13.fire_fail",
        ["decline", "legacy_underwriting"],
    )
    assert choice.show == [
        "p_f",
        "road_access",
        "vegetation_clearance",
        "slope_angle_deg",
        "is_7a_compliant",
        "min_distance_to_neighbor_ft",
    ]


def test_the_choice_that_declines_a_failed_fire_simulation_is_named_on_its_trace() -> None:
    plan = plan_for(Rulings(choices={"I13.fire_fail": "decline"}), **LEAD_003_FIRE)

    assert plan.effects[0].trace.choice_ids == ["I13.fire_fail"]


def test_the_fire_simulation_traces_follow_the_board_edges() -> None:
    rulings = Rulings(choices={**LEGACY.choices, "I16.distance": "adequate", "I16.slope": "gentle"})
    facts = lead_008(
        **{**LEAD_003_FIRE, "road_access": "Multiple Access Points", "q:willing_to_mitigate": False}
    )

    (graph,) = [g for g in load_graphs() if g.id == "fire_simulation"]
    paths = [p.trace.board_path for p in evaluate_graph(graph, facts, rulings).effects]

    # Unwilling to mitigate takes the board's WILL -> D_LIM edge, not the Limited box.
    unwilling = [p for p in paths if p[-1] == "04:D_LIM"]  # heavy vegetation and no 7a compliance
    assert len(unwilling) == 2
    assert all(p[-2:] == ["04:WILL", "04:D_LIM"] and "04:LIMITED" not in p for p in unwilling)
    (adequate,) = [p for p in paths if "04:ADEQ" in p]
    assert adequate[3:] == ["04:MIND", "04:ADEQ", "04:CTQ_B", "04:QUOTE", "04:MITIG"]


def test_a_decline_on_every_branch_names_the_case_each_branch_assumes() -> None:
    plan = plan_for(**PIER, year_built=2005, deck_height_ft=15)

    (trace,) = plan.declines_on_every_branch
    assert [
        (b.rule, b.board_path, [(a.field, a.when) for a in b.assumed]) for b in trace.alternatives
    ] == [
        (
            "PP-1",
            ["07:ROOT", "07:LIVING", "07:D1"],
            [("post_pier_supports_living_area", {"equals": True})],
        ),
        (
            "PP-5",
            ["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"],
            [("post_pier_supports_living_area", {"equals": False})],
        ),
    ]


def test_a_suppressed_decline_is_decided_with_an_internal_advisory_naming_the_overridden_rule() -> (
    None
):
    plan = plan_for(Rulings(suppressed_rules=["PP-1"]), **PIER, post_pier_supports_living_area=True)

    assert not plan.proposed_decline
    (advisory,) = [p.effect for p in plan.effects if p.effect.rule == "PP-1"]
    assert advisory.type == "advisory" and advisory.internal and "PP-1" in advisory.text  # type: ignore[union-attr]


def test_an_underwriters_decline_is_a_proposed_decline_with_its_reason() -> None:
    plan = plan_for(Rulings(decline_reason="Reputational risk"))

    assert plan.proposed_decline and plan.underwriter_decline == "Reputational risk"


def test_the_packet_carries_the_exclusion_the_mitigation_advisory_and_the_modifications_with_their_deadlines() -> (
    None
):
    plan = plan_for(
        Rulings(
            choices={
                "I13.fire_fail": "legacy_underwriting",
                "I16.slope": "gentle",
                "I16.distance": "adequate",
            }
        ),
        kyc_score=6,
        p_f=0.79,
        vegetation_clearance="Adequate",
        road_access="Multiple Access Points",
        is_7a_compliant=True,
        **UNOCCUPIED,
    )

    body = build_quote_packet.run(
        BuildQuotePacketInput(lead_label="8924 Lakeview Blvd", plan=plan, coverages={})
    ).body

    assert "Surcharges\n- 25% surcharge (for the duration of non-occupancy)" in body
    assert "- Liability coverage is excluded" in body  # PF-1
    assert "- A 100k AOP deductible, for the duration of non-occupancy" in body  # OC-9
    assert (
        "- A low temperature alarm or a winterized home in a cold climate (for the duration of non-occupancy)"
        in body
    )
    assert "- We will discuss a preliminary mitigation plan with you." in body  # I55
    assert "deal killer" not in body  # the fallbacks of I05 stay with the underwriter
    assert "PF-" not in body and "OC-" not in body  # no rule id reaches the producer
