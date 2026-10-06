# ABOUTME: Tests the chat suite (13.3, Chat): the row holds the Chat grader and the chat case result, and the grader fails a turn whose outcome is not the one its case expects.
# ABOUTME: The turns are the recorded chat cases played in replay; a wrong expectation is the turn graded against another outcome, or given a command it must not cause.
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

import uwh
from evals import run
from evals.cases import load_chat_cases
from evals.graders.chat import Expect, TurnEvidence, chat
from evals.run import evaluate_chat
from uwh.api.runtime import open_runtime
from uwh.runtime.event_types import EventType
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings
from uwh.skills.digest import chat_digest

OUTCOMES: tuple[Expect, ...] = ("answer_with_event", "proposal_card", "refused")


@pytest.fixture
def turns(
    settings: Settings, leadgen: LeadgenClient, stand_mailbox_client: httpx2.Client
) -> Iterator[list[TurnEvidence]]:
    mailbox = MailboxClient(stand_mailbox_client)
    mailbox.reset()
    with open_runtime(settings, leadgen, mailbox) as runtime, runtime.database() as db:
        played, misses = run.play_chat_cases(runtime, db, load_chat_cases())
    assert misses == []
    yield played


def test_the_chat_suite_passes_its_cases_and_its_row_holds_the_grader_and_the_case_result(
    settings: Settings, stand_leadgen_client: httpx2.Client, stand_mailbox_client: httpx2.Client
) -> None:
    row = evaluate_chat(
        settings, stand_leadgen_client, stand_mailbox_client, control=None, hypothesis=None
    )

    assert row["status"] == "scored" and row["suite"] == "chat"
    assert row["scores"]["Chat"]["passed"] is True, row["scores"]["Chat"]["failures"]
    assert row["skill_results"]["chat"] == {"cases_passed": 3, "cases_total": 3, "passed": True}
    assert row["tokens"]["in"] > 0 and row["tokens"]["out"] > 0
    assert row["cost_usd"] == 0.0
    assert row["skill_digests"]["chat"] == chat_digest(Path(uwh.__file__).parent, settings.model_id)


def test_every_turn_of_the_cases_has_the_outcome_its_case_expects(
    turns: list[TurnEvidence],
) -> None:
    assert [t.expect for t in turns] == [
        "answer_with_event",
        "proposal_card",
        "refused",
        "refused",
    ]
    assert chat(turns).failures == []


def test_a_turn_graded_against_another_outcome_fails(turns: list[TurnEvidence]) -> None:
    for turn in turns:
        for wrong in OUTCOMES:
            if wrong != turn.expect:
                assert chat([replace(turn, expect=wrong)]).failures, (turn.expect, wrong)


def test_a_question_that_caused_a_command_fails(turns: list[TurnEvidence]) -> None:
    card = next(t for t in turns if t.expect == "proposal_card")

    failures = chat([replace(card, expect="answer_with_event", cited_event_ids=[1])]).failures

    assert any("proposal_created" in f for f in failures)


def test_an_answer_that_cites_no_event_fails(turns: list[TurnEvidence]) -> None:
    question = next(t for t in turns if t.expect == "answer_with_event")

    failures = chat([replace(question, cited_event_ids=[])]).failures

    assert failures == [f"{question.case} / {question.message!r}: it cited no event id"]


def test_a_refusal_that_also_left_a_card_fails(turns: list[TurnEvidence]) -> None:
    refused = next(t for t in turns if t.expect == "refused")
    card = next(t for t in turns if t.expect == "proposal_card")

    failures = chat(
        [replace(refused, events=refused.events + card.events, proposal_id=card.proposal_id)]
    ).failures

    assert any(EventType.proposal_created.value in f for f in failures)
    assert any("card" in f for f in failures)
