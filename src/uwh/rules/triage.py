# ABOUTME: Field triage of 9.2: the join of a lead's usable facts and the registry gives each field a value status, a requirement, a resolution and the fields it depends on.
# ABOUTME: Conditions are the registry's prose, parsed into three results (active, inactive, unknown); the three conditional fields with no prose follow the 9.2 table.
import re
from collections.abc import Collection, Mapping

from pydantic import JsonValue

from uwh.rules.models import FieldTriage, Requirement, Resolution, ValueStatus
from uwh.rules.registry import Registry, RegistryField

_CONDITION = re.compile(r"^(\w+) (=|!=|in) (.+)$")


def _text(value: JsonValue) -> str:
    """A fact as the registry's condition prose writes it: a toggle is `true` or `false`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parsed_condition(prose: str, facts: Mapping[str, JsonValue]) -> tuple[bool | None, list[str]]:
    """Whether the registry's condition holds (None when its controlling field is unknown), and that field."""
    match = _CONDITION.match(prose)
    if match is None:
        raise ValueError(f"the registry condition {prose!r} has no known form")
    field, operator, operand = match.groups()
    if field not in facts:
        return None, [field]
    value = _text(facts[field])
    if operator == "in":
        holds = value in [part.strip() for part in operand.strip("()").split(",")]
    else:
        holds = (value == operand) == (operator == "=")
    return holds, [field]


def _gated_community_condition(facts: Mapping[str, JsonValue]) -> tuple[bool | None, list[str]]:
    """The 9.2 table: inactive off an inground pool or behind a fence, active for an unfenced inground
    pool, unknown otherwise."""
    pool, security = facts.get("pool_type"), facts.get("pool_security")
    if (pool is not None and pool != "Inground") or security == "Fenced":
        return False, ["pool_type", "pool_security"]
    if pool == "Inground" and security is not None:
        return True, ["pool_type", "pool_security"]
    return None, ["pool_type", "pool_security"]


def _requirement(
    field: RegistryField, facts: Mapping[str, JsonValue]
) -> tuple[Requirement, list[str]]:
    if field.required == "always":
        return Requirement.required, []
    if field.required == "bind_only":
        return Requirement.bind_only, []
    if field.required == "no" or field.name == "opening_protection":  # no page uses it: never asked
        return Requirement.optional, []
    if field.name == "is_gated_community":
        holds, depends_on = _gated_community_condition(facts)
    elif (
        field.required_when is None
    ):  # listed_for_sale, and the fields fetched from Stand's systems
        return Requirement.conditional_active, []
    else:
        holds, depends_on = _parsed_condition(field.required_when, facts)
    if holds is None:
        return Requirement.conditional_unknown, depends_on
    return (
        Requirement.conditional_active if holds else Requirement.conditional_inactive,
        depends_on,
    )


def _missing_resolution(
    field: RegistryField,
    requirement: Requirement,
    depends_on: list[str],
    registry: Registry,
    derivations: Mapping[str, str],
) -> tuple[Resolution, list[str]]:
    if requirement == Requirement.bind_only:
        return Resolution.defer, []
    if requirement in (Requirement.optional, Requirement.conditional_inactive):
        return Resolution.not_required, depends_on
    if not field.producer_editable:
        if field.name in derivations:
            return Resolution.derive, [derivations[field.name]]
        return Resolution.fetch, []
    if requirement == Requirement.conditional_unknown:
        if all(registry[name].producer_editable for name in depends_on):
            return Resolution.ask_follow_on, depends_on
        return Resolution.blocked, depends_on
    return Resolution.ask, depends_on


def triage_fields(
    registry: Registry,
    facts: Mapping[str, JsonValue],
    conflicting: Collection[str],
    derivations: Mapping[str, str],
) -> dict[str, FieldTriage]:
    """The triage of every registry field. `facts` holds the usable facts; `conflicting` the fields of
    an open conflict, which are verified with the producer and never asked again. `derivations` maps a
    derived field to the field it derives from."""
    result: dict[str, FieldTriage] = {}
    for name, field in registry.items():
        requirement, depends_on = _requirement(field, facts)
        if name in conflicting:
            status, resolution = ValueStatus.conflicting, Resolution.verify
        elif name in facts:
            status, resolution = ValueStatus.present, Resolution.none
        else:
            status = ValueStatus.missing
            resolution, depends_on = _missing_resolution(
                field, requirement, depends_on, registry, derivations
            )
        result[name] = FieldTriage(
            value_status=status,
            requirement=requirement,
            resolution=resolution,
            depends_on=depends_on,
        )
    return result
