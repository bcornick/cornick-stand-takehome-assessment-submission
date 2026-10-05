# ABOUTME: Tests the ten source-authority rules of 7.3 as named tests, the lead revision that moves when an effective fact changes, and a Hypothesis property on underwriter rulings and system-owned fields.
# ABOUTME: Each test opens a real database through open_store, inserts the lead it needs and reads back the observations, effective facts, blockers, events and revision; validators and derivations are plain functions registered in the test.
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import JsonValue

from uwh.runtime.event_types import EventType, FactSelected
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.facts import (
    Conflict,
    Derivation,
    LedgerRules,
    ReplyValue,
    RevisionChange,
    approve_observation,
    effective_facts,
    observe,
    observe_reply,
    open_conflicts,
    reject_observation,
    resolve_fact,
    usable_facts,
)
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers

NOW = datetime(2026, 6, 29, 8, 0, 0, tzinfo=UTC)
CONTEXT = EventContext("run-1", "replay", "workflow", "r" * 64, NOW, NOW)
UNDERWRITER = EventContext("run-1", "replay", "underwriter", "r" * 64, NOW, NOW)
LEAD = "L-1"


def future_roof(facts: Mapping[str, JsonValue]) -> list[Conflict]:
    year = facts.get("roof_replacement_year")
    if isinstance(year, int) and year > 2026:
        return [
            Conflict(
                validator="roof_year_future",
                fields=("roof_replacement_year",),
                values={"roof_replacement_year": year},
                question="Was the roof replaced in the year given?",
            )
        ]
    return []


def roof_before_home(facts: Mapping[str, JsonValue]) -> list[Conflict]:
    roof, built = facts.get("roof_replacement_year"), facts.get("year_built")
    if isinstance(roof, int) and isinstance(built, int) and roof < built:
        return [
            Conflict(
                validator="roof_before_home",
                fields=("roof_replacement_year", "year_built"),
                values={"roof_replacement_year": roof, "year_built": built},
                question="Which of the two years is right?",
            )
        ]
    return []


def roof_class(inputs: Mapping[str, JsonValue]) -> JsonValue:
    return "metal" if inputs["roof_material"] == "steel" else "shingle"


def steel_roof(facts: Mapping[str, JsonValue]) -> list[Conflict]:
    if facts.get("roof_material") == "steel":
        return [Conflict("steel_roof", ("roof_material",), {"roof_material": "steel"}, "Steel?")]
    return []


