# ABOUTME: The skill manifest model of section 8, the loader that reads one manifest, and the check that a skill folder holds every part it needs to run.
# ABOUTME: A manifest is manifest.yaml; the folder needs skill.py, cases/ for a skill with a pass threshold, and prompt.md for a model skill only.
from pathlib import Path
from typing import Self

import yaml
from pydantic import Field, ValidationError, model_validator

from uwh.rules.models import StrictModel
from uwh.skills.vertical import COMMAND_CLASSES


class SkillFolderError(Exception):
    """A skill folder lacks a part or its manifest breaks a rule; the message names the folder."""


class SkillManifest(StrictModel):
    """manifest.yaml. `fallback` is "none" for a deterministic skill. A skill with a `pass_threshold`
    has `cases/` the eval runs; a skill without one has no eval status."""

    name: str
    version: str
    purpose: str
    trigger: str
    command_classes: list[str]
    fallback: str
    pass_threshold: float | None = Field(default=None, gt=0, le=1)
    model_skill: bool = False

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        # A skill issues its commands as the workflow actor (7.4).
        issuable = {c.name for c in COMMAND_CLASSES if "workflow" in c.actors}
        refused = [c for c in self.command_classes if c not in issuable]
        if refused:
            raise ValueError(
                f"command_classes names classes a skill cannot issue: {', '.join(refused)}"
            )
        repeated = sorted({c for c in self.command_classes if self.command_classes.count(c) > 1})
        if repeated:
            raise ValueError(
                f"command_classes lists a class twice: duplicate {', '.join(repeated)}"
            )
        return self


def _folder_error(folder: Path, problem: str) -> SkillFolderError:
    return SkillFolderError(f"skill folder {folder.name}: {problem}")


def load_manifest(folder: Path) -> SkillManifest:
    """Read and validate the manifest of the skill folder; its name must equal the folder's.

    Only manifest.yaml is read, so it works on the app image, which holds no `cases/`.
    """
    manifest_path = folder / "manifest.yaml"
    if not manifest_path.is_file():
        raise _folder_error(folder, "manifest.yaml is missing")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise _folder_error(folder, "manifest.yaml is not a mapping")
    try:
        manifest = SkillManifest.model_validate(raw)
    except ValidationError as error:
        raise _folder_error(folder, f"manifest.yaml is invalid: {error}") from error
    if manifest.name != folder.name:
        raise _folder_error(folder, f"manifest name {manifest.name!r} differs from the folder name")
    return manifest


def check_skill_folder(folder: Path) -> SkillManifest:
    """Load the manifest of the skill folder and check the folder holds each part it needs.

    A skill with a `pass_threshold` needs `cases/`, which the app image leaves out, so the check
    runs where the evals run.
    """
    manifest = load_manifest(folder)
    if not (folder / "skill.py").is_file():
        raise _folder_error(folder, "skill.py is missing")
    if manifest.pass_threshold is not None and not (folder / "cases").is_dir():
        raise _folder_error(folder, "cases/ is missing")
    has_prompt = (folder / "prompt.md").is_file()
    if manifest.model_skill and not has_prompt:
        raise _folder_error(folder, "prompt.md is missing for a model skill")
    if has_prompt and not manifest.model_skill:
        raise _folder_error(
            folder, "prompt.md exists but the manifest does not declare a model skill"
        )
    return manifest
