# ABOUTME: Tests the autonomy of the send classes (7.4) and the check of a skill's manifest: a routine request sends at once, every other message waits.
# ABOUTME: The levels are read from the command classes in code.
import pytest

from tests.runtime.helpers import skill_manifest
from uwh.runtime.policy import autonomy_level, manifest_refusal


def test_a_routine_request_sends_at_once_and_every_other_message_waits_for_approval() -> None:
    assert autonomy_level("send_routine_request") == "auto"
    for name in ("send_sensitive_request", "send_quote_packet", "send_decline_notice"):
        assert autonomy_level(name) == "review", name


@pytest.mark.parametrize("name", ["approve", "send_postcard"])
def test_a_class_without_a_level_is_refused(name: str) -> None:
    with pytest.raises(ValueError):
        autonomy_level(name)


def test_a_manifest_refuses_a_class_it_does_not_declare_and_admits_one_it_does() -> None:
    manifest = skill_manifest("send_routine_request")

    assert manifest_refusal(manifest, "send_routine_request") is None
    assert manifest_refusal(manifest, "send_quote_packet") == (
        "the manifest of asker does not declare send_quote_packet"
    )
