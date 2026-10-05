# ABOUTME: Tests the autonomy of the send classes (7.4) and the approval binding check: a routine request sends at once, every other message waits, and each of the five bound values breaking an approval alone.
# ABOUTME: The binding tests compare plain values; the levels are read from the command classes in code.
from dataclasses import replace

import pytest

from uwh.runtime.policy import ApprovalBinding, autonomy_level, binding_changes, manifest_refusal
from uwh.skills.manifest import SkillManifest


def test_a_routine_request_sends_at_once_and_every_other_message_waits_for_approval() -> None:
    assert autonomy_level("send_routine_request") == "auto"
    for name in ("send_sensitive_request", "send_quote_packet", "send_decline_notice"):
        assert autonomy_level(name) == "review", name


@pytest.mark.parametrize("name", ["approve", "send_postcard"])
def test_a_class_without_a_level_is_refused(name: str) -> None:
    with pytest.raises(ValueError):
        autonomy_level(name)


APPROVED = ApprovalBinding(
    lead_revision=3,
    plan_hash="p" * 64,
    ruleset_hash="r" * 64,
    recipient="producer@example.com",
    payload_hash="h" * 64,
)
CHANGED_VALUES: dict[str, object] = {
    "lead_revision": 4,
    "plan_hash": "q" * 64,
    "ruleset_hash": "s" * 64,
    "recipient": "other@example.com",
    "payload_hash": "i" * 64,
}


def test_an_unchanged_binding_holds() -> None:
    assert binding_changes(APPROVED, replace(APPROVED)) == ()


@pytest.mark.parametrize("name", CHANGED_VALUES)
def test_each_bound_value_changing_alone_breaks_the_approval(name: str) -> None:
    current = replace(APPROVED, **{name: CHANGED_VALUES[name]})

    assert binding_changes(APPROVED, current) == (name,)


def test_several_changes_are_all_named() -> None:
    current = replace(APPROVED, lead_revision=9, recipient="other@example.com")

    assert binding_changes(APPROVED, current) == ("lead_revision", "recipient")


def manifest_declaring(*command_classes: str) -> SkillManifest:
    return SkillManifest(
        name="asker",
        version="1",
        purpose="Asks the producer.",
        trigger="a fact is missing",
        command_classes=list(command_classes),
        fallback="none",
        pass_threshold=1.0,
    )


def test_a_manifest_refuses_a_class_it_does_not_declare_and_admits_one_it_does() -> None:
    manifest = manifest_declaring("send_routine_request")

    assert manifest_refusal(manifest, "send_routine_request") is None
    assert manifest_refusal(manifest, "send_quote_packet") == (
        "the manifest of asker does not declare send_quote_packet"
    )
