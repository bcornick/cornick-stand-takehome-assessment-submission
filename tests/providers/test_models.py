# ABOUTME: Tests the section 9.4 provider result: status, value, source, fetched_at, is_stub, and the inputs a blocked result names.
# ABOUTME: The four statuses are written out here; the model forbids unknown fields and round-trips through JSON.
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from uwh.providers.models import ProviderResult

FOUND: dict[str, Any] = {
    "status": "found",
    "value": "4",
    "source": "fixture",
    "fetched_at": "2026-06-29T08:00:00+00:00",
    "is_stub": False,
}
BLOCKED: dict[str, Any] = {
    "status": "blocked",
    "value": None,
    "source": "fixture",
    "fetched_at": "2026-06-29T08:00:00+00:00",
    "is_stub": False,
    "missing_inputs": ["street_address", "zip"],
}


def test_the_status_is_one_of_four() -> None:
    assert list(get_args(ProviderResult.model_fields["status"].annotation)) == [
        "found",
        "not_found",
        "blocked",
        "unavailable",
    ]


def test_the_result_holds_the_section_9_4_fields() -> None:
    assert list(ProviderResult.model_fields) == [
        "status",
        "value",
        "source",
        "fetched_at",
        "is_stub",
        "missing_inputs",
    ]


@pytest.mark.parametrize("status", ["found", "not_found", "unavailable"])
def test_a_result_without_missing_inputs_is_valid_for_the_other_statuses(status: str) -> None:
    result = ProviderResult.model_validate({**FOUND, "status": status})
    assert result.missing_inputs == []


def test_a_blocked_result_names_the_missing_input_fields() -> None:
    result = ProviderResult.model_validate(BLOCKED)
    assert result.missing_inputs == ["street_address", "zip"]


def test_a_blocked_result_with_no_missing_input_is_refused() -> None:
    with pytest.raises(ValidationError):
        ProviderResult.model_validate({**BLOCKED, "missing_inputs": []})


def test_an_unblocked_result_that_names_missing_inputs_is_refused() -> None:
    with pytest.raises(ValidationError):
        ProviderResult.model_validate({**FOUND, "missing_inputs": ["zip"]})


def test_an_unknown_status_is_refused() -> None:
    with pytest.raises(ValidationError):
        ProviderResult.model_validate({**FOUND, "status": "timeout"})


def test_a_stub_is_marked() -> None:
    assert ProviderResult.model_validate({**FOUND, "is_stub": True}).is_stub is True


@pytest.mark.parametrize("payload", [FOUND, BLOCKED])
def test_the_result_round_trips_through_json(payload: dict[str, Any]) -> None:
    result = ProviderResult.model_validate(payload)
    assert ProviderResult.model_validate_json(result.model_dump_json()) == result


def test_the_result_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderResult.model_validate({**FOUND, "confidence": 0.9})
