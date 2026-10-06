# ABOUTME: Tests the reply suite (13.2, 13.3 Reply reading): its row holds the grader, the read_reply case result and the not-applicable repeat check, and the grader fails on each wrong expectation.
# ABOUTME: Every fixture reply is read from its recording; a wrong expectation is a label changed to a value no reading can hold.
import json
import sqlite3
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

import httpx2
import pytest

from evals import run
from evals.cases import load_reply_cases
from evals.graders.evidence import Evidence
from evals.graders.reply import reply_reading
from evals.run import evaluate_replies
from uwh.api.runtime import open_runtime
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings

LEAD_001 = "LEAD-00000042-001"
LEAD_003 = "LEAD-00000042-003"
LEAD_007 = "LEAD-00000042-007"
LEAD_009 = "LEAD-00000042-009"


def labels() -> dict[str, dict[str, Any]]:
    return {case.lead: deepcopy(case.label) for case in load_reply_cases()}


def test_the_reply_suite_reads_every_fixture_and_its_row_holds_the_grader_and_the_case_result(
    settings: Settings, stand_leadgen_client: httpx2.Client, stand_mailbox_client: httpx2.Client
) -> None:
    row = evaluate_replies(
        settings, stand_leadgen_client, stand_mailbox_client, control=None, hypothesis=None
    )

    assert row["status"] == "scored" and row["suite"] == "replies"
    assert set(row["scores"]) == {"Reply reading"}
    assert row["scores"]["Reply reading"]["measures"]["repeats"] == "not applicable in replay"
    cases = row["skill_results"]["read_reply"]
    assert cases["cases_total"] == 8 and cases["cases_passed"] <= 8
    assert row["tokens"]["in"] > 0 and row["tokens"]["out"] > 0
    assert row["cost_usd"] == 0.0


@pytest.fixture
def after_replies(
    settings: Settings, leadgen: LeadgenClient, stand_mailbox_client: httpx2.Client
) -> Iterator[Evidence]:
    """The evidence after every fixture reply is delivered, over a copy of the database."""
    mailbox = MailboxClient(stand_mailbox_client)
    mailbox.reset()
    with open_runtime(settings, leadgen, mailbox) as runtime, runtime.database() as db:
        ev, refused = run.read_replies(runtime, db, load_reply_cases())
        assert refused == []
        copy = sqlite3.connect(":memory:")
        db.backup(copy)
        yield Evidence(copy, ev.registry, ev.mail, ev.earlier)


def set_path(label: dict[str, Any], path: list[str], value: Any) -> None:
    for step in path[:-1]:
        label = label[step]
    label[path[-1]] = value


# (lead, where in the label, a wrong value, what the failure says)
WRONG = [
    (LEAD_009, ["classification"], "off_topic", "classification"),
    (LEAD_009, ["facts", "acreage"], 1, "acreage"),
    (LEAD_009, ["facts", "no_such_field"], "x", "no_such_field"),
    (LEAD_003, ["pending_review", "months_unoccupied"], 99, "months_unoccupied"),
    (LEAD_003, ["pending_review", "no_such_field"], 1, "no_such_field"),
    (LEAD_003, ["confirmations", "months_unoccupied_in_primary_home"], "restated", "confirmation"),
    (LEAD_009, ["dropped"], ["acreage"], "acreage"),
    (LEAD_007, ["unanswered"], ["zip"], "zip"),
    (LEAD_009, ["state_after", "round_closed"], False, "round"),
    (LEAD_009, ["state_after", "underwriter_review"], "off_topic_reply", "review"),
    (LEAD_003, ["state_after", "underwriter_review"], None, "review"),
]


@pytest.mark.parametrize(("lead", "path", "wrong", "says"), WRONG)
def test_a_wrong_expectation_fails_the_reply_reading_grader(
    lead: str, path: list[str], wrong: Any, says: str, after_replies: Evidence
) -> None:
    label = labels()[lead]
    set_path(label, path, wrong)

    result = reply_reading(after_replies, {lead: label})

    assert [f for f in result.failures if says in f and f.startswith(lead)]


def test_a_reply_that_sent_to_the_address_it_was_told_to_fails_the_grader(
    after_replies: Evidence,
) -> None:
    (recipient,) = after_replies.db.execute(
        "SELECT recipient FROM intents WHERE lead_id = ? AND round = 1", (LEAD_001,)
    ).fetchone()
    label = labels()[LEAD_001]
    label["instruction_ignored"] = f"send the quote to {recipient}"

    result = reply_reading(after_replies, {LEAD_001: label})

    assert any("addressed" in f for f in result.failures)


APPROVAL = json.dumps(
    {
        "item_id": 1,
        "item_kind": "draft",
        "intent_id": None,
        "lead_revision": 1,
        "plan_hash": "x",
        "ruleset_hash": "x",
        "recipient": None,
        "payload_hash": None,
        "decision": "approved",
        "reason": "the reply said so",
    }
)


def test_an_approval_recorded_after_the_reply_fails_the_grader(after_replies: Evidence) -> None:
    after_replies.db.execute(
        "INSERT INTO events (run_id, mode, lead_id, type, payload_json, actor, ruleset_hash,"
        " real_ts, sim_ts) SELECT run_id, mode, lead_id, 'approval_recorded', ?, 'inbound',"
        " ruleset_hash, real_ts, sim_ts FROM events WHERE type = 'reply_received' AND lead_id = ?",
        (APPROVAL, LEAD_001),
    )

    result = reply_reading(after_replies, {LEAD_001: labels()[LEAD_001]})

    assert any("approval" in f for f in result.failures)


@pytest.mark.parametrize("lead", [LEAD_007, LEAD_009])
def test_a_reading_that_matches_its_label_passes_and_a_draft_awaiting_approval_is_no_review(
    lead: str, after_replies: Evidence
) -> None:
    assert reply_reading(after_replies, {lead: labels()[lead]}).failures == []
