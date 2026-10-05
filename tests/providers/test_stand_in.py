# ABOUTME: Tests the stand-in providers (9.4): a lookup whose inputs are missing is blocked before the fixture is read, a lead the fixture lacks or whose submitted fields changed is unavailable, and an entry answers as captured.
# ABOUTME: The world is built in the test, so each case fixes the entry, the fingerprint and the facts it depends on.
from typing import Any

import pytest

from uwh.providers.stand_in import StandInProviders

ADDRESS = {"street_address": "1 Main St", "city": "Ukiah", "state": "CA", "zip": "95482"}
WORLD: dict[str, Any] = {
    "leads": {
        "L-1": {
            "fingerprint": "captured",
            "provider_values": {
                "protection_class": {"status": "not_found", "value": None},
                "replacement_cost": {"status": "found", "value": 500000},
            },
        }
    }
}


@pytest.mark.parametrize(
    ("field", "lead_id", "fingerprint", "facts", "expected"),
    [
        ("replacement_cost", "L-1", "captured", ADDRESS, ("found", 500000, [])),
        ("protection_class", "L-1", "captured", ADDRESS, ("not_found", None, [])),
        # The input check runs first: the entry says not_found, the lookup is blocked.
        ("protection_class", "L-1", "captured", {}, ("blocked", None, ADDRESS.keys())),
        ("replacement_cost", "L-1", "changed", ADDRESS, ("unavailable", None, [])),
        ("replacement_cost", "L-2", "captured", ADDRESS, ("unavailable", None, [])),
        # Blocked outranks unavailable too.
        ("replacement_cost", "L-2", "captured", {}, ("blocked", None, ADDRESS.keys())),
    ],
)
def test_a_lookup_answers_from_the_entry_unless_its_inputs_are_missing_or_the_entry_does_not_hold(
    field: str, lead_id: str, fingerprint: str, facts: dict[str, Any], expected: tuple[Any, ...]
) -> None:
    result = StandInProviders(WORLD).lookup(
        field, lead_id, fingerprint, facts, "2026-06-29T08:00:00Z"
    )

    assert (result.status, result.value, result.missing_inputs) == (
        expected[0],
        expected[1],
        list(expected[2]),
    )
