# ABOUTME: Grades the seed-42 first pass against Stand's answer key and shows the grader fails when a lead's asks are tampered with.
# ABOUTME: The key is the debug history of Stand's generator, regenerated in process; the system's state is read from the database of a real first pass.
import sqlite3
from dataclasses import replace

import pytest

from evals.graders.answer_key import (
    LeadState,
    Verdict,
    grade,
    read_lead_state,
    regenerate_history,
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
