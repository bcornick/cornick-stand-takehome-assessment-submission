# ABOUTME: Runs every skill's `cases/` tables (section 8) through the case runner of the evals: each case is one test, and a deliberately wrong expectation is shown to fail.
# ABOUTME: The same tables feed `make eval`, so a case that passes here is the one the run row counts.
import pytest

from evals.cases import Case, OBSERVERS, load_cases, mismatches
from tests.api.helpers import REGISTRY
from uwh.rules.registry import Registry, load_registry

CASES = [(skill, case) for skill in OBSERVERS for case in load_cases(skill)]


@pytest.fixture(scope="module")
def registry() -> Registry:
    return load_registry(str(REGISTRY))


@pytest.mark.parametrize(("skill", "case"), CASES, ids=[f"{s}: {c.name}" for s, c in CASES])
def test_a_case_holds(skill: str, case: Case, registry: Registry) -> None:
    assert mismatches(case.expect, OBSERVERS[skill](case, registry)) == []


def test_a_wrong_expectation_is_reported() -> None:
    observed = {"committed": ["no_action RF-1"], "paths": {"RF-1": ["05:ROOT"]}}

    assert mismatches({"committed": ["no_action RF-2"]}, observed) == [
        "committed: expected ['no_action RF-2'], observed ['no_action RF-1']"
    ]
    assert mismatches({"committed": {"excludes": ["no_action RF-1"]}}, observed) == [
        "committed: expected not in ['no_action RF-1']: 'no_action RF-1'"
    ]
    assert mismatches({"paths": {"RF-9": []}}, observed) == ["paths.RF-9: not observed"]
