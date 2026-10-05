# ABOUTME: The workflow steps of a lead's pass: each reads the lead's facts from the ledger, runs a skill on them and writes what the skill decided as events, observations, the plan and the draft.
# ABOUTME: The order is `WORKFLOW_STEP_ORDER`; the registry, providers and ledger rules a step needs arrive in `build_steps`, which is why the steps are built when the app starts.
import json
import sqlite3
from collections.abc import Callable
from functools import partial
from pathlib import Path

from pydantic import JsonValue

import uwh.skills
from uwh.providers.stand_in import StandInProviders
from uwh.rules.data_files import read_yaml
from uwh.rules.models import ActionPlan, FieldTriage, NotBuilt
from uwh.rules.registry import Registry
from uwh.runtime.event_types import (
    ConflictOpened,
    EventType,
    PlanBuilt,
    ProviderCalled,
    TriageCompleted,
)
from uwh.runtime.events import EventContext, append_event, format_timestamp
from uwh.runtime.facts import (
    LedgerRules,
    effective_facts,
    observe,
    open_conflicts,
    submitted_values,
    usable_facts,
)
from uwh.runtime.hashing import hash_json, plan_hash
from uwh.runtime.policy import manifest_refusal
from uwh.runtime.send import create_draft, replace_stale_drafts
from uwh.runtime.waits import open_blockers
from uwh.runtime.workflow import Step
from uwh.skills.build_quote_packet import skill as build_quote_packet
from uwh.skills.evaluate_playbook import skill as evaluate_playbook
from uwh.skills.plan_asks import skill as plan_asks
from uwh.skills.render_message import skill as render_message
from uwh.skills.resolve_data import skill as resolve_data
from uwh.skills.triage_fields import skill as triage_fields
from uwh.skills.manifest import load_manifest
from uwh.skills.vertical import WORKFLOW_STEP_ORDER

_SKILLS_ROOT = Path(uwh.skills.__file__).parent


def lead_label(db: sqlite3.Connection, lead_id: str) -> str:
    """The property address, or the lead id when the lead has none."""
    address = effective_facts(db, lead_id).get("street_address")
    return address.value if address is not None and isinstance(address.value, str) else lead_id


def _usable_values(db: sqlite3.Connection, lead_id: str) -> dict[str, JsonValue]:
    return {key: fact.value for key, fact in usable_facts(db, lead_id).items()}


def _triage(db: sqlite3.Connection, lead_id: str, registry: Registry) -> dict[str, FieldTriage]:
    """The triage of the lead's facts as they are now."""
    conflicting = [name for conflict in open_conflicts(db, lead_id) for name in conflict.fields]
    return triage_fields.run(
        triage_fields.TriageFieldsInput(
            registry=registry, facts=_usable_values(db, lead_id), conflicting_fields=conflicting
        )
    ).fields


def _triage_step(
    registry: Registry, db: sqlite3.Connection, context: EventContext, lead_id: str
) -> None:
    triage = _triage(db, lead_id, registry)
    append_event(
        db,
        context,
        EventType.triage_completed,
        TriageCompleted(fields={name: t.model_dump(mode="json") for name, t in triage.items()}),
        lead_id=lead_id,
    )


def _resolve_step(
    registry: Registry,
    providers: StandInProviders,
    rules: LedgerRules,
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
) -> None:
    """Look up each field triage says to fetch, record the lookup, and observe what the skill resolves.
    Raises ValueError when the manifest of resolve_data does not declare `fetch_data` (7.4)."""
    refusal = manifest_refusal(load_manifest(_SKILLS_ROOT / "resolve_data"), "fetch_data")
    if refusal is not None:
        raise ValueError(refusal)
    facts = _usable_values(db, lead_id)
    submitted = submitted_values(db, lead_id)
    fingerprint = hash_json({name: submitted.get(name) for name in registry})
    results = {}
    for field, triage in _triage(db, lead_id, registry).items():
        if triage.resolution == "fetch":
            result = providers.lookup(
                field, lead_id, fingerprint, facts, format_timestamp(context.real_ts)
            )
            append_event(
                db,
                context,
                EventType.provider_called,
                ProviderCalled(key=field, result=result),
                lead_id=lead_id,
            )
            results[field] = result
    resolved = resolve_data.run(resolve_data.ResolveDataInput(provider_results=results))
    for fact in resolved.facts:
        observe(db, context, lead_id, fact.key, fact.value, fact.source, fact.evidence, rules)


