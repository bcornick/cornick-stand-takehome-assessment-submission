# ABOUTME: Grades the system's first pass against Stand's answer key: the generator's debug history of a seed, regenerated in process, is checked record by record against each lead's asks.
# ABOUTME: The rules by record kind are those of architecture 13.2; each record ends as agreeing, exempt, an allowed disagreement of a named class, or disagreeing.
import copy
import json
import re
import sqlite3
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import JsonValue

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim-harness"))
# The grader runs Stand's generator in process; the path above makes it importable.
import leadgen  # noqa: E402
from leadgen import generator  # noqa: E402

from uwh.rules.confirmations import confirmation_asks  # noqa: E402
from uwh.rules.registry import Registry  # noqa: E402
from uwh.runtime.event_types import EventType, TriageCompleted  # noqa: E402
from uwh.runtime.events import read_events  # noqa: E402
from uwh.runtime.facts import open_conflicts, usable_facts  # noqa: E402
from uwh.rules.models import ActionPlan  # noqa: E402

CONFIG_PATH = Path(leadgen.__file__).with_name("generator_config.yaml")
# The queue the app reads: POST /queue?count=10&seed=<seed> with the service's default difficulty.
COUNT = 10
DIFFICULTY = "mixed"

# The registry fields whose conditions the registry does not state; section 9.2 fixes them.
INTERPRETED_FIELDS = frozenset({"listed_for_sale", "is_gated_community", "opening_protection"})
# Record kinds whose field is never asked. `archetype_null` joins them for a system-owned field.
NEVER_ASK_KINDS = frozenset({"missing_bind_only", "missing_system_owned", "missing_derived"})
ASK_KINDS = frozenset({"missing_required", "missing_required_conditional", "archetype_null"})
CONDITION = re.compile(r"^(\w+) (=|!=|in) (.+)$")


class Verdict(StrEnum):
    agrees = "agrees"
    exempt_proposed_decline = "exempt_proposed_decline"
    exempt_blocked = "exempt_blocked"
    allowed_inactive_condition = "allowed_inactive_condition"
    allowed_set_by_conflict = "allowed_set_by_conflict"
    disagrees = "disagrees"


@dataclass(frozen=True)
class Record:
    lead_id: str
    kind: str
    field: str
    detail: str


@dataclass(frozen=True)
class LeadState:
    """What the grader reads of one lead after the first pass."""

    asked: frozenset[str]  # fields of a field request or follow-on question, sent or drafted
    confirmed: frozenset[str]  # fields a sent or drafted confirmation, or an open choice, covers
    facts: Mapping[str, JsonValue]  # the usable facts
    blocked: frozenset[str]  # fields whose resolution is blocked
    proposed_decline: bool


@dataclass(frozen=True)
class Judgement:
    record: Record
    verdict: Verdict
    reason: str
    by_interpretation: bool  # decided by the 9.2 table, not by a condition the registry states


def regenerate_history(seed: int) -> list[Record]:
    """The records of the debug history of `seed`'s queue, from Stand's unmodified generator."""
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    leads = generator.generate_queue(seed, COUNT, DIFFICULTY, copy.deepcopy(config))
    return [
        Record(lead["lead_id"], touch["kind"], touch["field"], touch["detail"])
        for lead in leads
        for touch in lead["debug"]["perturbations"]
    ]


