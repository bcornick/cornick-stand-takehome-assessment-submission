# ABOUTME: Runs the `cases/` table of evaluate_playbook, the skill the case runner covers (section 8) through the case runner of the evals: each case is one test, and a deliberately wrong expectation is shown to fail.
# ABOUTME: The same tables feed `make eval`, so a case that passes here is the one the run row counts.
import pytest

from evals.cases import (
    Case,
    load_cases,
    mismatches,
    observe,
    observe_polish,
    run_polish_cases,
)

CASES = load_cases("evaluate_playbook")
POLISH_CASES = load_cases("polish_message")


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


@pytest.mark.parametrize("case", POLISH_CASES, ids=[c.name for c in POLISH_CASES])
def test_a_polish_message_case_holds(case: Case) -> None:
    assert mismatches(case.expect, observe_polish(case)) == []


def test_a_rewrite_that_a_check_rejects_is_not_reported_as_rewritten() -> None:
    (code_failure,) = [c for c in POLISH_CASES if c.expect.get("check") == "code_check"]

    assert mismatches({"result": "rewritten"}, observe_polish(code_failure)) == [
        "result: expected 'rewritten', observed 'rejected'"
    ]


def test_the_polish_message_result_counts_every_case() -> None:
    result = run_polish_cases()

    assert (result.cases_passed, result.cases_total, result.failures) == (
        len(POLISH_CASES),
        len(POLISH_CASES),
        [],
    )
