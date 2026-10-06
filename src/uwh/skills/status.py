# ABOUTME: A skill's status (section 8) read from the results log: the latest scored run row with no control, the skill's current digest and a result for the skill.
# ABOUTME: Gives `untested`, `passing` or `failing`, and None for a skill with no pass threshold, which has no eval; `unavailable` depends on the run mode and key, which the caller knows.
import json
from pathlib import Path

from uwh.runtime.event_types import SkillStatus
from uwh.skills.manifest import SkillManifest

# A model skill's rows count only when the model was called for real (section 8).
_MODEL_MODES = ("live", "record")


def skill_status(results: Path, manifest: SkillManifest, digest: str) -> SkillStatus | None:
    """The status of the skill at `digest` from the log at `results`; `untested` when no row speaks for
    it, and None when the skill has no pass threshold and so no cases to evaluate."""
    if manifest.pass_threshold is None:
        return None
    if not results.is_file():
        return "untested"
    latest: dict[str, bool] | None = None
    for line in results.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (
            row["kind"] == "run"
            and row["status"] == "scored"
            and row["control"] is None
            and row["skill_digests"].get(manifest.name) == digest
            and manifest.name in row["skill_results"]
            and (not manifest.model_skill or row["mode"] in _MODEL_MODES)
        ):
            latest = row["skill_results"][manifest.name]
    if latest is None:
        return "untested"
    return "passing" if latest["passed"] else "failing"