RULES = LedgerRules(
    system_owned_keys=frozenset({"kyc_score", "roof_class"}),
    validators=(future_roof, roof_before_home),
    derivations=(
        Derivation(
            id="roof_class_map", key="roof_class", inputs=("roof_material",), compute=roof_class
        ),
    ),
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db = open_store(str(tmp_path / "app.db"))
    add_lead(db)
    return db


def add_lead(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES (?, 'run-1', 'web', '2026-06-29T07:00:00Z', 'in_progress', 0)",
        (LEAD,),
    )


def revision(db: sqlite3.Connection) -> int:
    (value,) = db.execute("SELECT revision FROM leads WHERE lead_id = ?", (LEAD,)).fetchone()
    return int(value)


def submit(db: sqlite3.Connection, key: str, value: JsonValue, source: Any = "submitted") -> None:
    observe(db, CONTEXT, LEAD, key, value, source, {"row": "x"}, RULES)


def reply(
    db: sqlite3.Connection, key: str, value: JsonValue, *, round_closed: bool = False
) -> RevisionChange:
    return observe_reply(
        db,
        CONTEXT,
        LEAD,
        [ReplyValue(key, value, {"quote": str(value)})],
        RULES,
        round_closed=round_closed,
    )


def observations(db: sqlite3.Connection, key: str) -> list[tuple[Any, str, str]]:
    rows = db.execute(
        "SELECT value_json, source, status FROM observations WHERE key = ? ORDER BY id", (key,)
    ).fetchall()
    return [(json.loads(v), s, st) for v, s, st in rows]


def effective(db: sqlite3.Connection, key: str) -> tuple[Any, str, bool] | None:
    fact = effective_facts(db, LEAD).get(key)
    return None if fact is None else (fact.value, fact.source, fact.confirmed)


def open_kinds(db: sqlite3.Connection) -> list[tuple[str | None, str | None]]:
    return [(b.detail.item_kind, b.detail.cause) for b in open_blockers(db, LEAD)]


# ---- the ledger's two layers -----------------------------------------------------------------


def test_an_observation_writes_its_row_its_fact_observed_and_its_fact_selected(
    db: sqlite3.Connection,
) -> None:
    submit(db, "acreage", 2)
    row = db.execute(
        "SELECT lead_id, key, value_json, source, evidence_json, status, event_id FROM observations"
    ).fetchone()
    assert row[:4] == (LEAD, "acreage", "2", "submitted")
    assert json.loads(row[4]) == {"row": "x"} and row[5] == "accepted"
    types = [e.type for e in read_events(db, lead_id=LEAD)]
    assert types == [EventType.fact_observed, EventType.fact_selected]
    assert read_events(db, lead_id=LEAD)[0].id == row[6]
    assert effective_facts(db, LEAD)["acreage"].observation_id == 1


def test_the_fact_selected_events_alone_rebuild_the_effective_facts(db: sqlite3.Connection) -> None:
    submit(db, "acreage", 2)
    submit(db, "roof_material", "steel")
    reply(db, "year_built", 1990)
    reply(db, "acreage", 3)  # pending: no selection
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 5, "measured", RULES)
    rebuilt: dict[str, tuple[Any, str, bool]] = {}
    for event in read_events(db, lead_id=LEAD):
        if isinstance(event.payload, FactSelected):
            p = event.payload
            rebuilt[p.key] = (p.value, p.source, p.confirmed)
    assert rebuilt == {
        k: (f.value, f.source, f.confirmed) for k, f in effective_facts(db, LEAD).items()
    }
    assert rebuilt["acreage"] == (5, "underwriter", False)


# ---- rule 1 ----------------------------------------------------------------------------------


def test_rule_1_an_underwriter_ruling_outranks_every_other_source(db: sqlite3.Connection) -> None:
    submit(db, "acreage", 2)
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 4, "surveyed", RULES)
    assert effective(db, "acreage") == (4, "underwriter", False)
    submit(db, "acreage", 9, "fetched")
    submit(db, "acreage", 7, "assumed")
    assert reply(db, "acreage", 6).changed is False
    assert effective(db, "acreage") == (4, "underwriter", False)
    assert observations(db, "acreage")[-1] == (6, "reply", "rejected")
    assert open_kinds(db) == []


# ---- rule 2 ----------------------------------------------------------------------------------


def test_rule_2_a_reply_fills_a_missing_field_directly(db: sqlite3.Connection) -> None:
    change = reply(db, "year_built", 1990)
    assert effective(db, "year_built") == (1990, "reply", False)
    assert observations(db, "year_built") == [(1990, "reply", "accepted")]
    assert change.changed and open_kinds(db) == []


def test_rule_2_a_reply_replaces_an_assumed_value(db: sqlite3.Connection) -> None:
    submit(db, "year_built", 1980, "assumed")
    reply(db, "year_built", 1990)
    assert effective(db, "year_built") == (1990, "reply", False)
    assert observations(db, "year_built") == [
        (1980, "assumed", "accepted"),
        (1990, "reply", "accepted"),
    ]
    assert open_kinds(db) == []


# ---- rule 3 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["submitted", "fetched"])
def test_rule_3_a_reply_that_differs_from_a_submitted_or_fetched_value_is_pending_review(
    db: sqlite3.Connection, source: str
) -> None:
    submit(db, "acreage", 2, source)
    before = revision(db)
    change = reply(db, "acreage", 3)
    assert effective(db, "acreage") == (2, source, False)
    assert observations(db, "acreage")[-1] == (3, "reply", "pending_review")
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.owner) == ("underwriter_review", "underwriter")
    assert blocker.detail.item_kind == "observation"
    assert blocker.detail.observation_id == 2
    assert not change.changed and revision(db) == before


