# ABOUTME: Runs the `cases/` table of evaluate_playbook, the skill the case runner covers (section 8) through the case runner of the evals: each case is one test, and a deliberately wrong expectation is shown to fail.
# ABOUTME: The same tables feed `make eval`, so a case that passes here is the one the run row counts.
import pytest

from evals.cases import Case, load_cases, mismatches, observe

CASES = load_cases("evaluate_playbook")


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_a_case_holds(case: Case) -> None:
    assert mismatches(case.expect, observe(case)) == []


def test_a_wrong_expectation_is_reported() -> None:
    observed = {"committed": ["no_action RF-1"], "paths": {"RF-1": ["05:ROOT"]}}

    assert mismatches({"committed": ["no_action RF-2"]}, observed) == [
        "committed: expected ['no_action RF-2'], observed ['no_action RF-1']"
    ]
    assert mismatches({"committed": {"excludes": ["no_action RF-1"]}}, observed) == [
        "committed: expected not in ['no_action RF-1']: 'no_action RF-1'"
    ]
    assert mismatches({"paths": {"RF-9": []}}, observed) == ["paths.RF-9: not observed"]
