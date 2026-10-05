# ABOUTME: Tests the ten source-authority rules of 7.3, the lead revision that moves when an effective fact changes, and a Hypothesis property on underwriter rulings.
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

from uwh.runtime.event_types import ConflictClosed, EventType, FactSelected
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.facts import (
    Conflict,
    Derivation,
    LedgerRules,
    ReplyValue,
    approve_observation,
    effective_facts,
    observe,
    observe_late_reply,
    observe_reply,
    open_conflicts,
    reject_late_reply_values,
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
INTENT = "I-7"


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


def reply(db: sqlite3.Connection, key: str, value: JsonValue) -> None:
    observe_reply(db, CONTEXT, LEAD, [ReplyValue(key, value, {"quote": str(value)})], RULES)


def reply_values(db: sqlite3.Connection, *pairs: tuple[str, JsonValue]) -> None:
    values = [ReplyValue(key, value, {"quote": str(value)}) for key, value in pairs]
    observe_reply(db, CONTEXT, LEAD, values, RULES)


def late_reply(db: sqlite3.Connection, intent_id: str, *pairs: tuple[str, JsonValue]) -> int:
    """Record one late reply of the given values and return the id of its review."""
    values = [ReplyValue(key, value, {}) for key, value in pairs]
    observe_late_reply(db, CONTEXT, LEAD, values, RULES, intent_id=intent_id, cause="late_reply")
    return open_blockers(db, LEAD)[-1].id


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


def validators(db: sqlite3.Connection) -> list[str]:
    return [c.validator for c in open_conflicts(db, LEAD)]


def pending_acreage(db: sqlite3.Connection) -> int:
    submit(db, "acreage", 2)
    reply(db, "acreage", 3)
    (blocker,) = open_blockers(db, LEAD)
    assert blocker.detail.observation_id is not None
    return blocker.detail.observation_id


def conflict_on_roof(db: sqlite3.Connection) -> None:
    submit(db, "roof_replacement_year", 2030)
    assert validators(db) == ["roof_year_future"]


def events_of(db: sqlite3.Connection, event_type: EventType) -> list[Any]:
    return [e.payload for e in read_events(db, lead_id=LEAD) if e.type is event_type]


def test_the_fact_selected_events_alone_rebuild_the_effective_facts(db: sqlite3.Connection) -> None:
    submit(db, "acreage", 2)
    submit(db, "roof_material", "steel")
    reply(db, "year_built", 1990)
    reply(db, "acreage", 3)  # pending: no selection
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 5, "measured", RULES)
    submit(db, "roof_replacement_year", 2030)  # opens a conflict
    reply(
        db, "roof_replacement_year", 2030
    )  # rule 6: confirms; the selected observation is the same
    resolve_fact(db, UNDERWRITER, LEAD, "roof_material", "asphalt", "photo", RULES)
    rebuilt: dict[str, tuple[Any, str, bool]] = {}
    for payload in events_of(db, EventType.fact_selected):
        assert isinstance(payload, FactSelected)
        rebuilt[payload.key] = (payload.value, payload.source, payload.confirmed)
    assert rebuilt == {
        k: (f.value, f.source, f.confirmed) for k, f in effective_facts(db, LEAD).items()
    }
    assert rebuilt["acreage"] == (5, "underwriter", False)
    assert rebuilt["roof_replacement_year"] == (2030, "submitted", True)
    assert rebuilt["roof_class"] == ("shingle", "derived", False)


# ---- rule 1: an underwriter ruling outranks every other source ----------------------------------


def test_rule_1_a_ruling_outranks_every_other_source_and_a_differing_reply_waits_for_review(
    db: sqlite3.Connection,
) -> None:
    submit(db, "acreage", 2)
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 4, "surveyed", RULES)
    assert effective(db, "acreage") == (4, "underwriter", False)
    submit(db, "acreage", 9, "fetched")
    submit(db, "acreage", 7, "assumed")
    before = revision(db)
    reply(db, "acreage", 6)
    reply(db, "acreage", 8)
    assert revision(db) == before
    assert effective(db, "acreage") == (4, "underwriter", False)
    assert [o[2] for o in observations(db, "acreage")[-2:]] == ["pending_review"] * 2
    first, second = [b.detail.observation_id or 0 for b in open_blockers(db, LEAD)]
    reject_observation(db, UNDERWRITER, first)
    assert effective(db, "acreage") == (4, "underwriter", False)
    approve_observation(db, UNDERWRITER, second, RULES)
    assert effective(db, "acreage") == (8, "reply", False)


