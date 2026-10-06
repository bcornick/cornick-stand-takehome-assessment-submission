# ABOUTME: Tests the four playbook pages built in milestone 2 (Profile, Occupancy, Fire Simulation, Post & Pier) through the evaluate_playbook skill: the effects and board path each value reaches, the band boundaries the interpretation rows name, and what is left open.
# ABOUTME: Each table starts from lead 008's facts, a lead that no page of these four applies to, and changes only the values named; a None value makes the fact unknown.
from typing import Any

import pytest
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


def plan_for(rulings: Rulings | None = None, **changes: JsonValue) -> ActionPlan:
    return run(EvaluatePlaybookInput(facts=lead_008(**changes), rulings=rulings or Rulings()))


def effects(plan: ActionPlan, prefix: str, *, committed: bool = True) -> set[tuple[str, str]]:
    """The (effect type, rule) pairs of one page's rules, committed or possible."""
    return {
        (p.effect.type, p.effect.rule)
        for p in plan.effects
        if p.effect.rule.startswith(prefix) and p.committed == committed
    }


def path_of(plan: ActionPlan, rule: str) -> list[str]:
    (planned,) = [p for p in plan.effects if p.effect.rule == rule]
    return planned.trace.board_path


# ---- Profile -----------------------------------------------------------------------------------

SPOTLIGHT_EFFECTS = {
    ("exclusion_or_endorsement", "PF-1"),
    ("advisory", "PF-2"),
    ("advisory", "PF-3"),
    ("advisory", "PF-4"),
}
HIGH_EFFECTS = {("exclusion_or_endorsement", "PF-5"), ("advisory", "PF-6")}


@pytest.mark.parametrize(
    ("kyc_score", "expected", "branch"),
    [
        (5, set(), None),  # I02: the page does not apply
        (6, SPOTLIGHT_EFFECTS, ["02:ROOT", "02:SPOT", "02:SPOT1"]),
        (7, SPOTLIGHT_EFFECTS, ["02:ROOT", "02:SPOT", "02:SPOT1"]),
        (8, HIGH_EFFECTS, ["02:ROOT", "02:HIGH", "02:HIGH1"]),
        (10, HIGH_EFFECTS, ["02:ROOT", "02:HIGH", "02:HIGH1"]),
    ],
)
def test_profile_carries_the_liability_exclusion_and_every_later_rung_as_an_advisory(
    kyc_score: int, expected: set[tuple[str, str]], branch: list[str] | None
) -> None:
    plan = plan_for(kyc_score=kyc_score)

    assert effects(plan, "PF-") == expected
    assert not plan.proposed_decline  # the decline rungs are the underwriter's, not effects
    if branch is not None:
        first_rung = "PF-1" if kyc_score <= 7 else "PF-5"
        assert path_of(plan, first_rung) == branch
        # The later rungs are for the underwriter alone: the producer's packet carries the first.
        later = [p.effect for p in plan.effects if p.effect.type == "advisory"]
        assert later and all(effect.internal for effect in later)  # type: ignore[union-attr]


def test_a_later_rung_of_the_ladder_follows_the_boxes_of_the_rungs_before_it() -> None:
    plan = plan_for(kyc_score=6)

    assert path_of(plan, "PF-2") == ["02:ROOT", "02:SPOT", "02:SPOT1", "02:SPOT2", "02:SPOT3"]
    assert path_of(plan, "PF-4") == [
        "02:ROOT",
        "02:SPOT",
        "02:SPOT1",
        "02:SPOT2",
        "02:SPOT3",
        "02:SPOT4",
        "02:SPOT5",
        "02:SPOT6",
        "02:DECLINE",
    ]


def test_profile_is_undecided_while_the_score_is_unknown() -> None:
    plan = plan_for(kyc_score=None)

    assert [(u.graph, u.waits_on) for u in plan.undecided if u.graph == "profile"] == [
        ("profile", ["kyc_score"])
    ]


# ---- Occupancy ---------------------------------------------------------------------------------

