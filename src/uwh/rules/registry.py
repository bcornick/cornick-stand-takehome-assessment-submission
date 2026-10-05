# ABOUTME: Stand's field registry as typed fields in registry order: section, requirement level, the condition prose of a conditional field and who may supply the value.
# ABOUTME: The registry is read from the file the settings name; nothing here caches it.
import json
from pathlib import Path

from uwh.rules.models import StrictModel


class RegistryField(StrictModel):
    name: str
    section: str
    required: str  # always, conditional, bind_only or no
    required_when: str | None  # the registry's condition prose, for a conditional field
    producer_editable: bool  # false: system-owned, fetched or derived and never asked


Registry = dict[str, RegistryField]


def load_registry(path: str) -> Registry:
    """The registry's fields keyed by name, in the registry's order."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: RegistryField(
            name=name,
            section=entry["section"],
            required=entry["required"],
            required_when=entry.get("requiredWhen"),
            producer_editable=entry["editableByProducer"],
        )
        for name, entry in raw["fields"].items()
    }
