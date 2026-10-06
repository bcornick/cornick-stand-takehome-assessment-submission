# ABOUTME: Tests the evaluate_playbook skill on lead 008's facts: the outcome of each page it reaches, the pages it does not reach and the not-evaluated notes; the outcomes on the values around each band are in the skill's cases.
# ABOUTME: Lead 008's values are the captured seed-42 lead plus the fetched and derived facts its first pass adds.

from tests.skills.helpers import lead_008
from uwh.skills.evaluate_playbook.skill import EvaluatePlaybookInput, run


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
