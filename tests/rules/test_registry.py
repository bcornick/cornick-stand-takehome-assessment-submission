# ABOUTME: Tests the fact fields an underwriter may resolve: every registry field in the registry's order, each catalogue question that is a question, and the contact email.
# ABOUTME: Reads Stand's field registry and the image's catalogue.
from pathlib import Path

from uwh.rules.registry import CONTACT_EMAIL_KEY, fact_fields, load_registry

REGISTRY = Path(__file__).resolve().parents[2] / "docs" / "brief" / "field_registry.json"


def test_the_fact_fields_hold_every_registry_field_in_its_order_with_its_label_and_kind() -> None:
    registry = load_registry(str(REGISTRY))

    fields = fact_fields(registry)

    assert list(fields)[: len(registry)] == list(registry)
    assert fields["coverage_a"].label == registry["coverage_a"].label
    assert fields["coverage_a"].kind == registry["coverage_a"].kind
    assert fields["fire_alarm"].options == registry["fire_alarm"].options != []


def test_the_fact_fields_end_with_the_catalogue_questions_and_the_contact_email() -> None:
    registry = load_registry(str(REGISTRY))

    extra = [fact_fields(registry)[key] for key in list(fact_fields(registry))[len(registry) :]]

    assert [(f.key, f.kind) for f in extra] == [
        ("q:willing_to_mitigate", "toggle"),
        (CONTACT_EMAIL_KEY, "email"),
    ]
    assert extra[0].label.startswith("Would the applicant be willing")
