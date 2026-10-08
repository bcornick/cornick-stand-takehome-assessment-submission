# ABOUTME: Tests that each value shown with the fire simulation choice carries the reading the legacy-underwriting branch of the page's graph gives it.
# ABOUTME: The graph is the real one; the facts stand for lead 003, whose simulation failed. A decline is explained by the values on its path through the page's graph.
import pytest

from tests.api.helpers import REGISTRY
from uwh.api.readings import choice_readings, decline_reason
from uwh.api.views import ChoiceReading
from uwh.rules.graphs import load_graphs
from uwh.rules.models import ActionPlan, DeclineEffect, OpenChoice, PlannedEffect, RuleTrace
from uwh.rules.registry import fact_fields, load_registry

SHOW = [
    "p_f",
    "road_access",
    "vegetation_clearance",
    "slope_angle_deg",
    "is_7a_compliant",
    "min_distance_to_neighbor_ft",
]
FAIL = OpenChoice(
    choice_id="I13.fire_fail",
    options=["decline", "legacy_underwriting"],
    prompt="The fire simulation failed.",
    show=SHOW,
)
NO_THRESHOLD = "Your call: the playbook sets no threshold"
MITIGATE = "Passes only if the client will mitigate"


@pytest.mark.parametrize(
    ("key", "value", "text", "problem"),
    [
        ("p_f", 0.79, "Fails: above 0.50", True),
        ("road_access", "Limited / Dead-end / No Turnaround", "Declines", True),
        ("road_access", "Multiple Access Points", "Passes", False),
        ("road_access", "Single Access Point", "Your call: the playbook does not settle it", False),
        ("vegetation_clearance", "Too Close", MITIGATE, False),
        ("vegetation_clearance", "Adequate", "Passes", False),
        ("vegetation_clearance", "Marginal", "Your call: the playbook does not settle it", False),
        ("slope_angle_deg", 12, NO_THRESHOLD, False),
        ("is_7a_compliant", False, MITIGATE, False),
        ("is_7a_compliant", True, "Passes", False),
        ("min_distance_to_neighbor_ft", 14, NO_THRESHOLD, False),
    ],
)
def test_a_shown_value_reads_as_the_legacy_branch_treats_it(
    key: str, value: object, text: str, problem: bool
) -> None:
    readings = choice_readings(FAIL, load_graphs(), {key: value})  # type: ignore[dict-item]
    assert readings[key] == ChoiceReading(text=text, problem=problem)


def test_a_missing_value_carries_no_reading_since_the_value_already_says_not_provided() -> None:
    readings = choice_readings(FAIL, load_graphs(), {"slope_angle_deg": 30})

    assert set(readings) == {"slope_angle_deg"}


def _declined(rule: str, board_path: list[str], choice_ids: list[str] | None = None) -> ActionPlan:
    trace = RuleTrace(board_path=board_path, choice_ids=choice_ids or [])
    effect = DeclineEffect(type="decline", rule=rule)
    return ActionPlan(
        effects=[PlannedEffect(effect=effect, trace=trace, committed=True)], proposed_decline=True
    )


SUPPORTS = "Post & pier supports living area (not just decking)"


@pytest.mark.parametrize(
    ("plan", "facts", "reason"),
    [
        (
            _declined("PP-1", ["07:ROOT", "07:LIVING", "07:D1"]),
            {"foundation_type": "Piers", "post_pier_supports_living_area": True},
            f"Foundation Type is Piers and {SUPPORTS} is Yes,"
            " so the post and pier page declines it (PP-1)",
        ),
        (
            _declined("PP-2", ["07:ROOT", "07:DECK", "07:PRE2000", "07:D1"]),
            {
                "foundation_type": "Stilts",
                "post_pier_supports_living_area": False,
                "year_built": 1985,
            },
            f"Foundation Type is Stilts, {SUPPORTS} is No and Year Built is 1985,"
            " so the post and pier page declines it (PP-2)",
        ),
        (
            _declined("FS-1", ["04:ROOT", "04:FAIL", "04:D_FAIL"], ["I13.fire_fail"]),
            {"p_f": 0.79},
            "P(F) - Probability of Failure (fire simulation) is 0.79 and you chose decline"
            " (“too steep to defend”), so the fire simulation page declines it (FS-1)",
        ),
        (
            ActionPlan(underwriter_decline="the roof is beyond repair", proposed_decline=True),
            {},
            "the roof is beyond repair",
        ),
    ],
    ids=["living area on piers", "deck on stilts before 2000", "after a choice", "underwriter"],
)
def test_a_decline_is_explained_by_the_values_that_led_to_it(
    plan: ActionPlan, facts: dict[str, object], reason: str
) -> None:
    fields = fact_fields(load_registry(str(REGISTRY)))

    reasons = {"I13.fire_fail": "too steep to defend"}

    assert decline_reason(plan, load_graphs(), facts, fields, reasons) == reason  # type: ignore[arg-type]
