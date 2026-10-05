# ABOUTME: The derivations of 9.3: roof class and siding class computed from the material by the maps in `derivations.yaml`, as ledger derivations.
# ABOUTME: The maps are copied from Stand's generator; a derived field is never fetched or asked while its material is known.
from collections.abc import Mapping

from pydantic import JsonValue

from uwh.rules.data_files import read_yaml
from uwh.runtime.facts import Derivation


def _map_derivation(key: str, source: str, mapping: Mapping[str, str]) -> Derivation:
    def compute(inputs: Mapping[str, JsonValue]) -> JsonValue:
        return mapping[str(inputs[source])]

    return Derivation(id=f"{key}_map", key=key, inputs=(source,), compute=compute)


def ledger_derivations() -> tuple[Derivation, ...]:
    """One ledger derivation per map: the field takes the class its material maps to."""
    return tuple(
        _map_derivation(key, spec["from"], spec["map"])
        for key, spec in read_yaml("derivations.yaml")["maps"].items()
    )


def derived_from() -> dict[str, str]:
    """Each derived field and the field it derives from."""
    return {key: spec["from"] for key, spec in read_yaml("derivations.yaml")["maps"].items()}