VACANT_MODIFICATIONS = {
    ("surcharge", "OC-8"),
    ("exclusion_or_endorsement", "OC-9"),
    ("exclusion_or_endorsement", "OC-10"),
    ("requirement", "OC-11"),
    ("obligation", "OC-12"),
}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"is_rental": "Long-Term Rentals", "has_primary_policy_with_stand": True},
            {("surcharge", "OC-1")},
        ),
        (
            {"is_rental": "Short-Term Rentals", "has_primary_policy_with_stand": True},
            {("surcharge", "OC-2"), ("exclusion_or_endorsement", "OC-3")},
        ),
        (
            {
                "is_rental": "Long-Term Rentals",
                "has_primary_policy_with_stand": False,
                "broker_tier": "Tier 1",
            },
            {("surcharge", "OC-4")},
        ),
        ({**UNOCCUPIED, "months_unoccupied": 1}, VACANT_MODIFICATIONS),  # 1 month is under 60 days
        ({**UNOCCUPIED, "months_unoccupied": 3}, {("decline", "OC-13")}),
        ({**UNOCCUPIED, "months_unoccupied": 8}, {("decline", "OC-13")}),
        ({"months_unoccupied": 8, "has_primary_policy_with_stand": False}, {("decline", "OC-7")}),
        ({"listed_for_sale": True}, {("decline", "OC-14")}),
        ({"months_unoccupied": 0, "is_rental": "No", "listed_for_sale": False}, set()),
    ],
)
def test_occupancy_takes_the_branch_the_values_select(
    changes: dict[str, Any], expected: set[tuple[str, str]]
) -> None:
    plan = plan_for(**changes)

    assert effects(plan, "OC-") == expected
    assert plan.proposed_decline == any(kind == "decline" for kind, _ in expected)
    assert plan.open_choices == []


def test_occupancy_modifications_apply_for_the_duration_of_non_occupancy() -> None:
    plan = plan_for(**UNOCCUPIED)

    by_rule = {p.effect.rule: p.effect for p in plan.effects}
    assert by_rule["OC-8"].deadline == "duration_of_non_occupancy"  # type: ignore[union-attr]
    assert by_rule["OC-11"].deadline == "duration_of_non_occupancy"  # type: ignore[union-attr]
    assert path_of(plan, "OC-8") == ["03:ROOT", "03:UNOCC", "03:V_P", "03:LT60", "03:MODS"]


@pytest.mark.parametrize(
    ("option", "expected"),
    [("under_60_days", VACANT_MODIFICATIONS), ("over_60_days", {("decline", "OC-13")})],
)
def test_exactly_two_months_is_the_underwriters_choice_and_the_ruling_takes_its_branch(
    option: str, expected: set[tuple[str, str]]
) -> None:
    two_months = {**UNOCCUPIED, "months_unoccupied": 2}
    open_plan = plan_for(**two_months)
    ruled = plan_for(Rulings(choices={"I07.two_months": option}), **two_months)

    assert [c.choice_id for c in open_plan.open_choices] == ["I07.two_months"]
    assert open_plan.open_choices[0].show == ["months_unoccupied"]
    assert effects(open_plan, "OC-") == set()  # nothing is committed beneath the choice
    assert effects(open_plan, "OC-", committed=False) == VACANT_MODIFICATIONS | {
        ("decline", "OC-13")
    }
    assert not open_plan.proposed_decline
    assert [u.waits_on for u in open_plan.undecided if u.graph == "occupancy"] == [
        ["I07.two_months"]
    ]
    assert effects(ruled, "OC-") == expected
    assert ruled.open_choices == []
    assert ruled.effects[0].trace.choice_ids == ["I07.two_months"]


@pytest.mark.parametrize(
    ("option", "expected"),
    [("exception", {("surcharge", "OC-5")}), ("decline", {("decline", "OC-6")})],
)
def test_a_rental_with_no_primary_policy_and_no_tier_1_broker_is_the_underwriters_choice(
    option: str, expected: set[tuple[str, str]]
) -> None:
    rental = {
        "is_rental": "Long-Term Rentals",
        "has_primary_policy_with_stand": False,
        "broker_tier": "Tier 2",
    }

    open_plan = plan_for(**rental)
    ruled = plan_for(Rulings(choices={"I09.rental_exception": option}), **rental)

    assert [c.choice_id for c in open_plan.open_choices] == ["I09.rental_exception"]
    assert effects(ruled, "OC-") == expected


def test_occupancy_is_undecided_while_the_months_unoccupied_are_in_an_open_conflict() -> None:
    # An open conflict makes the field unknown to the graphs (9.6): lead 003's three months.
    plan = plan_for(months_unoccupied=None)

    assert [(u.graph, u.waits_on) for u in plan.undecided if u.graph == "occupancy"] == [
        ("occupancy", ["months_unoccupied"])
    ]
    assert effects(plan, "OC-") == set()


# ---- Fire Simulation ---------------------------------------------------------------------------

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


