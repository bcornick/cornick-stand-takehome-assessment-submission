# ABOUTME: The section 9.4 provider result: status, value, source, fetched_at, is_stub, and the inputs a blocked result names.
# ABOUTME: A blocked result names at least one missing input field; every other status names none.
from typing import Self

from pydantic import JsonValue, model_validator

from uwh.rules.models import StrictModel
from uwh.runtime.event_types import ProviderStatus


class ProviderResult(StrictModel):
    status: ProviderStatus  # 9.4
    value: JsonValue  # None unless found
    source: str  # the provider the value stands in for, or the stub marker's origin
    fetched_at: str  # ISO timestamp
    is_stub: bool  # True when the fixture had no entry and a seeded synthetic value answered
    missing_inputs: list[str] = []  # 9.4: "A blocked result names the missing input fields."

    @model_validator(mode="after")
    def blocked_names_its_missing_inputs(self) -> Self:
        if (self.status == "blocked") != bool(self.missing_inputs):
            raise ValueError("missing_inputs is non-empty exactly when the status is blocked")
        return self
