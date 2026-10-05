# ABOUTME: The conflict validators of 9.5: each tests present values for an inconsistency and returns the fields involved with the neutral confirmation question from `wording.yaml`.
# ABOUTME: The `kyc_score` range check goes to the underwriter, not the producer, and is not built here; every other validator of the table is.
from collections.abc import Callable, Mapping
from datetime import date

from pydantic import JsonValue

from uwh.rules.data_files import read_yaml
from uwh.runtime.facts import Conflict, Validator
from uwh.skills.vertical import REFERENCE_MORNING

Values = Mapping[str, JsonValue]

_OWNER_OCCUPIED = "Owner Occupied"
_TENANT_USES = ("Tenant", "Mixed (Secondary/Seasonal & Tenant)")


def _number(values: Values, field: str) -> float | None:
    value = values.get(field)
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _is_primary_home(values: Values) -> bool:
    """A primary home: the use type says so, the dwelling is owner occupied, or neither field is known."""
    use, dwelling = values.get("dwelling_use_type"), values.get("dwelling_type")
    return (
        use == "Primary"
        or (isinstance(dwelling, str) and dwelling.startswith(_OWNER_OCCUPIED))
        or (use is None and dwelling is None)
    )


def _before_reference_date(value: JsonValue) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value) < REFERENCE_MORNING.date()
    except ValueError:
        return False  # an unreadable date is not a value the check can compare


def _roof_before_build(values: Values) -> bool:
    roof, built = _number(values, "roof_replacement_year"), _number(values, "year_built")
    return roof is not None and built is not None and roof < built


def _roof_in_future(values: Values) -> bool:
    roof = _number(values, "roof_replacement_year")
    return roof is not None and roof > REFERENCE_MORNING.year


def _below(field: str, bound: float) -> Callable[[Values], bool]:
    return lambda values: (n := _number(values, field)) is not None and n < bound


def _equals_zero(field: str) -> Callable[[Values], bool]:
    return lambda values: _number(values, field) == 0


def _unoccupied_in_primary_home(values: Values) -> bool:
    months = _number(values, "months_unoccupied")
    return months is not None and months >= 1 and _is_primary_home(values)


def _no_residents_in_primary_home(values: Values) -> bool:
    return _number(values, "number_of_residents") == 0 and _is_primary_home(values)


def _owner_occupied_with_other_use(values: Values) -> bool:
    dwelling, use = values.get("dwelling_type"), values.get("dwelling_use_type")
    return (
        isinstance(dwelling, str)
        and dwelling.startswith(_OWNER_OCCUPIED)
        and use in ("Secondary", "Seasonal", *_TENANT_USES)
    )


def _tankless_with_tank_fields(values: Values) -> bool:
    return values.get("water_heater_type") == "Tankless" and any(
        field in values for field in ("water_heater_age_years", "water_heater_location")
    )


# Validator id -> the test on the lead's values. The ids and the fields each covers are the keys of
# `confirmations` in `wording.yaml`.
_TESTS: dict[str, Callable[[Values], bool]] = {
    "roof_year_in_future": _roof_in_future,
    "roof_year_before_year_built": _roof_before_build,
    "effective_date_in_past": lambda values: _before_reference_date(values.get("effective_date")),
    "panel_size_below_60": _below("electrical_panel_size_amps", 60),
    "no_residents_in_primary_home": _no_residents_in_primary_home,
    "acreage_zero": _equals_zero("acreage"),
    "months_unoccupied_in_primary_home": _unoccupied_in_primary_home,
    "primary_use_with_rental": lambda values: (
        values.get("dwelling_use_type") == "Primary" and values.get("is_rental") not in (None, "No")
    ),
    "owner_occupied_with_other_use": _owner_occupied_with_other_use,
    "tenant_use_without_rental": lambda values: (
        values.get("dwelling_use_type") in _TENANT_USES and values.get("is_rental") == "No"
    ),
    "tankless_with_tank_fields": _tankless_with_tank_fields,
}


def _validator(validator_id: str, fields: list[str], question: str) -> Validator:
    def validate(values: Values) -> list[Conflict]:
        if not _TESTS[validator_id](values):
            return []
        reported = {field: values[field] for field in fields if field in values}
        return [Conflict(validator_id, tuple(reported), reported, question.format_map(reported))]

    return validate


def conflict_validators() -> tuple[Validator, ...]:
    """One validator per confirmation of `wording.yaml`."""
    confirmations = read_yaml("wording.yaml")["confirmations"]
    return tuple(
        _validator(validator_id, spec["fields"], spec["question"])
        for validator_id, spec in confirmations.items()
    )
