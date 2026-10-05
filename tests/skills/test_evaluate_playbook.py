# ABOUTME: Tests the evaluate_playbook skill on lead 008's facts: the outcome of each page it reaches, the pages it does not reach, the not-evaluated notes, and the outcomes of the same pages on the values around each band.
# ABOUTME: Lead 008's values are the captured seed-42 lead plus the fetched and derived facts its first pass adds; each variation changes only the values named.
import pytest
from pydantic import JsonValue

from tests.skills.helpers import lead_008
from uwh.skills.evaluate_playbook.skill import EvaluatePlaybookInput, run


def outcomes(**changes: JsonValue) -> dict[tuple[str, str], list[str]]:
    """(effect type, rule) -> the board path of the outcome that produced it."""
    plan = run(EvaluatePlaybookInput(facts=lead_008(**changes)))
    return {(p.effect.type, p.effect.rule): p.trace.board_path for p in plan.effects}


def test_lead_008_reaches_roof_siding_and_replacement_cost_and_quotes_as_submitted() -> None:
    plan = run(EvaluatePlaybookInput(facts=lead_008()))

    assert {(p.effect.type, p.effect.rule, tuple(p.trace.board_path)) for p in plan.effects} == {
        ("no_action", "RF-1", ("05:ROOT", "05:CA", "05:OK_A")),  # Class A roof
        ("no_action", "SD-1", ("06:ROOT", "06:NC", "06:NC_OK")),  # stucco is class B
        ("no_action", "RC-2", ("12:ROOT", "12:AT", "12:AT_R")),  # 875,000 / 928,992 is 0.94
    }
    assert all(p.committed for p in plan.effects)
    assert not plan.proposed_decline and plan.undecided == []


def test_lead_008_is_noted_as_not_evaluated_on_the_two_pages_that_apply_to_every_lead() -> None:
    plan = run(EvaluatePlaybookInput(facts=lead_008()))

    assert [(n.ref, n.text) for n in plan.not_evaluated] == [
        ("electrical", "The Electrical page is not evaluated."),
        ("plumbing", "The Plumbing page is not evaluated."),
    ]
    assert [n.producer_text for n in plan.not_evaluated] == [
        "Electrical systems were not reviewed for this quote.",
        "Plumbing was not reviewed for this quote.",
    ]


# A change to lead 008's values and the rule it reaches.
@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"roof_classification": "Class C", "p_f": 0.15}, ("no_action", "RF-2")),
        ({"roof_classification": "Class C", "p_f": 0.16}, ("requirement", "RF-3")),
        ({"roof_classification": "Class C", "p_f": 0.49}, ("requirement", "RF-3")),
        ({"roof_classification": "Class C", "p_f": 0.50}, ("requirement", "RF-4")),  # I18
        ({"siding_classification": "C"}, ("advisory", "SD-2")),
        ({"siding_classification": "D"}, ("no_action", "SD-3")),
        ({"siding_classification": "D", "p_f": 0.15}, ("no_action", "SD-3")),
        ({"siding_classification": "D", "p_f": 0.16}, ("requirement", "SD-4")),
        (
            {"siding_classification": "D", "p_f": 0.50},
            ("requirement", "SD-4"),
        ),  # the board's "<= .50"
        # I52: composition shingles replaced more than 20 years before 2026, at a fire probability above 0.15
        (
            {
                "roof_replacement_year": 2005,
                "p_f": 0.16,
                "roof_material": "Asphalt Fiberglass Composite",
            },
            ("advisory", "RF-5"),
        ),
        (
            {"roof_replacement_year": 2005, "p_f": 0.16, "roof_material": "Architecture Shingles"},
            ("advisory", "RF-5"),
        ),
        ({"replacement_cost": 1000000}, ("advisory", "RC-1")),
        ({"replacement_cost": 972222}, ("no_action", "RC-2")),  # 0.90 is at the estimate
        ({"replacement_cost": 972223}, ("advisory", "RC-1")),
        ({"replacement_cost": 795455}, ("no_action", "RC-2")),  # 1.10 is at the estimate
        ({"replacement_cost": 795454}, ("no_action", "RC-3")),  # above, within 150 percent
        ({"replacement_cost": 583334}, ("no_action", "RC-3")),  # just within 150 percent
        ({"replacement_cost": 583333}, ("requirement", "RC-4")),  # just over 150 percent
    ],
)
def test_a_page_takes_the_band_its_values_fall_in(
    changes: dict[str, JsonValue], rule: tuple[str, str]
) -> None:
    assert rule in outcomes(**changes)


def test_a_missing_class_leaves_the_roof_page_undecided_and_contributes_nothing() -> None:
    facts = lead_008()
    del facts["roof_classification"]

    plan = run(EvaluatePlaybookInput(facts=facts))

    assert [(u.graph, u.waits_on) for u in plan.undecided] == [("roof", ["roof_classification"])]
    assert not any(p.effect.rule.startswith("RF") for p in plan.effects)


def test_an_unknown_fire_probability_leaves_the_fire_simulation_page_undecided() -> None:
    facts = lead_008()
    del facts["p_f"]

    plan = run(EvaluatePlaybookInput(facts=facts))

    assert ("fire_simulation", ["p_f"]) in [(u.graph, u.waits_on) for u in plan.undecided]


def test_a_cut_page_that_applies_is_noted_and_one_that_does_not_is_not() -> None:
    plan = run(EvaluatePlaybookInput(facts=lead_008(pool_type="Inground", protection_class="9")))

    assert [n.ref for n in plan.not_evaluated] == [
        "electrical",
        "plumbing",
        "pools",
        "protection_class_9_10",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {
            "roof_replacement_year": 2006,
            "p_f": 0.16,
            "roof_material": "Architecture Shingles",
        },  # exactly 20 years is not more than 20
        {
            "roof_replacement_year": 2005,
            "p_f": 0.15,
            "roof_material": "Architecture Shingles",
        },  # the fire probability is not above 0.15
        {"roof_replacement_year": 2005, "p_f": 0.16, "roof_material": "Slate"},  # not composition
        {"roof_replacement_year": 2005, "p_f": 0.16, "roof_material": "Standing Seam Metal"},
    ],
)
def test_a_roof_that_is_not_an_old_composition_roof_takes_no_age_advisory(
    changes: dict[str, JsonValue],
) -> None:
    assert ("advisory", "RF-5") not in outcomes(**changes)


def test_the_age_advisory_waits_for_the_year_the_roof_was_replaced() -> None:
    plan = run(
        EvaluatePlaybookInput(
            facts=lead_008(roof_material="Architecture Shingles", roof_replacement_year=None)
        )
    )

    assert [(u.graph, u.waits_on) for u in plan.undecided] == [("roof", ["roof_age_years"])]