def test_rule_1_resolve_fact_closes_the_conflicts_on_its_key_and_leaves_the_others_open(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 5, "measured", RULES)
    assert validators(db) == ["roof_year_future"]
    resolve_fact(db, UNDERWRITER, LEAD, "roof_replacement_year", 2030, "the invoice", RULES)
    assert validators(db) == []
    submit(db, "bedrooms", 2)  # another change re-runs the validators
    assert validators(db) == []
    assert len(events_of(db, EventType.conflict_opened)) == 1


def test_rule_1_resolve_fact_closes_the_conflict_of_a_pair_it_rules_one_field_of(
    db: sqlite3.Connection,
) -> None:
    submit(db, "year_built", 2000)
    submit(db, "roof_replacement_year", 1990)
    assert validators(db) == ["roof_before_home"]
    resolve_fact(db, UNDERWRITER, LEAD, "year_built", 2000, "the deed", RULES)
    assert validators(db) == []


def test_rule_1_resolve_fact_rejects_the_pending_observations_on_its_key_only(
    db: sqlite3.Connection,
) -> None:
    observation_id = pending_acreage(db)
    submit(db, "bedrooms", 3)
    reply(db, "bedrooms", 4)  # pending on another key
    resolve_fact(db, UNDERWRITER, LEAD, "acreage", 5, "measured", RULES)
    assert observations(db, "acreage")[1] == (3, "reply", "rejected")
    assert [(b.detail.item_kind, b.detail.observation_id) for b in open_blockers(db, LEAD)] == [
        ("observation", 4)
    ]
    with pytest.raises(ValueError, match="awaiting"):
        approve_observation(db, UNDERWRITER, observation_id, RULES)
    assert effective(db, "acreage") == (5, "underwriter", False)


# ---- rule 2: a reply fills a missing or assumed field -------------------------------------------


@pytest.mark.parametrize(
    ("assumed", "reply_value"), [(None, 1990), (1980, 1990), (1990, 1990)], ids=str
)
def test_rule_2_a_reply_fills_a_missing_field_and_replaces_an_assumed_value(
    db: sqlite3.Connection, assumed: int | None, reply_value: int
) -> None:
    if assumed is not None:
        submit(db, "year_built", assumed, "assumed")
    before = revision(db)

    reply(db, "year_built", reply_value)

    assert effective(db, "year_built") == (reply_value, "reply", False)
    assert observations(db, "year_built")[-1] == (reply_value, "reply", "accepted")
    assert open_kinds(db) == []
    assert revision(db) == before + 1


# ---- rule 3: a reply that differs from a submitted or fetched value waits for review ------------


@pytest.mark.parametrize("source", ["submitted", "fetched"])
def test_rule_3_a_reply_that_differs_from_a_submitted_or_fetched_value_is_pending_review(
    db: sqlite3.Connection, source: str
) -> None:
    submit(db, "acreage", 2, source)
    before = revision(db)
    reply(db, "acreage", 3)
    assert effective(db, "acreage") == (2, source, False)
    assert observations(db, "acreage")[-1] == (3, "reply", "pending_review")
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.owner) == ("underwriter_review", "underwriter")
    assert (blocker.detail.item_kind, blocker.detail.observation_id) == ("observation", 2)
    assert revision(db) == before


# ---- rule 4: a reply never sets a system-owned field --------------------------------------------


@pytest.mark.parametrize("present", [True, False])
def test_rule_4_a_reply_never_sets_a_system_owned_field(
    db: sqlite3.Connection, present: bool
) -> None:
    if present:
        submit(db, "kyc_score", 7)
    before = revision(db)
    reply(db, "kyc_score", 3)
    assert effective(db, "kyc_score") == ((7, "submitted", False) if present else None)
    assert observations(db, "kyc_score")[-1] == (3, "reply", "rejected")
    assert open_kinds(db) == [] and revision(db) == before