def read_lead_state(db: sqlite3.Connection, lead_id: str) -> LeadState:
    """The state of `lead_id` in the application database after the first pass."""
    ask_ids = {
        ask_id
        for (ask_ids_json,) in db.execute(
            "SELECT ask_ids_json FROM intents WHERE lead_id = ?", (lead_id,)
        )
        for ask_id in json.loads(ask_ids_json)
    }
    plan_json, plan_hash = db.execute(
        "SELECT plan_json, plan_hash FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    assert plan_hash is not None, f"{lead_id} has no plan"
    plan = ActionPlan.model_validate_json(plan_json)
    triage = [
        e.payload for e in read_events(db, lead_id=lead_id) if e.type == EventType.triage_completed
    ][-1]
    assert isinstance(triage, TriageCompleted)
    confirmations = confirmation_asks([c.opened for c in open_conflicts(db, lead_id)])
    return LeadState(
        asked=frozenset(ask_ids - {ask.ask_id for ask in confirmations}),
        confirmed=frozenset(
            name for ask in confirmations if ask.ask_id in ask_ids for name in ask.fields
        )
        | frozenset(name for choice in plan.open_choices for name in choice.show),
        facts={key: fact.value for key, fact in usable_facts(db, lead_id).items()},
        blocked=frozenset(
            name
            for name, entry in triage.fields.items()
            if isinstance(entry, dict) and entry["resolution"] == "blocked"
        ),
        proposed_decline=plan.proposed_decline,
    )


def _text(value: JsonValue) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def _condition(field: str, prose: str | None, facts: Mapping[str, JsonValue]) -> bool | None:
    """Whether `field`'s condition holds on `facts`: True, False, or None when a controlling field is unknown.

    A field with no registry condition follows the 9.2 table.
    """
    if field == "opening_protection":
        return False
    if field == "listed_for_sale":
        return True
    if field == "is_gated_community":
        pool, security = facts.get("pool_type"), facts.get("pool_security")
        if (pool is not None and pool != "Inground") or security == "Fenced":
            return False
        return True if pool == "Inground" and security is not None else None
    assert prose is not None, f"{field} has no condition"
    match = CONDITION.match(prose)
    assert match is not None, f"the condition {prose!r} has no known form"
    controlling, operator, operand = match.groups()
    if controlling not in facts:
        return None
    value = _text(facts[controlling])
    if operator == "in":
        return value in [part.strip() for part in operand.strip("()").split(",")]
    return (value == operand) == (operator == "=")


def _judge(
    record: Record,
    later_kinds: set[tuple[str, str]],
    state: LeadState,
    registry: Registry,
) -> tuple[Verdict, str]:
    field = registry[record.field]
    asked = record.field in state.asked
    if record.kind not in ASK_KINDS | NEVER_ASK_KINDS | {"conflict", "archetype_set"}:
        raise ValueError(f"the answer key has no rule for the record kind {record.kind}")
    if record.kind == "archetype_set":
        return Verdict.agrees, "no expectation"
    if record.kind == "conflict":
        if state.proposed_decline:
            return Verdict.exempt_proposed_decline, "the decline review stands for the confirmation"
        if record.field in state.confirmed:
            return Verdict.agrees, "a confirmation or underwriter item covers it"
        return Verdict.disagrees, "no confirmation or underwriter item covers the conflict"
    if record.kind in NEVER_ASK_KINDS or not field.producer_editable:
        if asked:
            return Verdict.disagrees, "a field the system owns or defers was asked"
        return Verdict.agrees, "not asked"
    # The key expects an ask, unless a conflict injection gave the field a value, or its
    # condition is inactive.
    if (record.field, "conflict") in later_kinds:
        if asked:
            return Verdict.agrees, "asked"
        return Verdict.allowed_set_by_conflict, "a conflict injection set the field again"
    if record.kind == "missing_required_conditional":
        holds = _condition(record.field, field.required_when, state.facts)
        if holds is False:
            if asked:
                return Verdict.disagrees, "a field whose condition is inactive was asked"
            return Verdict.allowed_inactive_condition, "the condition is inactive"
    if state.proposed_decline:
        return Verdict.exempt_proposed_decline, "the lead is a proposed decline"
    if asked:
        return Verdict.agrees, "asked"
    if record.field in state.blocked:
        return Verdict.exempt_blocked, "the field's resolution is blocked"
    return Verdict.disagrees, "an ask is expected and none was made"


def grade(
    history: list[Record], states: Mapping[str, LeadState], registry: Registry
) -> list[Judgement]:
    """One judgement per record of `history`; `states` holds each lead's state by lead id."""
    judgements: list[Judgement] = []
    for index, record in enumerate(history):
        later = {(r.field, r.kind) for r in history[index + 1 :] if r.lead_id == record.lead_id}
        verdict, reason = _judge(record, later, states[record.lead_id], registry)
        judgements.append(
            Judgement(
                record=record,
                verdict=verdict,
                reason=reason,
                by_interpretation=record.field in INTERPRETED_FIELDS
                and record.kind == "missing_required_conditional",
            )
        )
    return judgements


def summary(judgements: list[Judgement]) -> str:
    """The counts of each verdict, those decided by the 9.2 table, and every disagreement."""
    counts = Counter(j.verdict for j in judgements)
    lines = [f"{verdict.value}: {counts[verdict]}" for verdict in Verdict]
    lines.append(f"decided by the 9.2 table: {sum(j.by_interpretation for j in judgements)}")
    lines += [
        f"DISAGREES {j.record.lead_id} {j.record.kind} {j.record.field}: {j.reason}"
        for j in judgements
        if j.verdict == Verdict.disagrees
    ]
    return "\n".join(lines)
