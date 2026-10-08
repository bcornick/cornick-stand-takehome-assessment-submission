# ABOUTME: Tests that each value shown with the fire simulation choice carries the reading the legacy-underwriting branch of the page's graph gives it.
# ABOUTME: The graph is the real one; the facts stand for lead 003, whose simulation failed.
import pytest

from uwh.api.readings import choice_readings
from uwh.api.views import ChoiceReading
from uwh.rules.graphs import load_graphs
from uwh.rules.models import OpenChoice

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
        ("p_f", None, "Not provided", False),
        ("road_access", "Limited / Dead-end / No Turnaround", "Declines", True),
        ("road_access", "Multiple Access Points", "Passes", False),
        ("road_access", "Single Access Point", "Your call: the playbook does not settle it", False),
        ("road_access", None, "Not provided", False),
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
    facts = {} if value is None else {key: value}
    readings = choice_readings(FAIL, load_graphs(), facts)  # type: ignore[arg-type]
    assert readings[key] == ChoiceReading(text=text, problem=problem)
