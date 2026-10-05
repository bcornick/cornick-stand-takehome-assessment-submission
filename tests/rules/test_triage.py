# ABOUTME: Tests field triage of 9.2 on lead 008's real fields: which missing fields are asked, deferred, fetched, derived, blocked or not required, and what a missing controlling field or a conflict changes.
# ABOUTME: Each row names a field and the triage it must get; the registry is Stand's file and the lead is the seed-42 queue's lead 008 as captured in the provider fixture.
import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from uwh.rules.derivations import derived_from
from uwh.rules.models import Requirement, Resolution, ValueStatus
from uwh.rules.registry import Registry, load_registry
from uwh.rules.triage import triage_fields
from uwh.rules.validators import conflict_validators

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "src" / "uwh" / "providers" / "data" / "world-42.json"


@pytest.fixture(scope="module")
def registry() -> Registry:
    return load_registry(str(ROOT / "docs" / "brief" / "field_registry.json"))


def lead_008_facts() -> dict[str, JsonValue]:
    fields = json.loads(WORLD.read_text(encoding="utf-8"))["leads"]["LEAD-00000042-008"]["fields"]
    return {name: value for name, value in fields.items() if value is not None}


# Every null field of lead 008 and what happens to it. Exactly two are asked.
LEAD_008_NULLS = {
    "electrical_panel_brand": Resolution.ask,
    "property_purchase_date": Resolution.ask,
    "occupation": Resolution.defer,  # bind only
    "opening_protection": Resolution.not_required,  # never asked: no page uses it
    "siding_classification": Resolution.derive,
    "replacement_cost": Resolution.fetch,
    "slope_angle_deg": Resolution.fetch,
    "min_distance_to_neighbor_ft": Resolution.fetch,
    "deck_height_ft": Resolution.not_required,  # foundation is Slab
    "post_pier_supports_living_area": Resolution.not_required,
    "trust_name": Resolution.not_required,  # not held in a trust
    "above_ground_pool_ladder": Resolution.not_required,  # no pool
    "water_heater_age_years": Resolution.not_required,  # tankless
    "water_heater_location": Resolution.not_required,
    "fire_dept_response_time": Resolution.not_required,  # protection class 5
    "alternative_water_source": Resolution.not_required,
    "interior_sprinklers": Resolution.not_required,
    "physical_barriers": Resolution.not_required,
}


def test_lead_008_asks_exactly_its_two_producer_fields(registry: Registry) -> None:
    triage = triage_fields(registry, lead_008_facts(), set(), derived_from())

    assert {name: triage[name].resolution for name in LEAD_008_NULLS} == LEAD_008_NULLS
    assert sorted(n for n, t in triage.items() if t.resolution == Resolution.ask) == [
        "electrical_panel_brand",
        "property_purchase_date",
    ]
    assert triage["street_address"].resolution == Resolution.none


def test_a_missing_system_owned_controlling_field_blocks_its_dependents(
    registry: Registry,
) -> None:
    facts = lead_008_facts()
    del facts["protection_class"]

    triage = triage_fields(registry, facts, set(), derived_from())

    assert triage["fire_dept_response_time"].resolution == Resolution.blocked
    assert triage["fire_dept_response_time"].depends_on == ["protection_class"]
    assert triage["protection_class"].resolution == Resolution.fetch


def test_a_dependent_of_a_missing_producer_field_is_a_follow_on_question(
    registry: Registry,
) -> None:
    facts = lead_008_facts()
    del facts["pool_type"]
    del facts["pool_security"]

    triage = triage_fields(registry, facts, set(), derived_from())

    assert triage["pool_type"].resolution == Resolution.ask
    assert triage["pool_security"].requirement == Requirement.conditional_unknown
    assert triage["pool_security"].resolution == Resolution.ask_follow_on


def test_a_field_in_an_open_conflict_is_verified_not_asked(registry: Registry) -> None:
    triage = triage_fields(registry, lead_008_facts(), {"roof_replacement_year"}, derived_from())

    assert triage["roof_replacement_year"].value_status == ValueStatus.conflicting
    assert triage["roof_replacement_year"].resolution == Resolution.verify


def test_a_missing_field_beside_a_conflict_over_a_present_value_is_asked(
    registry: Registry,
) -> None:
    facts = {**lead_008_facts(), "number_of_residents": 0}
    del facts["dwelling_use_type"]
    (conflict,) = [
        c
        for validate in conflict_validators()
        for c in validate({"number_of_residents": 0, "dwelling_type": "Owner Occupied Condo"})
    ]

    triage = triage_fields(registry, facts, set(conflict.fields), derived_from())

    assert triage["number_of_residents"].resolution == Resolution.verify
    assert triage["dwelling_use_type"].value_status == ValueStatus.missing
    assert triage["dwelling_use_type"].resolution == Resolution.ask


# 9.2: is_gated_community is inactive when pool_type is known and not Inground or pool_security is
# Fenced, active for an inground pool with a known security that is not Fenced, unknown otherwise.
@pytest.mark.parametrize(
    ("pool", "expected"),
    [
        ({"pool_type": "None"}, (Requirement.conditional_inactive, Resolution.not_required)),
        (
            {"pool_type": "Above Ground"},
            (Requirement.conditional_inactive, Resolution.not_required),
        ),
        (
            {"pool_type": "Inground", "pool_security": "Fenced"},
            (Requirement.conditional_inactive, Resolution.not_required),
        ),
        ({"pool_security": "Fenced"}, (Requirement.conditional_inactive, Resolution.not_required)),
        (
            {"pool_type": "Inground", "pool_security": "Unfenced"},
            (Requirement.conditional_active, Resolution.ask),
        ),
        (
            {"pool_type": "Inground", "pool_security": "None"},
            (Requirement.conditional_active, Resolution.ask),
        ),
        ({"pool_type": "Inground"}, (Requirement.conditional_unknown, Resolution.ask_follow_on)),
        (
            {"pool_security": "Unfenced"},
            (Requirement.conditional_unknown, Resolution.ask_follow_on),
        ),
        ({}, (Requirement.conditional_unknown, Resolution.ask_follow_on)),
    ],
)
def test_a_gated_community_is_asked_by_the_three_valued_pool_rule(
    registry: Registry, pool: dict[str, JsonValue], expected: tuple[Requirement, Resolution]
) -> None:
    facts = lead_008_facts()
    for name in ("is_gated_community", "pool_type", "pool_security"):
        facts.pop(name, None)

    triage = triage_fields(registry, {**facts, **pool}, set(), derived_from())["is_gated_community"]

    assert (triage.requirement, triage.resolution) == expected
