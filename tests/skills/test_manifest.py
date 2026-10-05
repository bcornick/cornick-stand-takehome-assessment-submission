# ABOUTME: Tests the skill folder check of section 8: each missing part, each manifest rule, and the real tree against SKILLS.
# ABOUTME: Folders are built under tmp_path so each failing case is shown; the real-tree tests fail on an unregistered or incomplete skill.
from pathlib import Path
from typing import Any

import pytest
import yaml

import uwh.skills
from uwh.skills import SKILLS
from uwh.skills.manifest import SkillFolderError, check_skill_folder

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
    cases: tuple[str, ...] = ("one.yaml",),
) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    if "manifest.yaml" not in skip:
        text = yaml.safe_dump(MANIFEST if manifest is None else manifest)
        (folder / "manifest.yaml").write_text(text, encoding="utf-8")
    if "skill.py" not in skip:
        (folder / "skill.py").write_text("# skill\n", encoding="utf-8")
    if "cases" not in skip:
        (folder / "cases").mkdir()
        for case in cases:
            (folder / "cases" / case).write_text("input: 1\n", encoding="utf-8")
    if prompt:
        (folder / "prompt.md").write_text("prompt\n", encoding="utf-8")
    return folder


def test_a_complete_deterministic_skill_loads(tmp_path: Path) -> None:
    manifest = check_skill_folder(build(tmp_path))
    assert manifest.name == "demo"
    assert manifest.command_classes == ["fetch_data"]
    assert manifest.pass_threshold == 1.0


def test_a_complete_model_skill_loads(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "model_skill": True}, prompt=True)
    assert check_skill_folder(folder).model_skill is True


@pytest.mark.parametrize("part", ["manifest.yaml", "skill.py", "cases"])
def test_a_missing_part_is_named(tmp_path: Path, part: str) -> None:
    with pytest.raises(SkillFolderError, match=f"(?s)demo.*{part}"):
        check_skill_folder(build(tmp_path, skip=(part,)))


@pytest.mark.parametrize("cases", [(), (".gitkeep",), (".hidden.yaml",), ("notes.md",)])
def test_a_cases_folder_without_a_case_file_fails(tmp_path: Path, cases: tuple[str, ...]) -> None:
    with pytest.raises(SkillFolderError, match="(?s)demo.*cases"):
        check_skill_folder(build(tmp_path, cases=cases))


def test_a_model_skill_without_a_prompt_fails(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "model_skill": True})
    with pytest.raises(SkillFolderError, match="(?s)demo.*prompt.md"):
        check_skill_folder(folder)


def test_a_deterministic_skill_with_a_prompt_fails(tmp_path: Path) -> None:
    with pytest.raises(SkillFolderError, match="(?s)demo.*prompt.md"):
        check_skill_folder(build(tmp_path, prompt=True))


def test_a_manifest_name_that_differs_from_the_folder_fails(tmp_path: Path) -> None:
    with pytest.raises(SkillFolderError, match="(?s)demo.*name"):
        check_skill_folder(build(tmp_path, {**MANIFEST, "name": "other"}))


def test_an_unknown_command_class_fails(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "command_classes": ["launch_rocket"]})
    with pytest.raises(SkillFolderError, match="(?s)demo.*launch_rocket"):
        check_skill_folder(folder)


def test_a_skill_that_issues_no_command_has_an_empty_list(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "command_classes": []})
    assert check_skill_folder(folder).command_classes == []


def test_an_unknown_field_fails(tmp_path: Path) -> None:
    with pytest.raises(SkillFolderError, match="(?s)demo.*surprise"):
        check_skill_folder(build(tmp_path, {**MANIFEST, "surprise": 1}))


@pytest.mark.parametrize(
    "field",
    ["name", "version", "purpose", "trigger", "command_classes", "fallback", "pass_threshold"],
)
def test_a_manifest_missing_a_field_fails(tmp_path: Path, field: str) -> None:
    manifest = {k: v for k, v in MANIFEST.items() if k != field}
    with pytest.raises(SkillFolderError, match=f"(?s)demo.*{field}"):
        check_skill_folder(build(tmp_path, manifest))


def test_a_threshold_below_one_needs_a_reason(tmp_path: Path) -> None:
    folder = build(tmp_path, {**MANIFEST, "pass_threshold": 0.9})
    with pytest.raises(SkillFolderError, match="(?s)demo.*threshold_reason"):
        check_skill_folder(folder)


def test_a_threshold_below_one_with_a_reason_loads(tmp_path: Path) -> None:
    manifest = {**MANIFEST, "pass_threshold": 0.9, "threshold_reason": "Replies are ambiguous."}
    assert check_skill_folder(build(tmp_path, manifest)).pass_threshold == 0.9


@pytest.mark.parametrize("threshold", [0, -0.5, 1.5])
def test_a_threshold_outside_zero_to_one_fails(tmp_path: Path, threshold: float) -> None:
    manifest = {**MANIFEST, "pass_threshold": threshold, "threshold_reason": "Because."}
    with pytest.raises(SkillFolderError, match="(?s)demo.*pass_threshold"):
        check_skill_folder(build(tmp_path, manifest))


def test_a_manifest_that_is_not_a_mapping_fails(tmp_path: Path) -> None:
    folder = build(tmp_path)
    (folder / "manifest.yaml").write_text("- a\n- list\n", encoding="utf-8")
    with pytest.raises(SkillFolderError, match="(?s)demo.*manifest.yaml"):
        check_skill_folder(folder)


SKILLS_DIR = Path(uwh.skills.__file__).parent


def test_skills_is_a_plain_list_of_names() -> None:
    assert isinstance(SKILLS, list)
    assert all(isinstance(name, str) for name in SKILLS)
    assert len(SKILLS) == len(set(SKILLS))


def test_every_skill_folder_is_registered() -> None:
    folders = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert folders == set(SKILLS)


def test_every_registered_skill_folder_is_complete() -> None:
    for name in SKILLS:
        assert check_skill_folder(SKILLS_DIR / name).name == name
