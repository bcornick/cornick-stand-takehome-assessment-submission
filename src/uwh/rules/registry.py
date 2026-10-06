# ABOUTME: Stand's field registry as typed fields in registry order: label, section, answer type and options, requirement level, the condition prose of a conditional field and who may supply the value.
# ABOUTME: The registry is read from the file the settings name; nothing here caches it. The fact fields are the keys an underwriter may resolve: the registry's, the catalogue's questions and the contact email.
import json
from pathlib import Path

from uwh.rules.data_files import read_yaml
from uwh.rules.models import StrictModel


class RegistryField(StrictModel):
    name: str
    label: str
    section: str
    kind: str  # the registry's answer type: date, integer, select, toggle ...
    options: list[str]  # the option strings of a select; empty otherwise
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
            label=entry["label"],
            section=entry["section"],
            kind=entry["type"]["kind"],
            options=entry["type"].get("options", []),
            required=entry["required"],
            required_when=entry.get("requiredWhen"),
            producer_editable=entry["editableByProducer"],
        )
        for name, entry in raw["fields"].items()
    }


# The internal fact key of the recipient of a lead with no contact route (A.11).
CONTACT_EMAIL_KEY = "q:contact_email"


class FactField(StrictModel):
    """A fact key an underwriter may resolve, with the label and answer type the page offers it by."""

    key: str
    label: str
    kind: str
    options: list[str]


def fact_fields(registry: Registry) -> dict[str, FactField]:
    """The keys `resolve_fact` accepts: every registry field in registry order, then each catalogue
    question as `q:<catalogue id>` (a document request is not a question), then the contact email."""
    fields = {
        name: FactField(key=name, label=field.label, kind=field.kind, options=field.options)
        for name, field in registry.items()
    }
    for catalogue_id, question in read_yaml("catalogue.yaml")["questions"].items():
        if question["answer_type"] != "document":
            key = f"q:{catalogue_id}"
            fields[key] = FactField(
                key=key, label=question["wording"], kind=question["answer_type"], options=[]
            )
    fields[CONTACT_EMAIL_KEY] = FactField(
        key=CONTACT_EMAIL_KEY, label="Contact email", kind="email", options=[]
    )
    return fields
