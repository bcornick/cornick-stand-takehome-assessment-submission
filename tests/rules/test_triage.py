# ABOUTME: Tests field triage of 9.2 on lead 008's real fields: what a missing controlling field blocks, which dependents of a missing producer field become follow-on questions, and how an open conflict changes what is asked.
# ABOUTME: Each test removes or changes facts of lead 008 as captured in the provider fixture and names the triage a field must get; the registry is Stand's file.
import pytest

from tests.api.helpers import REGISTRY
from tests.skills.helpers import lead_008
from uwh.rules.derivations import derived_from
from uwh.rules.models import Requirement, Resolution, ValueStatus
from uwh.rules.registry import Registry, load_registry
from uwh.rules.triage import triage_fields
from uwh.rules.validators import conflict_validators


@pytest.fixture(scope="module")
def registry() -> Registry:
    return load_registry(str(REGISTRY))


def test_a_missing_system_owned_controlling_field_blocks_its_dependents(
    registry: Registry,
) -> None:
    triage = triage_fields(registry, lead_008(protection_class=None), set(), derived_from())

    assert triage["fire_dept_response_time"].resolution == Resolution.blocked
    assert triage["fire_dept_response_time"].depends_on == ["protection_class"]
    assert triage["protection_class"].resolution == Resolution.fetch


def test_a_dependent_of_a_missing_producer_field_is_a_follow_on_question(
    registry: Registry,
) -> None:
    facts = lead_008(pool_type=None, pool_security=None)

    triage = triage_fields(registry, facts, set(), derived_from())

    assert triage["pool_type"].resolution == Resolution.ask
    assert triage["pool_security"].requirement == Requirement.conditional_unknown
    assert triage["pool_security"].resolution == Resolution.ask_follow_on


def test_a_field_in_an_open_conflict_is_verified_not_asked(registry: Registry) -> None:
    triage = triage_fields(registry, lead_008(), {"roof_replacement_year"}, derived_from())

    assert triage["roof_replacement_year"].value_status == ValueStatus.conflicting
    assert triage["roof_replacement_year"].resolution == Resolution.verify


def test_a_missing_field_beside_a_conflict_over_a_present_value_is_asked(
    registry: Registry,
) -> None:
    facts = lead_008(number_of_residents=0, dwelling_use_type=None)
    (conflict,) = [
        c
        for validate in conflict_validators()
        for c in validate({"number_of_residents": 0, "dwelling_type": "Owner Occupied Condo"})
    ]

    triage = triage_fields(registry, facts, set(conflict.fields), derived_from())

    assert triage["number_of_residents"].resolution == Resolution.verify
    assert triage["dwelling_use_type"].value_status == ValueStatus.missing
    assert triage["dwelling_use_type"].resolution == Resolution.ask