@pytest.mark.parametrize(
    ("existing", "incoming", "expected"),
    [
        ("assumed", "submitted", "submitted"),
        ("assumed", "fetched", "fetched"),
        ("submitted", "assumed", "submitted"),
        ("fetched", "assumed", "fetched"),
        ("reply", "assumed", "reply"),
        ("underwriter", "assumed", "underwriter"),
    ],
)
def test_an_assumed_value_never_replaces_an_existing_one_and_any_real_value_replaces_it(
    db: sqlite3.Connection, existing: str, incoming: str, expected: str
) -> None:
    if existing == "reply":
        reply(db, "acreage", 2)
    elif existing == "underwriter":
        resolve_fact(db, UNDERWRITER, LEAD, "acreage", 2, "measured", RULES)
    else:
        submit(db, "acreage", 2, existing)
    submit(db, "acreage", 3, incoming)
    value = 3 if expected == incoming else 2
    assert effective(db, "acreage") == (value, expected, False)


# ---- rule 5: a derived fact follows its inputs ---------------------------------------------------


def test_rule_5_a_derived_fact_is_computed_with_its_input_and_recomputed_when_it_changes(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_material", "steel")
    assert effective(db, "roof_class") == ("metal", "derived", False)
    derived = effective_facts(db, LEAD)["roof_class"]
    assert derived.evidence == {"derivation_id": "roof_class_map", "inputs": {"roof_material": 1}}
    submit(db, "acreage", 2)
    assert len(observations(db, "roof_class")) == 1  # nothing it used changed
    before = revision(db)

    resolve_fact(db, UNDERWRITER, LEAD, "roof_material", "asphalt", "photo", RULES)

    assert effective(db, "roof_class") == ("shingle", "derived", False)
    assert effective_facts(db, LEAD)["roof_class"].evidence["inputs"] == {"roof_material": 4}
    assert revision(db) == before + 1  # one change of facts is one revision step


def test_rule_5_a_derivation_outranks_a_submitted_value_but_not_an_underwriters(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_class", "tile")
    submit(db, "acreage", 2)
    assert effective(db, "roof_class") == ("tile", "submitted", False)  # its input is missing
    submit(db, "roof_material", "steel")
    assert effective(db, "roof_class") == ("metal", "derived", False)
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


# ---- rule 6: a restating reply confirms a conflicting value -------------------------------------


def test_rule_6_a_restating_reply_closes_the_conflict_and_confirms_the_fact(
    db: sqlite3.Connection,
) -> None:
    conflict_on_roof(db)
    before = revision(db)
    reply(db, "roof_replacement_year", 2030)
    assert validators(db) == []
    assert effective(db, "roof_replacement_year") == (2030, "submitted", True)
    assert observations(db, "roof_replacement_year")[-1] == (2030, "reply", "accepted")
    (closed,) = events_of(db, EventType.conflict_closed)
    assert isinstance(closed, ConflictClosed)
    assert (closed.validator, closed.observation_id) == ("roof_year_future", 2)
    assert "roof_replacement_year" in usable_facts(db, LEAD)
    assert revision(db) == before + 1
    submit(db, "acreage", 2)  # another change re-runs the validators
    assert validators(db) == []
    assert len(events_of(db, EventType.conflict_opened)) == 1


def test_rule_6_a_reply_that_changes_a_conflicting_field_follows_rule_3(
    db: sqlite3.Connection,
) -> None:
    submit(db, "year_built", 2000)
    submit(db, "roof_replacement_year", 1990)
    assert validators(db) == ["roof_before_home"]
    reply(db, "year_built", 1980)
    assert effective(db, "year_built") == (2000, "submitted", False)
    assert observations(db, "year_built")[-1] == (1980, "reply", "pending_review")
    assert validators(db) == ["roof_before_home"]
    reply(db, "year_built", 2000)  # a restated value of the pair closes the conflict
    assert validators(db) == []
    assert effective(db, "year_built") == (2000, "submitted", True)
    assert effective(db, "roof_replacement_year") == (1990, "submitted", False)


@pytest.mark.parametrize("restated_first", [True, False])
def test_rule_6_one_reply_cannot_confirm_a_conflict_and_change_the_other_field_of_its_pair(
    db: sqlite3.Connection, restated_first: bool
) -> None:
    submit(db, "year_built", 2000)
    submit(db, "roof_replacement_year", 1990)
    pairs: list[tuple[str, JsonValue]] = [("year_built", 2000), ("roof_replacement_year", 1985)]
    reply_values(db, *(pairs if restated_first else pairs[::-1]))
    assert validators(db) == ["roof_before_home"]
    assert observations(db, "year_built")[-1] == (2000, "reply", "accepted")
    assert observations(db, "roof_replacement_year")[-1] == (1985, "reply", "pending_review")
    assert effective(db, "year_built") == (2000, "submitted", False)
    assert effective(db, "roof_replacement_year") == (1990, "submitted", False)
    assert open_kinds(db) == [("observation", None)]


# ---- rule 7: a reply that differs from an accepted reply waits for review -----------------------


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


# ---- rule 8: a value that trips a validator opens a conflict ------------------------------------


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
    assert "roof_replacement_year" not in usable_facts(db, LEAD)
    assert open_kinds(db) == []


def test_rule_8_a_conflict_closes_when_a_new_value_no_longer_trips_the_validator(
    db: sqlite3.Connection,
) -> None:
    submit(db, "roof_replacement_year", 2030, "assumed")
    assert validators(db) == ["roof_year_future"]
    submit(db, "roof_replacement_year", 2015, "fetched")
    assert validators(db) == []
    assert [c.observation_id for c in events_of(db, EventType.conflict_closed)] == [None]
    assert "roof_replacement_year" in usable_facts(db, LEAD)


# ---- rule 9: a reply to a closed round raises a review ------------------------------------------


def test_rule_9_a_reply_to_a_closed_round_is_recorded_raises_one_review_and_moves_the_revision(
    db: sqlite3.Connection,
) -> None:
    submit(db, "acreage", 2)
    before = revision(db)
    late_reply(db, INTENT, ("year_built", 1990), ("kyc_score", 4))
    assert observations(db, "year_built") == [(1990, "reply", "pending_review")]
    assert observations(db, "kyc_score") == [(4, "reply", "rejected")]
    assert effective(db, "year_built") is None
    (blocker,) = open_blockers(db, LEAD)
    assert (blocker.kind, blocker.detail.item_kind, blocker.detail.cause) == (
        "underwriter_review",
        "review",
        "late_reply",
    )
    assert blocker.detail.intent_id == INTENT
    assert revision(db) == before + 1


def test_rule_9_acknowledging_a_late_reply_rejects_its_values_and_no_others(
    db: sqlite3.Connection,
) -> None:
    pending_acreage(db)  # a rule 3 value awaits its own review
    first = late_reply(db, "I-1", ("year_built", 1990), ("stories", 2))
    second = late_reply(db, "I-2", ("bedrooms", 3))
    reject_late_reply_values(db, first)
    assert observations(db, "year_built") == [(1990, "reply", "rejected")]
    assert observations(db, "stories") == [(2, "reply", "rejected")]
    assert observations(db, "bedrooms") == [(3, "reply", "pending_review")]
    assert observations(db, "acreage")[-1] == (3, "reply", "pending_review")
    assert effective(db, "year_built") is None
    reject_late_reply_values(db, second)
    assert observations(db, "bedrooms") == [(3, "reply", "rejected")]
    assert observations(db, "acreage")[-1] == (3, "reply", "pending_review")


def test_rule_9_a_late_reply_value_a_ruling_already_rejected_stays_rejected(
    db: sqlite3.Connection,
) -> None:
    review = late_reply(db, "I-1", ("year_built", 1990), ("stories", 2))
    resolve_fact(db, UNDERWRITER, LEAD, "year_built", 1985, "the deed", RULES)
    reject_late_reply_values(db, review)
    assert observations(db, "year_built") == [
        (1990, "reply", "rejected"),
        (1985, "underwriter", "accepted"),
    ]
    assert observations(db, "stories") == [(2, "reply", "rejected")]
    assert effective(db, "year_built") == (1985, "underwriter", False)


# ---- rule 10: the underwriter settles a pending observation -------------------------------------


def test_rule_10_approve_makes_a_pending_observation_the_effective_fact(
    db: sqlite3.Connection,
) -> None:
    observation_id = pending_acreage(db)
    before = revision(db)
    approve_observation(db, UNDERWRITER, observation_id, RULES)
    assert effective(db, "acreage") == (3, "reply", False)
    assert observations(db, "acreage")[-1] == (3, "reply", "accepted")
    assert open_blockers(db, LEAD) == []
    assert revision(db) == before + 1
    types = [e.type for e in read_events(db, lead_id=LEAD)]
    assert types[-2:] == [EventType.blocker_closed, EventType.fact_selected]
    with pytest.raises(ValueError, match="awaiting"):
        approve_observation(db, UNDERWRITER, observation_id, RULES)


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
    resolve_fact(db, UNDERWRITER, LEAD, "kyc_score", 8, "called the producer", RULES)
    assert effective(db, "kyc_score") == (8, "underwriter", False)
    row = db.execute(
        "SELECT value_json, source, status, evidence_json FROM observations WHERE key = 'kyc_score'"
    ).fetchone()
    assert row[:3] == ("8", "underwriter", "accepted")
    assert json.loads(row[3]) == {"reason": "called the producer"}


# ---- the lead revision ---------------------------------------------------------------------------


def test_the_revision_moves_once_for_every_kind_of_change_the_rules_allow(
    db: sqlite3.Connection,
) -> None:
    steps: list[tuple[str, Any]] = [
        ("a submitted value", lambda: submit(db, "acreage", 2)),
        ("an assumed value", lambda: submit(db, "year_built", 1980, "assumed")),
        ("a reply replacing an assumed value", lambda: reply(db, "year_built", 1990)),
        (
            "an underwriter value",
            lambda: resolve_fact(db, UNDERWRITER, LEAD, "acreage", 4, "x", RULES),
        ),
        ("a value that opens a conflict", lambda: reply(db, "roof_replacement_year", 2031)),
        (
            "a restated value confirming a conflict",
            lambda: reply(db, "roof_replacement_year", 2031),
        ),
        ("a late reply", lambda: late_reply(db, INTENT, ("year_built", 1991))),
    ]
    for name, step in steps:
        before = revision(db)
        step()
        assert revision(db) == before + 1, name


def test_the_revision_does_not_move_when_no_effective_fact_changed(db: sqlite3.Connection) -> None:
    submit(db, "acreage", 2)
    submit(db, "bedrooms", 3)
    before = revision(db)
    reply(db, "acreage", 2)  # restated, no conflict open
    reply(db, "bedrooms", 4)  # pending_review
    reply(db, "kyc_score", 4)  # system-owned
    reject_observation(db, UNDERWRITER, open_blockers(db, LEAD)[0].detail.observation_id or 0)
    submit(db, "acreage", 9, "fetched")  # does not replace a submitted value
    assert revision(db) == before


# ---- the property --------------------------------------------------------------------------------

operations: st.SearchStrategy[Sequence[tuple[str, int]]] = st.lists(
    st.tuples(
        st.sampled_from(["submitted", "fetched", "assumed", "reply", "underwriter"]),
        st.integers(0, 4),
    ),
    max_size=12,
)


@given(ops=operations)
def test_an_underwriter_ruling_when_present_is_the_effective_value_in_any_order(
    ops: Sequence[tuple[str, int]],
) -> None:
    db = open_store(":memory:")
    add_lead(db)
    for source, value in ops:
        if source == "reply":
            reply(db, "acreage", value)
        elif source == "underwriter":
            resolve_fact(db, UNDERWRITER, LEAD, "acreage", value, "ruling", RULES)
        else:
            submit(db, "acreage", value, source)
    rulings = [value for source, value in ops if source == "underwriter"]
    if rulings:
        assert effective(db, "acreage") == (rulings[-1], "underwriter", False)
