# ABOUTME: The autonomy level of a command class (7.4), fixed in code, the five values an approval binds and the check of a skill's manifest.
# ABOUTME: Pure checks over a command class and a manifest; the send and the decision to dispatch belong to other modules.
from dataclasses import dataclass

from uwh.runtime.event_types import AutonomyLevel
from uwh.skills import vertical
from uwh.skills.manifest import SkillManifest


def autonomy_level(command_class: str) -> AutonomyLevel:
    """The level of the class: `auto` sends without an approval, `review` waits for one.

    Raises ValueError for an unknown class and for a human-only class (no level applies).
    """
    declared = vertical.command_class(command_class)
    if declared is None:
        raise ValueError(f"unknown command class {command_class}")
    if declared.default_level is None:
        raise ValueError(f"{command_class} has no autonomy level")
    return declared.default_level


@dataclass(frozen=True)
class ApprovalBinding:
    """The five values an approval binds to (7.4): the lead revision, the action-plan hash, the ruleset
    hash, the recipient and the payload hash of the exact message or packet."""

    lead_revision: int
    plan_hash: str
    ruleset_hash: str
    recipient: str
    payload_hash: str


def manifest_refusal(manifest: SkillManifest, command_class: str) -> str | None:
    """The reason the skill may not issue the command class, or None when its manifest declares it (8)."""
    if command_class not in manifest.command_classes:
        return f"the manifest of {manifest.name} does not declare {command_class}"
    return None