# I12: the hand cases at 0.21 and 0.54 record that the threshold is this submission's invention,
# since no generated lead falls between 0.20 and 0.55.
@pytest.mark.parametrize(
    ("p_f", "applies"), [(0.21, False), (0.50, False), (0.51, True), (0.54, True)]
)
def test_fire_simulation_fails_above_a_fire_probability_of_one_half(
    p_f: float, applies: bool
) -> None:
    plan = plan_for(p_f=p_f)

    assert [c.choice_id for c in plan.open_choices] == (["I13.fire_fail"] if applies else [])


def test_a_failed_fire_simulation_is_one_open_choice_with_the_legacy_values_shown() -> None:
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
    assert plan.catalogue_questions == []  # the mitigation question waits for the choice
    assert not plan.proposed_decline  # a decline beneath the choice is possible, not committed
    assert ("decline", "FS-1") in effects(plan, "FS-", committed=False)
    assert [(u.graph, u.waits_on) for u in plan.undecided if u.graph == "fire_simulation"] == [
        ("fire_simulation", ["I13.fire_fail"])
    ]


def test_choosing_to_decline_a_failed_fire_simulation_proposes_the_decline_and_shows_no_card() -> (
    None
):
    plan = plan_for(Rulings(choices={"I13.fire_fail": "decline"}), **LEAD_003_FIRE)

    assert plan.proposed_decline and plan.open_choices == []
    assert path_of(plan, "FS-1") == ["04:ROOT", "04:FAIL", "04:D_FAIL"]
    assert plan.effects[0].trace.choice_ids == ["I13.fire_fail"]


def test_legacy_underwriting_shows_the_remaining_choices_and_asks_the_mitigation_question() -> None:
    plan = plan_for(LEGACY, **LEAD_003_FIRE)

    # The slope choice is beneath moderate or light vegetation, which too-close vegetation is not.
    assert [c.choice_id for c in plan.open_choices] == ["I16.distance"]
    assert plan.catalogue_questions == ["willing_to_mitigate"]
    assert not plan.proposed_decline
    assert [u.waits_on for u in plan.undecided if u.graph == "fire_simulation"] == [
        ["I16.distance", "q:willing_to_mitigate", "road_access"]
    ]


@pytest.mark.parametrize(
    ("answers", "committed"),
    [
        ({"I16.distance": "adequate", "q:willing_to_mitigate": True}, {("advisory", "FS-2")}),
        (
            {"I16.distance": "too_close", "q:willing_to_mitigate": True},
            {("decline", "FS-4"), ("advisory", "FS-2")},
        ),
        (
            {"I16.distance": "adequate", "q:willing_to_mitigate": False},
            {("decline", "FS-3"), ("advisory", "FS-2")},
        ),
    ],
)
def test_legacy_underwriting_takes_the_branches_the_answers_select(
    answers: dict[str, Any], committed: set[tuple[str, str]]
) -> None:
    choices = {k: v for k, v in answers.items() if not k.startswith("q:")}
    facts = {k: v for k, v in answers.items() if k.startswith("q:")}
    plan = run(
        EvaluatePlaybookInput(
            facts={
                **lead_008(**{**LEAD_003_FIRE, "road_access": "Multiple Access Points"}),
                **facts,
            },
            rulings=Rulings(choices={**LEGACY.choices, **choices}),
        )
    )

    assert effects(plan, "FS-") == committed
    assert plan.proposed_decline == any(kind == "decline" for kind, _ in committed)


# The other legacy choices are answered, so the road access is the only open one.
ANSWERED_LEGACY = Rulings(
    choices={**LEGACY.choices, "I16.distance": "adequate", "I16.slope": "gentle"}
)


@pytest.mark.parametrize(
    ("road_access", "committed", "card"),
    [
        ("Multiple Access Points", {("advisory", "FS-2")}, []),
        ("Limited / Dead-end / No Turnaround", {("decline", "FS-3")}, []),
        ("Single Access Point", set(), ["I14.road_access"]),
        ("Unknown", set(), ["I14.road_access"]),
    ],
)
def test_legacy_underwriting_reads_the_road_access_by_the_rows_ruling(
    road_access: str, committed: set[tuple[str, str]], card: list[str]
) -> None:
    plan = plan_for(
        ANSWERED_LEGACY,
        p_f=0.79,
        vegetation_clearance="Adequate",
        is_7a_compliant=True,
        road_access=road_access,
    )

    assert effects(plan, "FS-") >= committed
    assert [c.choice_id for c in plan.open_choices] == card


