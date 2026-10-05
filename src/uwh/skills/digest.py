# ABOUTME: The skill digest of A.4: the skill's own source, one shared hash of the Python source outside the skill folders, the image's rules data and the model id.
# ABOUTME: Takes the `src/uwh` directory as a path; it never reads settings or the environment.
from pathlib import Path

from uwh.runtime.hashing import (
    file_entries,
    hash_json,
    ruleset_hash,
    source_files,
)


def skill_digest(src_root: Path, skill: str, model_id: str | None = None) -> str:
    """The digest of `skill`, under `src_root` (the `src/uwh` directory).

    It covers:
    - every source file in `skills/<skill>/` except `cases/`;
    - every Python file under `src_root` outside the skill folders, with the modules directly
      under `skills/` included, so a change to the rules core, a provider or the runtime changes
      every skill's digest while a change to another skill's folder changes none but its own;
    - the hash of `rules/data/` in `src_root`;
    - `model_id`, for a model skill.

    Compiled files are never hashed.
    """
    skills_dir = src_root / "skills"
    skill_dir = skills_dir / skill
    if not skill_dir.is_dir():
        raise FileNotFoundError(f"skill folder not found: {skill_dir}")

    own = [p for p in source_files(skill_dir) if p.relative_to(skill_dir).parts[0] != "cases"]
    folders = [p for p in skills_dir.iterdir() if p.is_dir() and p.name != "__pycache__"]
    shared = [
        p
        for p in source_files(src_root)
        if p.suffix == ".py" and not any(p.is_relative_to(folder) for folder in folders)
    ]
    return hash_json(
        {
            "skill": skill,
            "skill_files": file_entries(skill_dir, own),
            "shared_python": file_entries(src_root, shared),
            "rules_data": ruleset_hash(src_root / "rules" / "data"),
            "model_id": model_id,
        }
    )
