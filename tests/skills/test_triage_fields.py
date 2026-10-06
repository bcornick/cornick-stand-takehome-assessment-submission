# ABOUTME: Tests the triage_fields skill on the real values of seed-42 lead 008 for the three-valued pool condition of section 9.2 that decides whether is_gated_community is asked.
# ABOUTME: Each row removes is_gated_community and sets the two pool facts; a wrong reading of an unknown pool fails the row that depends on it.
import pytest

from tests.api.helpers import REGISTRY
from tests.skills.helpers import lead_008
from uwh.rules.models import Requirement, Resolution
from uwh.rules.registry import load_registry
from uwh.skills.triage_fields.skill import TriageFieldsInput, run

INACTIVE = (Requirement.conditional_inactive, Resolution.not_required)
ACTIVE = (Requirement.conditional_active, Resolution.ask)
UNKNOWN = (Requirement.conditional_unknown, Resolution.ask_follow_on)


@pytest.mark.parametrize(
    ("pool_type", "pool_security", "expected"),
    [
        ("None", None, INACTIVE),
        ("Above Ground", None, INACTIVE),
        ("Inground", "Fenced", INACTIVE),
        (None, "Fenced", INACTIVE),
        ("Inground", "Unfenced", ACTIVE),
        ("Inground", "None", ACTIVE),
        ("Inground", None, UNKNOWN),
        (None, "Unfenced", UNKNOWN),
        (None, None, UNKNOWN),
    ],
)
def test_is_gated_community_follows_the_pool_condition(
    pool_type: str | None, pool_security: str | None, expected: tuple[Requirement, Resolution]
) -> None:
    facts = lead_008(is_gated_community=None, pool_type=pool_type, pool_security=pool_security)

    triage = run(
        TriageFieldsInput(registry=load_registry(str(REGISTRY)), facts=facts, conflicting_fields=[])
    )

    found = triage.fields["is_gated_community"]
    assert (found.requirement, found.resolution) == expected
