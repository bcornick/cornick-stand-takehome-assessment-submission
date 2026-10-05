# ABOUTME: The triage_fields skill (9.2): a lead's usable facts and open conflicts against the registry give each field its value status, requirement and resolution.
# ABOUTME: Deterministic; the rules are in `uwh.rules.triage`.
from pydantic import JsonValue

from uwh.rules.derivations import derived_from
from uwh.rules.models import FieldTriage, StrictModel
from uwh.rules.registry import Registry
from uwh.rules.triage import triage_fields


class TriageFieldsInput(StrictModel):
    registry: Registry
    facts: dict[str, JsonValue]  # the lead's usable facts; a missing key is a missing field
    conflicting_fields: list[str]  # the fields of the open conflicts


class TriageFieldsOutput(StrictModel):
    fields: dict[str, FieldTriage]  # registry field -> its triage, in registry order


def run(input: TriageFieldsInput) -> TriageFieldsOutput:
    return TriageFieldsOutput(
        fields=triage_fields(input.registry, input.facts, input.conflicting_fields, derived_from())
    )