@pytest.mark.parametrize(
    ("clearance", "card"),
    [
        ("Too Close", []),
        ("Adequate", ["I16.slope"]),
        ("Marginal", ["I15.vegetation"]),
        ("Unknown", ["I15.vegetation"]),
    ],
)
def test_legacy_underwriting_reads_the_vegetation_clearance_by_the_rows_ruling(
    clearance: str, card: list[str]
) -> None:
    plan = plan_for(
        LEGACY,
        p_f=0.79,
        vegetation_clearance=clearance,
        road_access="Multiple Access Points",
        is_7a_compliant=True,
        min_distance_to_neighbor_ft=60,
    )

    assert sorted(c.choice_id for c in plan.open_choices if c.choice_id != "I16.distance") == card


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


def test_the_old_roof_advisory_cites_the_row_and_the_rental_exception_cites_both_boxes() -> None:
    old_roof = plan_for(
        roof_replacement_year=2005, p_f=0.16, roof_material="Asphalt Fiberglass Composite"
    )
    rental = plan_for(
        Rulings(choices={"I09.rental_exception": "exception"}),
        is_rental="Long-Term Rentals",
        has_primary_policy_with_stand=False,
        broker_tier="Tier 2",
    )

    assert path_of(old_roof, "RF-5") == ["05:ROOT", "I52"]
    assert path_of(rental, "OC-5") == [
        "03:ROOT",
        "03:RENT",
        "03:R_NP",
        "03:LEAD",
        "03:WELL",
        "03:W15",
    ]


# ---- Post & Pier -------------------------------------------------------------------------------

PIER = {"foundation_type": "Piers"}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"post_pier_supports_living_area": True}, {("decline", "PP-1")}),  # lead 000
        ({"post_pier_supports_living_area": False, "year_built": 1999}, {("decline", "PP-2")}),
        (
            {"post_pier_supports_living_area": False, "year_built": 2000, "deck_height_ft": 8},
            {("surcharge", "PP-3")},
        ),
        (
            {"post_pier_supports_living_area": False, "year_built": 2000, "deck_height_ft": 9},
            {("surcharge", "PP-4")},
        ),
        (
            {"post_pier_supports_living_area": False, "year_built": 2000, "deck_height_ft": 12},
            {("surcharge", "PP-4")},
        ),
        (
            {"post_pier_supports_living_area": False, "year_built": 2000, "deck_height_ft": 13},
            {("decline", "PP-5")},
        ),
    ],
)
def test_post_and_pier_takes_the_branch_the_values_select(
    changes: dict[str, Any], expected: set[tuple[str, str]]
) -> None:
    plan = plan_for(**PIER, **changes)

    assert effects(plan, "PP-") == expected
    assert plan.proposed_decline == any(kind == "decline" for kind, _ in expected)


def test_a_slab_foundation_does_not_reach_the_post_and_pier_page() -> None:
    assert effects(plan_for(post_pier_supports_living_area=True), "PP-") == set()


def test_a_high_deck_on_a_home_built_in_2000_or_later_declines_whatever_the_supports_field_holds() -> (
    None
):
    plan = plan_for(**PIER, year_built=2005, deck_height_ft=15)

    (trace,) = plan.declines_on_every_branch
    assert plan.proposed_decline and effects(plan, "PP-") == set()
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


def test_a_deck_above_twelve_feet_on_a_home_built_in_2000_or_later_declines_when_the_supports_are_known() -> (
    None
):
    plan = plan_for(
        **PIER, post_pier_supports_living_area=False, year_built=2005, deck_height_ft=15
    )

    assert plan.proposed_decline and effects(plan, "PP-") == {("decline", "PP-5")}


@pytest.mark.parametrize(
    "unknown",
    [
        {"post_pier_supports_living_area": None},
        {"year_built": None, "post_pier_supports_living_area": False},
    ],
)
def test_post_and_pier_is_undecided_when_an_unknown_value_leaves_a_branch_that_does_not_decline(
    unknown: dict[str, Any],
) -> None:
    plan = plan_for(**PIER, **{"year_built": 2005, "deck_height_ft": 8, **unknown})

    assert not plan.proposed_decline and plan.declines_on_every_branch == []
    assert [u.graph for u in plan.undecided if u.graph == "post_and_pier"] == ["post_and_pier"]


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


# ---- the quote packet -------------------------------------------------------------------------


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
