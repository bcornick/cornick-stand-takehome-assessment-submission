# ABOUTME: Tests the skill status read from the results log: only the latest scored, non-control row at the skill's current digest counts, and a model skill ignores replay rows.
# ABOUTME: Each row is written to a temporary log in the shape of the run row of 13.5.
import json
from pathlib import Path
from typing import Any

import pytest

from uwh.skills.status import skill_status


def row(
    *,
    passed: bool = True,
    digest: str = "d1",
    status: str = "scored",
    control: str | None = None,
    mode: str = "replay",
    kind: str = "run",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "control": control,
        "mode": mode,
        "skill_digests": {"triage_fields": digest},
        "skill_results": {"triage_fields": {"cases_passed": 1, "cases_total": 1, "passed": passed}},
    }


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], "untested"),
        ([row()], "passing"),
        ([row(), row(passed=False)], "failing"),  # the latest row speaks
        ([row(passed=False), row()], "passing"),
        ([row(digest="old")], "untested"),  # the skill has changed since
        ([row(), row(passed=False, digest="old")], "passing"),
        ([row(), row(passed=False, control="do_nothing")], "passing"),
        ([row(), row(passed=False, status="invalid")], "passing"),
        ([row(), {"kind": "decision"}], "passing"),
    ],
)
def test_the_latest_scored_row_at_the_current_digest_gives_the_status(
    tmp_path: Path, rows: list[dict[str, Any]], expected: str
) -> None:
    log = tmp_path / "results.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    assert skill_status(log, "triage_fields", "d1", model_skill=False) == expected


def test_a_model_skill_ignores_a_row_from_replay(tmp_path: Path) -> None:
    log = tmp_path / "results.jsonl"
    log.write_text(json.dumps(row(mode="replay")) + "\n", encoding="utf-8")

    assert skill_status(log, "triage_fields", "d1", model_skill=True) == "untested"
    log.write_text(json.dumps(row(mode="live")) + "\n", encoding="utf-8")
    assert skill_status(log, "triage_fields", "d1", model_skill=True) == "passing"


def test_a_missing_log_leaves_the_skill_untested(tmp_path: Path) -> None:
    assert skill_status(tmp_path / "none.jsonl", "triage_fields", "d1", model_skill=False) == (
        "untested"
    )
