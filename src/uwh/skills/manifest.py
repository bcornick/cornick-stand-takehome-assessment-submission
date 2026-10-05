# ABOUTME: The skill manifest model of section 8 and the check that a skill folder holds every part it needs.
# ABOUTME: A manifest is manifest.yaml; the folder needs skill.py, a cases/ folder with a case file, and prompt.md for a model skill only.
from pathlib import Path
from typing import Self

import yaml
from pydantic import Field, ValidationError, model_validator

from uwh.rules.models import StrictModel
from uwh.skills.vertical import COMMAND_CLASSES


class SkillFolderError(Exception):
    """A skill folder lacks a part or its manifest breaks a rule; the message names the folder."""


class SkillManifest(StrictModel):
    """manifest.yaml. `fallback` is "none" for a deterministic skill."""

    name: str
    version: str
    purpose: str
    trigger: str
    command_classes: list[str]
    fallback: str
    pass_threshold: float = Field(gt=0, le=1)
    threshold_reason: str | None = None
    model_skill: bool = False

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        known = {c.name for c in COMMAND_CLASSES}
        unknown = [c for c in self.command_classes if c not in known]
        if unknown:
            raise ValueError(f"command_classes names unknown classes: {', '.join(unknown)}")
        if self.pass_threshold != 1.0 and not self.threshold_reason:
            raise ValueError("a pass_threshold other than 1.0 needs a threshold_reason")
        return self


def check_skill_folder(folder: Path) -> SkillManifest:
    """Load the manifest of the skill folder and check the folder holds each part it needs.

    A case file is a `*.yaml` file directly in `cases/` whose name does not start with a dot.
    """

    def fail(problem: str) -> SkillFolderError:
        return SkillFolderError(f"skill folder {folder.name}: {problem}")

    manifest_path = folder / "manifest.yaml"
    if not manifest_path.is_file():
        raise fail("manifest.yaml is missing")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise fail("manifest.yaml is not a mapping")
    try:
        manifest = SkillManifest.model_validate(raw)
    except ValidationError as error:
        raise fail(f"manifest.yaml is invalid: {error}") from error
    if manifest.name != folder.name:
        raise fail(f"manifest name {manifest.name!r} differs from the folder name")
    if not (folder / "skill.py").is_file():
        raise fail("skill.py is missing")
    cases = folder / "cases"
    if not cases.is_dir():
        raise fail("cases is missing")
    if not any(
        p.is_file() and p.suffix == ".yaml" and not p.name.startswith(".") for p in cases.iterdir()
    ):
        raise fail("cases holds no case file (*.yaml)")
    has_prompt = (folder / "prompt.md").is_file()
    if manifest.model_skill and not has_prompt:
        raise fail("prompt.md is missing for a model skill")
    if has_prompt and not manifest.model_skill:
        raise fail("prompt.md exists but the manifest does not declare a model skill")
    return manifest
