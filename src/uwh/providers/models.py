# ABOUTME: The section 9.4 provider result: status, value, source, fetched_at, is_stub, and the inputs a blocked result names.
# ABOUTME: A blocked result names at least one missing input field; every other status names none. Only a found result has a value.
from typing import Literal, Self

from pydantic import JsonValue, model_validator

from uwh.rules.models import StrictModel

ProviderStatus = Literal["found", "not_found", "blocked", "unavailable"]


class ProviderResult(StrictModel):
    status: ProviderStatus  # 9.4
    value: JsonValue  # None unless the status is found, and never None when it is
    source: str  # the provider the value stands in for, or the stub marker's origin
    fetched_at: str  # ISO timestamp
    is_stub: bool  # True when the fixture had no entry and a seeded synthetic value answered
    missing_inputs: list[str] = []  # 9.4: "A blocked result names the missing input fields."

    @model_validator(mode="after")
    def blocked_names_its_missing_inputs(self) -> Self:
        if (self.status == "blocked") != bool(self.missing_inputs):
            raise ValueError("missing_inputs is non-empty exactly when the status is blocked")
        return self

    @model_validator(mode="after")
    def only_a_found_result_has_a_value(self) -> Self:
        if (self.status == "found") != (self.value is not None):
            raise ValueError("value is present exactly when the status is found")
        return self
