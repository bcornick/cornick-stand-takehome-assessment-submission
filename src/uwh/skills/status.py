# ABOUTME: A skill's status (section 8) read from the results log: the latest scored run row with no control, the skill's current digest and a result for the skill.
# ABOUTME: Gives `untested`, `passing` or `failing`; `unavailable` depends on the run mode and key, which the caller knows.
import json
from pathlib import Path

from uwh.runtime.event_types import SkillStatus

# A model skill's rows count only when the model was called for real (section 8).
_MODEL_MODES = ("live", "record")


def skill_status(results: Path, skill: str, digest: str, *, model_skill: bool) -> SkillStatus:
    """The status of `skill` at `digest` from the log at `results`; `untested` when no row speaks for it."""
    if not results.is_file():
        return "untested"
    latest: dict[str, bool] | None = None
    for line in results.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (
            row["kind"] == "run"
            and row["status"] == "scored"
            and row["control"] is None
            and row["skill_digests"].get(skill) == digest
            and skill in row["skill_results"]
            and (not model_skill or row["mode"] in _MODEL_MODES)
        ):
            latest = row["skill_results"][skill]
    if latest is None:
        return "untested"
    return "passing" if latest["passed"] else "failing"