def _evaluate_step(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
    """Build the action plan and store it on the lead when it differs from the stored one."""
    plan = evaluate_playbook.run(
        evaluate_playbook.EvaluatePlaybookInput(facts=_usable_values(db, lead_id))
    )
    dumped = plan.model_dump(mode="json")
    digest = plan_hash(dumped)
    (stored,) = db.execute("SELECT plan_hash FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if stored == digest:
        return
    db.execute(
        "UPDATE leads SET plan_json = ?, plan_hash = ? WHERE lead_id = ?",
        (json.dumps(dumped), digest, lead_id),
    )
    append_event(
        db, context, EventType.plan_built, PlanBuilt(plan=dumped, plan_hash=digest), lead_id=lead_id
    )


def _recipient(db: sqlite3.Connection, lead_id: str, facts: dict[str, JsonValue]) -> str:
    """10.3: the directory's address for an agent portal or a broker, the applicant's own address for a web lead."""
    (source,) = db.execute("SELECT source FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    address = (
        facts.get("owner_email")
        if source == "direct_web"
        else read_yaml("contacts.yaml").get(source)
    )
    if not isinstance(address, str):
        raise NotBuilt(
            f"lead {lead_id} has no contact route, and the review that resolves it is not built"
        )
    return address


def _unsettled_intent(db: sqlite3.Connection, lead_id: str) -> bool:
    """A message of the lead that is a draft, being sent, or sent with the result in doubt."""
    return (
        db.execute(
            "SELECT 1 FROM intents WHERE lead_id = ? AND state IN ('draft', 'dispatching', 'unknown')",
            (lead_id,),
        ).fetchone()
        is not None
    )


def _request_in_flight(db: sqlite3.Connection, lead_id: str) -> bool:
    """One request per lead at a time (10.1): an unsettled message, or a sent request still waiting
    for its reply."""
    return _unsettled_intent(db, lead_id) or any(
        blocker.kind == "producer_reply" for blocker in open_blockers(db, lead_id)
    )


def _planned_asks(
    registry: Registry, db: sqlite3.Connection, lead_id: str
) -> plan_asks.PlanAsksOutput:
    conflicts = [
        ConflictOpened(
            validator=c.validator, fields=list(c.fields), values=c.values, question=c.question
        )
        for c in open_conflicts(db, lead_id)
    ]
    return plan_asks.run(
        plan_asks.PlanAsksInput(
            registry=registry, triage=_triage(db, lead_id, registry), conflicts=conflicts
        )
    )


def _ask_producer_step(
    registry: Registry, db: sqlite3.Connection, context: EventContext, lead_id: str
) -> None:
    """Plan the asks, render them and draft the request. A draft built at an older revision is replaced;
    a lead with a request in flight, or nothing to ask, gets no new draft."""
    planned = _planned_asks(registry, db, lead_id)
    replace_stale_drafts(db, context, lead_id)
    if not planned.asks or _request_in_flight(db, lead_id):
        return
    facts = {key: fact.value for key, fact in effective_facts(db, lead_id).items()}
    rendered = render_message.run(
        render_message.RenderMessageInput(
            registry=registry,
            lead_label=lead_label(db, lead_id),
            asks=planned.asks,
        )
    )
    create_draft(
        db,
        context,
        load_manifest(_SKILLS_ROOT / "render_message"),
        lead_id,
        planned.message_class,
        _recipient(db, lead_id, facts),
        rendered.subject,
        rendered.body,
        rendered.ask_ids,
    )


# The coverages a quote packet shows as submitted.
_COVERAGE_FIELDS = ("coverage_a", "coverage_e", "coverage_f")


def _quote_packet_step(
    registry: Registry, db: sqlite3.Connection, context: EventContext, lead_id: str
) -> None:
    """Draft the quote packet when the plan holds no decline and nothing open, no ask remains, and the
    lead holds no blocker and no unsettled message (8). The draft waits for the underwriter."""
    (plan_json,) = db.execute(
        "SELECT plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    plan = ActionPlan.model_validate_json(plan_json)
    if (
        not build_quote_packet.is_ready(plan)
        or _planned_asks(registry, db, lead_id).asks
        or open_blockers(db, lead_id)
        or _unsettled_intent(db, lead_id)
    ):
        return
    facts = effective_facts(db, lead_id)
    packet = build_quote_packet.run(
        build_quote_packet.BuildQuotePacketInput(
            lead_label=lead_label(db, lead_id),
            plan=plan,
            coverages={
                name: build_quote_packet.Coverage(
                    label=registry[name].label, value=facts[name].value
                )
                for name in _COVERAGE_FIELDS
                if name in facts
            },
        )
    )
    create_draft(
        db,
        context,
        load_manifest(_SKILLS_ROOT / "build_quote_packet"),
        lead_id,
        "quote_packet",
        _recipient(db, lead_id, {key: fact.value for key, fact in facts.items()}),
        packet.subject,
        packet.body,
        [],
    )


def build_steps(
    registry: Registry, providers: StandInProviders, rules: LedgerRules
) -> tuple[Step, ...]:
    """The workflow's steps in `WORKFLOW_STEP_ORDER`."""
    runners: dict[str, Callable[[sqlite3.Connection, EventContext, str], None]] = {
        "triage_fields": partial(_triage_step, registry),
        "resolve_data": partial(_resolve_step, registry, providers, rules),
        "evaluate_playbook": _evaluate_step,
        "ask_producer": partial(_ask_producer_step, registry),
        "build_quote_packet": partial(_quote_packet_step, registry),
    }
    return tuple(Step(name, runners[name]) for name in WORKFLOW_STEP_ORDER)
