# ABOUTME: Tests the resolve_data skill (9.3): a found lookup is a fetched fact, a protection class the provider does not find is assumed to be 9, a blocked lookup yields nothing, and what the build does not handle raises.
# ABOUTME: Provider results are built in the test; each row fixes the status and the field.
import pytest

from uwh.providers.models import ProviderResult
from uwh.rules.models import NotBuilt
from uwh.skills.resolve_data.skill import ResolveDataInput, run


def result(status: str, value: object = None, missing: list[str] | None = None) -> ProviderResult:
    return ProviderResult.model_validate(
        {
            "status": status,
            "value": value,
            "source": "Verisk LOCATION PPC",
            "fetched_at": "2026-06-29T08:00:00Z",
            "missing_inputs": missing or [],
        }
    )


def resolved(field: str, looked_up: ProviderResult) -> list[tuple[str, object, str]]:
    output = run(ResolveDataInput(provider_results={field: looked_up}))
    return [(fact.key, fact.value, fact.source) for fact in output.facts]


@pytest.mark.parametrize(
    ("field", "looked_up", "expected"),
    [
        ("replacement_cost", result("found", 500000), [("replacement_cost", 500000, "fetched")]),
        ("protection_class", result("not_found"), [("protection_class", "9", "assumed")]),
        ("protection_class", result("blocked", missing=["zip"]), []),
    ],
)
def test_a_lookup_becomes_a_fetched_fact_a_stated_default_or_nothing(
    field: str, looked_up: ProviderResult, expected: list[tuple[str, object, str]]
) -> None:
    assert resolved(field, looked_up) == expected


def test_a_field_with_no_default_that_is_not_found_stops_the_lead() -> None:
    with pytest.raises(NotBuilt, match="did not find replacement_cost"):
        resolved("replacement_cost", result("not_found"))


def test_an_unavailable_provider_raises() -> None:
    with pytest.raises(ValueError, match="unavailable for protection_class"):
        resolved("protection_class", result("unavailable"))
