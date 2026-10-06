# ABOUTME: Grades the seed-42 first pass against Stand's answer key, pins its exemption counts, and shows the grader fails when a lead's asks or decline are tampered with.
# ABOUTME: The key is the debug history of Stand's generator, regenerated in process; the system's state is read from the database of a real first pass.
import sqlite3
from pathlib import Path
from collections import Counter
from dataclasses import replace

import pytest

from evals.graders import answer_key
from evals.graders.answer_key import (
    LeadState,
    Verdict,
    grade,
    pinned_exemptions,
    read_lead_state,
    regenerate_history,
    stands_key,
    summary,
)
from uwh.rules.registry import Registry, load_registry
from tests.api.helpers import REGISTRY

LEAD_008 = "LEAD-00000042-008"


@pytest.fixture
def registry() -> Registry:
    return load_registry(str(REGISTRY))


@pytest.fixture
def states(first_pass_db: sqlite3.Connection) -> dict[str, LeadState]:
    return {
        lead_id: read_lead_state(first_pass_db, lead_id)
        for (lead_id,) in first_pass_db.execute("SELECT lead_id FROM leads")
    }


def test_the_key_agrees_on_every_seed_42_record_it_decides(
    states: dict[str, LeadState], registry: Registry
) -> None:
    judgements = grade(regenerate_history(42), states, registry)
    report = summary(judgements)
    print(report)

    assert judgements
    assert not [j for j in judgements if j.verdict == Verdict.disagrees], report


def test_the_exemptions_the_system_decides_are_the_counts_the_labels_pin(
    states: dict[str, LeadState], registry: Registry
) -> None:
    counts = Counter(j.verdict for j in grade(regenerate_history(42), states, registry))

    pinned = pinned_exemptions(42)
    assert pinned == {Verdict.exempt_proposed_decline: 26, Verdict.exempt_blocked: 0}
    assert {verdict: counts[verdict] for verdict in pinned} == pinned


def test_a_lead_wrongly_proposed_as_a_decline_moves_the_exemption_count(
    states: dict[str, LeadState], registry: Registry
) -> None:
    tampered = {**states, LEAD_008: replace(states[LEAD_008], proposed_decline=True)}

    counts = Counter(j.verdict for j in grade(regenerate_history(42), tampered, registry))

    assert (
        counts[Verdict.exempt_proposed_decline]
        > pinned_exemptions(42)[Verdict.exempt_proposed_decline]
    )


def test_a_removed_ask_is_a_disagreement(states: dict[str, LeadState], registry: Registry) -> None:
    lead = states[LEAD_008]
    assert "property_purchase_date" in lead.asked
    tampered = {**states, LEAD_008: replace(lead, asked=lead.asked - {"property_purchase_date"})}

    history = regenerate_history(42)
    before = {j.record for j in grade(history, states, registry) if j.verdict == Verdict.disagrees}
    after = [j for j in grade(history, tampered, registry) if j.verdict == Verdict.disagrees]

    (new,) = [j for j in after if j.record not in before]
    assert (new.record.lead_id, new.record.field) == (LEAD_008, "property_purchase_date")
    assert "none was made" in new.reason


def test_a_conflict_with_no_confirmation_is_a_disagreement(
    states: dict[str, LeadState], registry: Registry
) -> None:
    lead = "LEAD-00000042-004"
    assert "number_of_residents" in states[lead].confirmed
    tampered = {**states, lead: replace(states[lead], confirmed=frozenset())}

    after = [
        j
        for j in grade(regenerate_history(42), tampered, registry)
        if j.verdict == Verdict.disagrees
    ]

    (conflict,) = after
    assert (conflict.record.lead_id, conflict.record.kind) == (lead, "conflict")
    assert conflict.reason == "no confirmation covers the conflict"


def test_the_key_grader_fails_when_an_exemption_count_differs_from_the_pinned_one(
    first_pass_db: sqlite3.Connection,
    registry: Registry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert stands_key(first_pass_db, registry, 42).failures == []
    pins = tmp_path / "evals" / "labels" / "seed42"
    pins.mkdir(parents=True)
    (pins / "exemptions.yaml").write_text(
        "exemptions: {proposed_decline: 25, blocked: 1}\n", encoding="utf-8"
    )
    monkeypatch.setattr(answer_key, "ROOT", tmp_path)

    failures = stands_key(first_pass_db, registry, 42).failures

    assert failures == [
        "exempt_proposed_decline is 26, the labels pin 25",
        "exempt_blocked is 0, the labels pin 1",
    ]
