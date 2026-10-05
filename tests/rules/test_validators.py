# ABOUTME: Tests the conflict validators of 9.5: each fires on values that break its check and stays quiet on the nearest values that do not.
# ABOUTME: Each row is a validator id with one set of values that fires it and one that does not; the confirmation question names the reported values.
import pytest
from pydantic import JsonValue

from uwh.rules.validators import conflict_validators

PRIMARY: dict[str, JsonValue] = {
    "dwelling_use_type": "Primary",
    "dwelling_type": "Owner Occupied Single Family Residence",
}

# validator id -> (values that fire it, values that do not)
CASES: dict[str, tuple[dict[str, JsonValue], dict[str, JsonValue]]] = {
    "roof_year_in_future": ({"roof_replacement_year": 2027}, {"roof_replacement_year": 2026}),
    "roof_year_before_year_built": (
        {"roof_replacement_year": 1990, "year_built": 1993},
        {"roof_replacement_year": 1993, "year_built": 1993},
    ),
    "effective_date_in_past": ({"effective_date": "2026-06-28"}, {"effective_date": "2026-06-29"}),
    "panel_size_below_60": (
        {"electrical_panel_size_amps": 50},
        {"electrical_panel_size_amps": 60},
    ),
    "no_residents_in_primary_home": (
        {**PRIMARY, "number_of_residents": 0},
        {
            "dwelling_use_type": "Secondary",
            "dwelling_type": "Secondary Residence",
            "number_of_residents": 0,
        },
    ),
    "acreage_zero": ({"acreage": 0}, {"acreage": 0.32}),
    "months_unoccupied_in_primary_home": (
        {**PRIMARY, "months_unoccupied": 1},
        {**PRIMARY, "months_unoccupied": 0},
    ),
    "primary_use_with_rental": (
        {"dwelling_use_type": "Primary", "is_rental": "Long-Term Rentals"},
        {"dwelling_use_type": "Primary", "is_rental": "No"},
    ),
    "owner_occupied_with_other_use": (
        {"dwelling_type": "Owner Occupied Multi Family Residence", "dwelling_use_type": "Seasonal"},
        {"dwelling_type": "Owner Occupied Multi Family Residence", "dwelling_use_type": "Primary"},
    ),
    "tenant_use_without_rental": (
        {"dwelling_use_type": "Tenant", "is_rental": "No"},
        {"dwelling_use_type": "Tenant", "is_rental": "Long-Term Rentals"},
    ),
    "tankless_with_tank_fields": (
        {"water_heater_type": "Tankless", "water_heater_age_years": 6},
        {"water_heater_type": "Tankless"},
    ),
}


def fired(values: dict[str, JsonValue]) -> set[str]:
    return {c.validator for validate in conflict_validators() for c in validate(values)}


@pytest.mark.parametrize("validator_id", CASES)
def test_a_validator_fires_on_its_values_and_not_on_the_nearest_values_that_pass(
    validator_id: str,
) -> None:
    breaking, passing = CASES[validator_id]

    assert validator_id in fired(breaking)
    assert validator_id not in fired(passing)


def test_the_question_reports_the_values_it_asks_about() -> None:
    (conflict,) = [
        c
        for validate in conflict_validators()
        for c in validate({"roof_replacement_year": 1990, "year_built": 1993})
    ]

    assert conflict.question == (
        "The home is listed as built in 1993 and the roof as replaced in 1990."
        " Can you confirm both years?"
    )
    assert conflict.values == {"roof_replacement_year": 1990, "year_built": 1993}


def test_a_conflict_covers_only_the_fields_that_are_present() -> None:
    (conflict,) = [
        c
        for validate in conflict_validators()
        for c in validate({"number_of_residents": 0, "dwelling_type": PRIMARY["dwelling_type"]})
    ]

    assert conflict.fields == ("number_of_residents", "dwelling_type")
    assert "dwelling_use_type" not in conflict.values
    assert conflict.question == (
        "The number of people living in the home is listed as 0. Can you confirm that number?"
    )
