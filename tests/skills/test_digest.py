# ABOUTME: Tests that the skill digest changes with the skill's own source, the shared modules, the rules data and the model id, and with nothing else.
# ABOUTME: Each test compares the digest before and after one change to a small tree under tmp_path.
from pathlib import Path

from uwh.skills.digest import chat_digest, skill_digest

FILES = {
    "skills/__init__.py": "",
    "skills/vertical.py": "TRANSITIONS = 1\n",
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
    "chat/__init__.py": "",
    "chat/manifest.yaml": "name: chat\n",
    "chat/prompt.md": "prompt\n",
    "chat/skill.py": "STEPS = 4\n",
    "chat/tools.py": "TOOLS = 1\n",
    "chat/cases/chat.yaml": "cases: []\n",
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


def test_digest_covers_every_source_file_in_the_skill_folder(tmp_path: Path) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    for rel in ("manifest.yaml", "skill.py", "prompt.md", "__init__.py"):
        edit(root, f"skills/demo/{rel}", "changed\n")
        assert skill_digest(root, "demo") != base, rel
        edit(root, f"skills/demo/{rel}", FILES[f"skills/demo/{rel}"])
        assert skill_digest(root, "demo") == base, rel


def test_an_edit_under_cases_or_to_another_skills_folder_leaves_the_digest_unchanged(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    base = skill_digest(root, "demo")
    edit(root, "skills/demo/cases/x.yaml", "input: 2\n")
    edit(root, "skills/demo/cases/y.yaml", "input: 3\n")
    other = skill_digest(root, "other")
    edit(root, "skills/other/skill.py", "CHANGED = 1\n")
    assert skill_digest(root, "demo") == base
    assert skill_digest(root, "other") != other


def test_an_edit_to_a_shared_module_or_the_rules_data_changes_every_skills_digest(
    tmp_path: Path,
) -> None:
    shared = (
        "rules/core.py",
        "providers/lookup.py",
        "runtime/store.py",
        "skills/vertical.py",
        "rules/data/interpretation.yaml",
    )
    for rel in shared:
        root = build(tmp_path / rel.replace("/", "_"))
        before = {s: skill_digest(root, s) for s in ("demo", "other")}
        edit(root, rel, "CHANGED = 1\n")
        after = {s: skill_digest(root, s) for s in ("demo", "other")}
        assert all(after[s] != before[s] for s in before), rel


def test_the_model_id_is_part_of_a_model_skills_digest(tmp_path: Path) -> None:
    root = build(tmp_path)
    none = skill_digest(root, "demo")
    a = skill_digest(root, "demo", "model-a")
    b = skill_digest(root, "demo", "model-b")
    assert len({none, a, b}) == 3
    assert a == skill_digest(root, "demo", "model-a")


def test_the_chat_digest_covers_the_prompt_the_manifest_the_tools_and_the_skill(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    base = chat_digest(root, "model-a")
    for rel in ("manifest.yaml", "prompt.md", "skill.py", "tools.py"):
        edit(root, f"chat/{rel}", "changed\n")
        assert chat_digest(root, "model-a") != base, rel
        edit(root, f"chat/{rel}", FILES[f"chat/{rel}"])
        assert chat_digest(root, "model-a") == base, rel


def test_the_chat_digest_ignores_its_cases_and_other_folders_and_follows_the_model_id(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    base = chat_digest(root, "model-a")
    edit(root, "chat/cases/chat.yaml", "cases: [x]\n")
    edit(root, "skills/demo/skill.py", "CHANGED = 1\n")
    edit(root, "runtime/store.py", "CHANGED = 1\n")
    assert chat_digest(root, "model-a") == base
    assert chat_digest(root, "model-b") != base
