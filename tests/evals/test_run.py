# ABOUTME: Tests the eval runner end to end in process against Stand's leadgen and mailbox apps: the reference run passes and its row holds the fields of 13.5, each control is caught by its named grader, and an unreachable service gives an invalid row and a non-zero exit.
# ABOUTME: Every run replays the recordings, so no model is called.
import json
from pathlib import Path

import httpx2
import pytest

from evals import run
from evals.controls import Control
from evals.run import evaluate_seed42, failed
from uwh.settings import Settings


FIELDS = {
    "kind",
    "run_id",
    "commit",
    "evaluator_hash",
    "case_set_id",
    "skill_digests",
    "scores",
    "critical_errors",
    "tokens",
    "cost_usd",
    "hypothesis",
    "suite",
    "control",
    "mode",
    "status",
    "skill_results",
}


def test_the_reference_run_passes_every_grader_and_its_row_holds_the_fields_of_13_5(
    settings: Settings, stand_leadgen_client: httpx2.Client, stand_mailbox_client: httpx2.Client
) -> None:
    row = evaluate_seed42(
        settings, stand_leadgen_client, stand_mailbox_client, control=None, hypothesis="a test"
    )

    assert failed(row) == []
    assert FIELDS <= row.keys()
    assert (row["suite"], row["control"], row["mode"], row["hypothesis"]) == (
        "seed42",
        None,
        "replay",
        "a test",
    )
    assert row["tokens"]["in"] > 0  # lead 008's reply was read from its recording


# The graders each control must fail (13.4).
CAUGHT_BY = {
    Control.do_nothing: {"Coverage"},
    Control.email_everything: {"Forbidden asks", "Asks"},
    Control.send_twice: {"Send safety", "One open request"},
}


@pytest.mark.parametrize("control", list(Control))
def test_each_control_is_caught_by_its_named_graders(
    control: Control,
    settings: Settings,
    stand_leadgen_client: httpx2.Client,
    stand_mailbox_client: httpx2.Client,
) -> None:
    row = evaluate_seed42(
        settings, stand_leadgen_client, stand_mailbox_client, control=control, hypothesis=None
    )

    failing = {name for name, score in row["scores"].items() if not score["passed"]}
    assert CAUGHT_BY[control] <= failing
    assert row["control"] == control.value
    assert failed(row)


def test_an_unreachable_service_gives_an_invalid_row_and_a_non_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "results.jsonl"
    monkeypatch.setattr(run, "RESULTS_PATH", log)
    for name, value in {
        "UWH_DB": "per run",
        "RUN_MODE": "replay",
        "GIT_COMMIT": "0123abc",
        "LEADGEN_URL": "http://127.0.0.1:9",
        "MAILBOX_URL": "http://127.0.0.1:9",
    }.items():
        monkeypatch.setenv(name, value)

    assert run.main(["--suite", "seed42"]) == 1

    (row,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert row["status"] == "invalid" and "scores" not in row
    assert "health check" in row["reason"]
