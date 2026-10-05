# ABOUTME: Tests that the skill digest covers what A.4 names and nothing else, one clause per test on a small tree under tmp_path.
# ABOUTME: Each test compares the digest before and after one change: cases, compiled files, shared modules, rules data, model id, other skills.
import py_compile
from pathlib import Path

from uwh.runtime.hashing import active_ruleset_dir
from uwh.skills.digest import skill_digest

FILES = {
    "skills/__init__.py": "",
    "skills/vertical.py": "STATUSES = 1\n",
    "skills/demo/__init__.py": "",
    "skills/demo/manifest.yaml": "name: demo\n",
    "skills/demo/skill.py": "def run(x):\n    return x\n",
    "skills/demo/prompt.md": "prompt\n",
    "skills/demo/cases/x.yaml": "input: 1\n",
    "skills/other/manifest.yaml": "name: other\n",
    "skills/other/skill.py": "def run(x):\n    return x\n",
    "rules/__init__.py": "",
    "rules/core.py": "CORE = 1\n",
    "rules/data/interpretation.yaml": "I01: ruling\n",
    "providers/lookup.py": "LOOKUP = 1\n",
    "runtime/store.py": "STORE = 1\n",
}


def build(tmp_path: Path) -> Path:
    root = tmp_path / "src" / "uwh"
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def edit(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8", newline="\n")


def test_digest_is_stable_for_an_unchanged_tree(tmp_path: Path) -> None:
    root = build(tmp_path)
    digest = skill_digest(root, "demo")
    assert digest == skill_digest(root, "demo")
    assert len(digest) == 64


def test_digest_covers_every_source_file_in_the_skill_folder(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    for rel in ("manifest.yaml", "skill.py", "prompt.md", "__init__.py"):
        edit(root, f"skills/demo/{rel}", "changed\n")
        assert skill_digest(root, "demo") != base, rel
        edit(root, f"skills/demo/{rel}", FILES[f"skills/demo/{rel}"])
        assert skill_digest(root, "demo") == base, rel


def test_digest_covers_a_file_added_to_the_skill_folder(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    edit(root, "skills/demo/helpers.py", "H = 1\n")
    assert skill_digest(root, "demo") != base


def test_digest_covers_the_path_of_a_skill_file(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    (root / "skills/demo/prompt.md").rename(root / "skills/demo/prompt2.md")
    assert skill_digest(root, "demo") != base


def test_an_edit_under_cases_leaves_the_digest_unchanged(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    edit(root, "skills/demo/cases/x.yaml", "input: 2\n")
    edit(root, "skills/demo/cases/y.yaml", "input: 3\n")
    assert skill_digest(root, "demo") == base


def test_a_nested_directory_named_cases_is_still_a_source_file(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    (root / "skills/demo/lib/cases").mkdir(parents=True)
    edit(root, "skills/demo/lib/cases/data.py", "X = 1\n")
    assert skill_digest(root, "demo") != base


def test_compiled_files_are_never_hashed(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    for rel in (
        "skills/demo/skill.py",
        "skills/vertical.py",
        "rules/core.py",
        "providers/lookup.py",
        "runtime/store.py",
    ):
        py_compile.compile(str(root / rel), doraise=True)
    edit(root, "skills/demo/__pycache__/stray.pyc", "x")
    edit(root, "rules/data/stray.pyc", "x")
    assert list(root.rglob("__pycache__"))
    assert skill_digest(root, "demo") == base


def test_hidden_files_and_editor_leftovers_leave_the_digest_unchanged(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    for rel in (
        "skills/demo/.DS_Store",
        "skills/demo/.hidden/helper.py",
        "skills/demo/skill.py~",
        "skills/demo/.skill.py.swp",
        "skills/demo/skill.py.swp",
        "rules/data/.DS_Store",
        "rules/data/interpretation.yaml~",
        "rules/data/interpretation.yaml.swp",
        "rules/.DS_Store",
        "rules/.hidden/mod.py",
        "rules/core.py~",
        "runtime/.DS_Store",
        "runtime/store.py.swp",
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        edit(root, rel, "junk\n")
        assert skill_digest(root, "demo") == base, rel


def test_an_edit_to_a_shared_module_changes_every_skills_digest(tmp_path: Path) -> None:
    for rel in ("rules/core.py", "providers/lookup.py", "runtime/store.py", "skills/vertical.py"):
        root = build(tmp_path / rel.replace("/", "_"))
        before = {s: skill_digest(root, s) for s in ("demo", "other")}
        edit(root, rel, "CHANGED = 1\n")
        after = {s: skill_digest(root, s) for s in ("demo", "other")}
        assert all(after[s] != before[s] for s in before), rel


def test_an_added_shared_module_changes_every_skills_digest(tmp_path: Path) -> None:
    root = build(tmp_path)
    before = {s: skill_digest(root, s) for s in ("demo", "other")}
    edit(root, "runtime/clock.py", "CLOCK = 1\n")
    assert all(skill_digest(root, s) != before[s] for s in before)


def test_an_edit_to_another_skills_folder_leaves_this_digest_unchanged(tmp_path: Path) -> None:
    root = build(tmp_path)
    demo, other = skill_digest(root, "demo"), skill_digest(root, "other")
    edit(root, "skills/other/skill.py", "CHANGED = 1\n")
    assert skill_digest(root, "demo") == demo
    assert skill_digest(root, "other") != other


def test_a_non_python_file_outside_the_skill_and_rules_data_leaves_the_digest_unchanged(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    edit(root, "runtime/notes.md", "notes\n")
    edit(root, "rules/notes.yaml", "notes\n")
    edit(root, "skills/other/prompt.md", "other prompt\n")
    assert skill_digest(root, "demo") == base


def test_an_edit_to_the_image_rules_data_changes_the_digest(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    edit(root, "rules/data/interpretation.yaml", "I01: other ruling\n")
    assert skill_digest(root, "demo") != base


def test_the_active_ruleset_leaves_the_digest_unchanged(tmp_path: Path) -> None:
    # Holds by construction: the digest takes no settings and reads only under the source root.
    # It states the A.4 clause that the digest covers `rules/data/` in the image, never the
    # active ruleset.
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    rulesets = tmp_path / "volume" / "rulesets"
    active = active_ruleset_dir("ab" * 32, rulesets, root / "rules" / "data")
    active.mkdir(parents=True)
    edit(active, "interpretation.yaml", "I35: tolerance 0.2\n")
    assert skill_digest(root, "demo") == base


def test_the_model_id_is_part_of_a_model_skills_digest(tmp_path: Path) -> None:
    root = build(tmp_path)
    none = skill_digest(root, "demo")
    a = skill_digest(root, "demo", "model-a")
    b = skill_digest(root, "demo", "model-b")
    assert len({none, a, b}) == 3
    assert a == skill_digest(root, "demo", "model-a")