# ---- rule 4 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("present", [True, False])
def test_rule_4_a_reply_never_sets_a_system_owned_field(
    db: sqlite3.Connection, present: bool
) -> None:
    if present:
        submit(db, "kyc_score", 7)
    change = reply(db, "kyc_score", 3)
    assert effective(db, "kyc_score") == ((7, "submitted", False) if present else None)
    assert observations(db, "kyc_score")[-1] == (3, "reply", "rejected")
    assert open_kinds(db) == [] and not change.changed


# ---- rule 5 ----------------------------------------------------------------------------------


def test_rule_5_a_derived_fact_is_computed_and_recorded_with_the_observation_it_used(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_material", "steel")
    assert effective(db, "roof_class") == ("metal", "derived", False)
    derived = effective_facts(db, LEAD)["roof_class"]
    assert derived.evidence == {"derivation_id": "roof_class_map", "inputs": {"roof_material": 1}}


def test_rule_5_a_derived_fact_is_recomputed_when_its_input_changes(db: sqlite3.Connection) -> None:
    submit(db, "roof_material", "steel")
    before = revision(db)
    resolve_fact(db, UNDERWRITER, LEAD, "roof_material", "asphalt", "photo", RULES)
    assert effective(db, "roof_class") == ("shingle", "derived", False)
    assert effective_facts(db, LEAD)["roof_class"].evidence["inputs"] == {"roof_material": 3}
    assert observations(db, "roof_class") == [
        ("metal", "derived", "accepted"),
        ("shingle", "derived", "accepted"),
    ]
    assert revision(db) == before + 1  # one change of facts is one revision step


def test_rule_5_a_derived_fact_is_not_recomputed_when_nothing_it_used_changed(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_material", "steel")
    submit(db, "acreage", 2)
    assert len(observations(db, "roof_class")) == 1


def test_rule_5_an_underwriter_value_for_a_derived_key_is_not_recomputed(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_material", "steel")
    resolve_fact(db, UNDERWRITER, LEAD, "roof_class", "tile", "by sight", RULES)
    resolve_fact(db, UNDERWRITER, LEAD, "roof_material", "asphalt", "photo", RULES)
    assert effective(db, "roof_class") == ("tile", "underwriter", False)


def test_rule_5_a_derived_fact_is_usable_only_while_its_inputs_are(db: sqlite3.Connection) -> None:
    submit(db, "roof_material", "steel")
    assert "roof_class" in usable_facts(db, LEAD)
    rules = LedgerRules(validators=(steel_roof,), derivations=RULES.derivations)
    observe(db, CONTEXT, LEAD, "acreage", 1, "submitted", {}, rules)
    assert "roof_material" not in usable_facts(db, LEAD)
    assert "roof_class" not in usable_facts(db, LEAD)
    assert effective(db, "roof_class") == ("metal", "derived", False)


# ---- rule 6 ----------------------------------------------------------------------------------


def conflict_on_roof(db: sqlite3.Connection) -> None:
    submit(db, "roof_replacement_year", 2030)
    assert [c.validator for c in open_conflicts(db, LEAD)] == ["roof_year_future"]


def test_rule_6_a_restating_reply_closes_the_conflict_and_marks_the_fact_confirmed(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    before = revision(db)
    change = reply(db, "roof_replacement_year", 2030)
    assert open_conflicts(db, LEAD) == []
    assert effective(db, "roof_replacement_year") == (2030, "submitted", True)
    assert observations(db, "roof_replacement_year")[-1] == (2030, "reply", "accepted")
    closed = [
        e.payload for e in read_events(db, lead_id=LEAD) if e.type is EventType.conflict_closed
    ]
    assert [c.model_dump() for c in closed] == [
        {
            "validator": "roof_year_future",
            "fields": ["roof_replacement_year"],
            "values": {"roof_replacement_year": 2030},
            "observation_id": 2,
        }
    ]
    assert "roof_replacement_year" in usable_facts(db, LEAD)
    assert change.changed and revision(db) == before + 1


def test_rule_6_a_closed_conflict_is_not_opened_again_on_the_same_values(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    reply(db, "roof_replacement_year", 2030)
    submit(db, "acreage", 2)  # another change re-runs the validators
    assert open_conflicts(db, LEAD) == []
    opened = [e for e in read_events(db, lead_id=LEAD) if e.type is EventType.conflict_opened]
    assert len(opened) == 1


def test_rule_6_a_reply_that_changes_the_conflicting_field_follows_rule_3(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    reply(db, "roof_replacement_year", 2020)
    assert observations(db, "roof_replacement_year")[-1] == (2020, "reply", "pending_review")
    assert effective(db, "roof_replacement_year") == (2030, "submitted", False)
    assert [c.validator for c in open_conflicts(db, LEAD)] == ["roof_year_future"]
    assert open_kinds(db) == [("observation", None)]


def test_rule_6_a_reply_that_changes_either_field_of_a_conflicting_pair_follows_rule_3(
    db: sqlite3.Connection,
) -> None:
    submit(db, "year_built", 2000)
    submit(db, "roof_replacement_year", 1990)
    assert [c.validator for c in open_conflicts(db, LEAD)] == ["roof_before_home"]
    reply(db, "year_built", 1980)
    assert effective(db, "year_built") == (2000, "submitted", False)
    assert observations(db, "year_built")[-1] == (1980, "reply", "pending_review")
    assert [c.validator for c in open_conflicts(db, LEAD)] == ["roof_before_home"]


def test_rule_6_a_restated_value_of_a_pair_closes_the_conflict(db: sqlite3.Connection) -> None:
    submit(db, "year_built", 2000)
    submit(db, "roof_replacement_year", 1990)
    reply(db, "year_built", 2000)
    assert open_conflicts(db, LEAD) == []
    assert effective(db, "year_built") == (2000, "submitted", True)
    assert effective(db, "roof_replacement_year") == (1990, "submitted", False)


# ---- rule 7 ----------------------------------------------------------------------------------


def test_rule_7_a_reply_that_differs_from_an_accepted_reply_value_is_pending_review(
    db: sqlite3.Connection,
) -> None:
    reply(db, "year_built", 1990)
    reply(db, "year_built", 1985)
    assert effective(db, "year_built") == (1990, "reply", False)
    assert observations(db, "year_built") == [
        (1990, "reply", "accepted"),
        (1985, "reply", "pending_review"),
    ]
    assert open_kinds(db) == [("observation", None)]


# ---- rule 8 ----------------------------------------------------------------------------------


def test_rule_8_a_reply_value_that_trips_a_validator_is_accepted_and_opens_the_conflict(
    db: sqlite3.Connection,
) -> None:
    reply(db, "roof_replacement_year", 2031)
    assert observations(db, "roof_replacement_year") == [(2031, "reply", "accepted")]
    assert effective(db, "roof_replacement_year") == (2031, "reply", False)
    (conflict,) = open_conflicts(db, LEAD)
    assert (conflict.validator, conflict.fields, conflict.values) == (
        "roof_year_future",
        ("roof_replacement_year",),
        {"roof_replacement_year": 2031},
    )
    assert conflict.question == "Was the roof replaced in the year given?"
    opened = [
        e.payload.model_dump()
        for e in read_events(db, lead_id=LEAD)
        if e.type is EventType.conflict_opened
    ]
    assert opened == [
        {
            "validator": "roof_year_future",
            "fields": ["roof_replacement_year"],
            "values": {"roof_replacement_year": 2031},
            "question": "Was the roof replaced in the year given?",
        }
    ]
    assert "roof_replacement_year" not in usable_facts(db, LEAD)
    assert open_kinds(db) == []


def test_a_conflict_closes_when_a_new_value_no_longer_trips_the_validator(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    resolve_fact(db, UNDERWRITER, LEAD, "roof_replacement_year", 2015, "roof invoice", RULES)
    assert open_conflicts(db, LEAD) == []
    closed = [
        e.payload for e in read_events(db, lead_id=LEAD) if e.type is EventType.conflict_closed
    ]
    assert [c.observation_id for c in closed] == [None]  # type: ignore[attr-defined]
    assert "roof_replacement_year" in usable_facts(db, LEAD)


# ---- rule 9 ----------------------------------------------------------------------------------


def test_rule_9_a_reply_to_a_closed_round_is_recorded_raises_a_review_and_moves_the_revision(
    db: sqlite3.Connection,
) -> None:
    submit(db, "acreage", 2)
    before = revision(db)
    change = reply(db, "year_built", 1990, round_closed=True)
    assert observations(db, "year_built") == [(1990, "reply", "pending_review")]
    assert effective(db, "year_built") is None
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.detail.item_kind, blocker.detail.cause) == (
        "underwriter_review",
        "review",
        "late_reply",
    )
    assert change == RevisionChange(before, before + 1) and revision(db) == before + 1


def test_rule_9_a_late_reply_that_holds_no_value_still_raises_the_review(
    db: sqlite3.Connection,
) -> None:
    before = revision(db)
    change = observe_reply(db, CONTEXT, LEAD, [], RULES, round_closed=True)
    assert open_kinds(db) == [("review", "late_reply")]
    assert change.after == before + 1


def test_rule_9_a_late_reply_does_not_set_a_system_owned_field(db: sqlite3.Connection) -> None:
    reply(db, "kyc_score", 4, round_closed=True)
    assert observations(db, "kyc_score") == [(4, "reply", "rejected")]


def test_rule_9_one_late_reply_raises_one_review_whatever_the_number_of_values(
    db: sqlite3.Connection,
) -> None:
    values = [ReplyValue("year_built", 1990, {}), ReplyValue("acreage", 2, {})]
    observe_reply(db, CONTEXT, LEAD, values, RULES, round_closed=True)
    assert open_kinds(db) == [("review", "late_reply")]
    assert revision(db) == 1


# ---- rule 10 ---------------------------------------------------------------------------------


def pending_acreage(db: sqlite3.Connection) -> int:
    submit(db, "acreage", 2)
    reply(db, "acreage", 3)
    (blocker,) = open_blockers(db, LEAD)
    assert blocker.detail.observation_id is not None
    return blocker.detail.observation_id


def test_rule_10_approve_makes_a_pending_observation_the_effective_fact(
    db: sqlite3.Connection,
) -> None:
    observation_id = pending_acreage(db)
    before = revision(db)
    change = approve_observation(db, UNDERWRITER, observation_id, RULES)
    assert effective(db, "acreage") == (3, "reply", False)
    assert observations(db, "acreage")[-1] == (3, "reply", "accepted")
    assert open_blockers(db, LEAD) == []
    assert change == RevisionChange(before, before + 1)
    types = [e.type for e in read_events(db, lead_id=LEAD)]
    assert types[-2:] == [EventType.blocker_closed, EventType.fact_selected]


def test_rule_10_reject_keeps_the_existing_value(db: sqlite3.Connection) -> None:
    observation_id = pending_acreage(db)
    before = revision(db)
    reject_observation(db, UNDERWRITER, observation_id)
    assert effective(db, "acreage") == (2, "submitted", False)
    assert observations(db, "acreage")[-1] == (3, "reply", "rejected")
    assert open_blockers(db, LEAD) == []
    assert revision(db) == before


def test_rule_10_resolve_fact_records_an_underwriter_observation_for_any_fact(
    db: sqlite3.Connection,
) -> None:
    change = resolve_fact(db, UNDERWRITER, LEAD, "kyc_score", 8, "called the producer", RULES)
    assert effective(db, "kyc_score") == (8, "underwriter", False)
    row = db.execute(
        "SELECT value_json, source, status, evidence_json FROM observations WHERE key = 'kyc_score'"
    ).fetchone()
    assert row[:3] == ("8", "underwriter", "accepted")
    assert json.loads(row[3]) == {"reason": "called the producer"}
    assert change.changed


def test_rule_10_approve_and_reject_refuse_an_observation_that_is_not_awaiting_a_decision(
    db: sqlite3.Connection,
) -> None:
    observation_id = pending_acreage(db)
    approve_observation(db, UNDERWRITER, observation_id, RULES)
    for operation in (
        lambda: approve_observation(db, UNDERWRITER, observation_id, RULES),
        lambda: reject_observation(db, UNDERWRITER, observation_id),
        lambda: approve_observation(db, UNDERWRITER, 99, RULES),
    ):
        with pytest.raises(ValueError, match="awaiting"):
            operation()


def test_a_late_reply_observation_is_not_approvable_as_an_observation(
    db: sqlite3.Connection,
) -> None:
    reply(db, "year_built", 1990, round_closed=True)
    with pytest.raises(ValueError, match="awaiting"):
        approve_observation(db, UNDERWRITER, 1, RULES)
    assert effective(db, "year_built") is None


# ---- the lead revision -----------------------------------------------------------------------


def test_the_revision_moves_for_every_kind_of_change_the_rules_allow(
    db: sqlite3.Connection,
) -> None:
    steps: list[tuple[str, Any]] = [
        ("a submitted value", lambda: submit(db, "acreage", 2)),
        ("an assumed value", lambda: submit(db, "year_built", 1980, "assumed")),
        ("a reply replacing an assumed value", lambda: reply(db, "year_built", 1990)),
        ("a reply filling a missing field", lambda: reply(db, "months_unoccupied", 0)),
        (
            "an underwriter value",
            lambda: resolve_fact(db, UNDERWRITER, LEAD, "acreage", 4, "x", RULES),
        ),
        ("a value that opens a conflict", lambda: reply(db, "roof_replacement_year", 2031)),
        (
            "a restated value confirming a conflict",
            lambda: reply(db, "roof_replacement_year", 2031),
        ),
        ("a late reply", lambda: reply(db, "year_built", 1991, round_closed=True)),
    ]
    for name, step in steps:
        before = revision(db)
        step()
        assert revision(db) == before + 1, name
    submit(db, "bedrooms", 3)
    reply(db, "bedrooms", 4)
    before = revision(db)
    approve_observation(
        db, UNDERWRITER, open_blockers(db, LEAD)[-1].detail.observation_id or 0, RULES
    )
    assert revision(db) == before + 1


def test_the_revision_does_not_move_when_no_effective_fact_changed(db: sqlite3.Connection) -> None:
    submit(db, "acreage", 2)
    submit(db, "bedrooms", 3)
    before = revision(db)
    assert not reply(db, "acreage", 2).changed  # restated, no conflict open
    assert not reply(db, "bedrooms", 4).changed  # pending_review
    assert not reply(db, "kyc_score", 4).changed  # system-owned
    reject_observation(db, UNDERWRITER, open_blockers(db, LEAD)[0].detail.observation_id or 0)
    submit(db, "acreage", 9, "fetched")  # does not replace a submitted value
    assert revision(db) == before


def test_the_change_reports_the_revision_before_and_after(db: sqlite3.Connection) -> None:
    change = reply(db, "year_built", 1990)
    assert change == RevisionChange(0, 1)
    assert reply(db, "year_built", 1990) == RevisionChange(1, 1)


# ---- the property ----------------------------------------------------------------------------

operations: st.SearchStrategy[Sequence[tuple[str, int]]] = st.lists(
    st.tuples(
        st.sampled_from(["submitted", "fetched", "assumed", "reply", "underwriter"]),
        st.integers(0, 4),
    ),
    max_size=12,
)


def run(db: sqlite3.Connection, key: str, ops: Sequence[tuple[str, int]]) -> None:
    for source, value in ops:
        if source == "reply":
            reply(db, key, value)
        elif source == "underwriter":
            resolve_fact(db, UNDERWRITER, LEAD, key, value, "ruling", RULES)
        else:
            submit(db, key, value, source)


@given(ops=operations)
def test_an_underwriter_ruling_when_present_is_the_effective_value_in_any_order(
    ops: Sequence[tuple[str, int]],
) -> None:
    db = open_store(":memory:")
    add_lead(db)
    run(db, "acreage", ops)
    rulings = [value for source, value in ops if source == "underwriter"]
    if rulings:
        assert effective(db, "acreage") == (rulings[-1], "underwriter", False)


@given(ops=operations)
def test_a_reply_never_becomes_effective_for_a_system_owned_field(
    ops: Sequence[tuple[str, int]],
) -> None:
    db = open_store(":memory:")
    add_lead(db)
    run(db, "kyc_score", [(s, v) for s, v in ops if s != "underwriter"])
    fact = effective(db, "kyc_score")
    assert fact is None or fact[1] != "reply"
    assert all(
        status == "rejected"
        for _, source, status in observations(db, "kyc_score")
        if source == "reply"
    )
