# ABOUTME: Tests the skill folder check of section 8: a missing part, a prompt that does not fit the skill, a command class the skill may not issue, and every registered skill folder.
# ABOUTME: Folders are built under tmp_path so each failing case is shown; the real-tree tests fail on an unregistered or incomplete skill.
from pathlib import Path
from typing import Any

import pytest
import yaml

import uwh.skills
from uwh.skills import SKILLS
from uwh.skills.manifest import SkillFolderError, check_skill_folder
from uwh.skills.vertical import COMMAND_CLASSES

MANIFEST: dict[str, Any] = {
    "name": "demo",
    "version": "1",
    "purpose": "Shows the manifest.",
    "trigger": "a demo happens",
    "command_classes": ["fetch_data"],
    "fallback": "none",
    "pass_threshold": 1.0,
    "model_skill": False,
}


def build(
    tmp_path: Path,
    manifest: dict[str, Any] | None = None,
    *,
    skip: tuple[str, ...] = (),
    prompt: bool = False,
) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    if "manifest.yaml" not in skip:
        text = yaml.safe_dump(MANIFEST if manifest is None else manifest)
        (folder / "manifest.yaml").write_text(text, encoding="utf-8")
    if "skill.py" not in skip:
        (folder / "skill.py").write_text("# skill\n", encoding="utf-8")
    if prompt:
        (folder / "prompt.md").write_text("prompt\n", encoding="utf-8")
    return folder


@pytest.mark.parametrize("part", ["manifest.yaml", "skill.py"])
def test_a_missing_part_is_named(tmp_path: Path, part: str) -> None:
    with pytest.raises(SkillFolderError, match=f"(?s)demo.*{part}"):
        check_skill_folder(build(tmp_path, skip=(part,)))


@pytest.mark.parametrize("model_skill", [True, False])
def test_a_prompt_that_does_not_fit_the_skill_fails(tmp_path: Path, model_skill: bool) -> None:
    # A model skill needs a prompt and a deterministic skill must not carry one.
    folder = build(tmp_path, {**MANIFEST, "model_skill": model_skill}, prompt=not model_skill)
    with pytest.raises(SkillFolderError, match="(?s)demo.*prompt.md"):
        check_skill_folder(folder)


def test_an_unknown_command_class_fails(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "command_classes": ["launch_rocket"]})
    with pytest.raises(SkillFolderError, match="(?s)demo.*launch_rocket"):
        check_skill_folder(folder)


@pytest.mark.parametrize("name", [c.name for c in COMMAND_CLASSES if "workflow" not in c.actors])
def test_a_class_the_workflow_actor_may_not_submit_fails(tmp_path: Path, name: str) -> None:
    folder = build(tmp_path, {**MANIFEST, "command_classes": ["fetch_data", name]})
    with pytest.raises(SkillFolderError, match=f"(?s)demo.*{name}"):
        check_skill_folder(folder)


SKILLS_DIR = Path(uwh.skills.__file__).parent


def test_every_registered_skill_folder_is_complete() -> None:
    for name in SKILLS:
        assert check_skill_folder(SKILLS_DIR / name).name == name
