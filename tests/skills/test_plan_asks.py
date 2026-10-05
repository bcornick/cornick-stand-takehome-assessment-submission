# ABOUTME: Tests the class of the request plan_asks chooses: a request of confirmations only takes the confirmation-only class, and one with a field request is a routine request.
# ABOUTME: The class is read through the module's constant so the test follows a change of that choice and fails if the skill stops using it.
import pytest

from tests.api.helpers import REGISTRY
from uwh.rules.models import FieldTriage, Requirement, Resolution, ValueStatus
from uwh.rules.registry import load_registry
from uwh.runtime.event_types import ConflictOpened
from uwh.skills.plan_asks import skill
from uwh.skills.plan_asks.skill import PlanAsksInput

CONFLICT = ConflictOpened(
    validator="no_residents_in_primary_home",
    fields=["no_residents_in_primary_home"],
    values={"no_residents_in_primary_home": 0},
    question="The number of people living in the home is listed as 0. Can you confirm that number?",
)
COVERAGE_A_MISSING = FieldTriage(
    value_status=ValueStatus.missing,
    requirement=Requirement.required,
    resolution=Resolution.ask,
    depends_on=[],
)


@pytest.mark.parametrize(
    ("triage", "expected"),
    [({}, "sensitive_request"), ({"coverage_a": COVERAGE_A_MISSING}, "routine_request")],
    ids=["confirmations only", "a field request too"],
)
def test_a_request_of_confirmations_only_takes_the_confirmation_only_class(
    monkeypatch: pytest.MonkeyPatch, triage: dict[str, FieldTriage], expected: str
) -> None:
    monkeypatch.setattr(skill, "CONFIRMATION_ONLY_CLASS", "sensitive_request")

    planned = skill.run(
        PlanAsksInput(registry=load_registry(str(REGISTRY)), triage=triage, conflicts=[CONFLICT])
    )

    assert planned.message_class == expected
