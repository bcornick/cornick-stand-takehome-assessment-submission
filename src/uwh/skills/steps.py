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
from uwh.rules.models import ActionPlan, Ask, FieldTriage
from uwh.rules.registry import Registry
from uwh.runtime.event_types import (
    BlockerDetail,
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
from uwh.runtime.rulings import rulings_in_force
from uwh.runtime.send import create_draft, replace_stale_drafts, rounds_used
from uwh.runtime.waits import Blocker, close_blocker, open_blocker, open_blockers
from uwh.runtime.workflow import Step, stored_plan
from uwh.skills.build_quote_packet import skill as build_quote_packet
from uwh.skills.evaluate_playbook import skill as evaluate_playbook
from uwh.skills.plan_asks import skill as plan_asks
from uwh.skills.render_message import skill as render_message
from uwh.skills.resolve_data import skill as resolve_data
from uwh.skills.triage_fields import skill as triage_fields
from uwh.skills.manifest import load_manifest
from uwh.skills.vertical import MAX_REQUEST_ROUNDS, WORKFLOW_STEP_ORDER

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
    """Record the triage of the lead's facts as they are now. The latest `triage_completed` of a lead
    is its current triage."""
    triage = _triage(db, lead_id, registry)
    append_event(
        db,
        context,
        EventType.triage_completed,
        TriageCompleted(fields={name: t.model_dump(mode="json") for name, t in triage.items()}),
        lead_id=lead_id,
    )


def _pass_triage(db: sqlite3.Connection, lead_id: str) -> dict[str, FieldTriage]:
    """The triage the pass's first step recorded, before anything is fetched: it says what to fetch."""
    (payload,) = db.execute(
        "SELECT payload_json FROM events WHERE lead_id = ? AND type = ? ORDER BY id DESC LIMIT 1",
        (lead_id, EventType.triage_completed.value),
    ).fetchone()
    return {
        name: FieldTriage.model_validate(triage)
        for name, triage in TriageCompleted.model_validate_json(payload).fields.items()
    }


def _resolve_step(
    registry: Registry,
    providers: StandInProviders,
    rules: LedgerRules,
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
) -> None:
    """Look up each field the pass's triage says to fetch, record the lookup, observe what the skill
    resolves and record the triage again, now that the fetched facts are in. Raises ValueError when the manifest of resolve_data does not declare `fetch_data` (7.4)."""
    refusal = manifest_refusal(load_manifest(_SKILLS_ROOT / "resolve_data"), "fetch_data")
    if refusal is not None:
        raise ValueError(refusal)
    facts = _usable_values(db, lead_id)
    submitted = submitted_values(db, lead_id)
    fingerprint = hash_json({name: submitted.get(name) for name in registry})
    results = {}
    for field, triage in _pass_triage(db, lead_id).items():
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
    _triage_step(registry, db, context, lead_id)


def _sync_underwriter_question(
    db: sqlite3.Connection, context: EventContext, lead_id: str, plan: ActionPlan
) -> None:
    """One question card holds every open choice of the lead (9.6 rule 6). The card is replaced when
    the open choices change and closed when none is open."""
    choice_ids = [choice.choice_id for choice in plan.open_choices]
    card = next((b for b in open_blockers(db, lead_id) if b.kind == "underwriter_question"), None)
    if card is not None and card.detail.choice_ids == choice_ids:
        return
    if card is not None:
        close_blocker(db, context, card.id)
    if choice_ids:
        open_blocker(
            db,
            context,
            lead_id,
            "underwriter_question",
            "underwriter",
            BlockerDetail(
                choice_ids=choice_ids,
                resume_trigger="an underwriter answers the choices",
                text=" ".join(choice.prompt for choice in plan.open_choices),
            ),
        )


def _evaluate_step(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
    """Build the action plan and store it on the lead when it differs from the stored one; keep the
    lead's question card in step with the plan's open choices."""
    plan = evaluate_playbook.run(
        evaluate_playbook.EvaluatePlaybookInput(
            facts=_usable_values(db, lead_id), rulings=rulings_in_force(db, lead_id)
        )
    )
    dumped = plan.model_dump(mode="json")
    digest = plan_hash(dumped)
    (stored,) = db.execute("SELECT plan_hash FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if stored != digest:
        db.execute(
            "UPDATE leads SET plan_json = ?, plan_hash = ? WHERE lead_id = ?",
            (json.dumps(dumped), digest, lead_id),
        )
        append_event(
            db,
            context,
            EventType.plan_built,
            PlanBuilt(plan=dumped, plan_hash=digest),
            lead_id=lead_id,
        )
    _sync_underwriter_question(db, context, lead_id, plan)


def _source(db: sqlite3.Connection, lead_id: str) -> str:
    """The channel the lead came in by. The applicant is the recipient of a `direct_web` lead (10.3)."""
    (source,) = db.execute("SELECT source FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    return str(source)


def _recipient(db: sqlite3.Connection, lead_id: str, facts: dict[str, JsonValue]) -> str:
    """10.3: the directory's address for an agent portal or a broker, the applicant's own address for a web lead."""
    source = _source(db, lead_id)
    address = (
        facts.get("owner_email")
        if source == "direct_web"
        else read_yaml("contacts.yaml").get(source)
    )
    if not isinstance(address, str):
        raise ValueError(f"lead {lead_id} has no contact route")
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
    registry: Registry, db: sqlite3.Connection, lead_id: str, plan: ActionPlan
) -> plan_asks.PlanAsksOutput:
    return plan_asks.run(
        plan_asks.PlanAsksInput(
            registry=registry,
            triage=_triage(db, lead_id, registry),
            conflicts=[c.opened for c in open_conflicts(db, lead_id)],
            catalogue_questions=plan.catalogue_questions,
        )
    )


def _draft_decline_notice(
    registry: Registry, db: sqlite3.Connection, context: EventContext, lead_id: str
) -> None:
    """The decline notice of a proposed decline waits for the underwriter. A lead holding an unsettled
    message gets none yet."""
    if _unsettled_intent(db, lead_id):
        return
    facts = {key: fact.value for key, fact in effective_facts(db, lead_id).items()}
    notice = render_message.run(
        render_message.RenderMessageInput(
            kind="decline_notice", registry=registry, lead_label=lead_label(db, lead_id), asks=[]
        )
    )
    create_draft(
        db,
        context,
        load_manifest(_SKILLS_ROOT / "render_message"),
        lead_id,
        "decline_notice",
        _recipient(db, lead_id, facts),
        notice.subject,
        notice.body,
        [],
    )


def _round_limit_review(db: sqlite3.Connection, lead_id: str) -> Blocker | None:
    return next((b for b in open_blockers(db, lead_id) if b.detail.cause == "round_limit"), None)


def _what_is_asked(registry: Registry, ask: Ask) -> str:
    """The labels of the fields an ask is about, or its wording when none is a registry field."""
    labels = [registry[name].label for name in ask.fields if name in registry]
    return ", ".join(labels) if labels else ask.wording


def _ask_producer_step(
    registry: Registry, db: sqlite3.Connection, context: EventContext, lead_id: str
) -> None:
    """Draft the message the plan calls for. A proposed decline suppresses every request and drafts the
    decline notice (9.6 rule 1). Otherwise the asks are planned, rendered and drafted as a request; a
    draft built at an older revision is replaced, a lead with a request in flight, or nothing to ask,
    gets no new draft, and a lead that has had its two rounds goes to the underwriter (10.1)."""
    replace_stale_drafts(db, context, lead_id)
    plan = stored_plan(db, lead_id)
    limit_review = _round_limit_review(db, lead_id)
    if plan.proposed_decline:
        if limit_review is not None:
            close_blocker(db, context, limit_review.id)  # the decline ends the lead
        _draft_decline_notice(registry, db, context, lead_id)
        return
    planned = _planned_asks(registry, db, lead_id, plan)
    if not planned.asks:
        if limit_review is not None:
            close_blocker(db, context, limit_review.id)
        return
    if _request_in_flight(db, lead_id):
        return
    if rounds_used(db, lead_id) >= MAX_REQUEST_ROUNDS:
        if limit_review is None:
            open_blocker(
                db,
                context,
                lead_id,
                "underwriter_review",
                "underwriter",
                BlockerDetail(
                    item_kind="review",
                    cause="round_limit",
                    cause_persists=True,
                    resume_trigger="the facts are supplied or the lead is declined",
                    text=f"{MAX_REQUEST_ROUNDS} requests have been sent and these are still open: "
                    f"{'; '.join(_what_is_asked(registry, ask) for ask in planned.asks)}.",
                ),
            )
        return
    facts = {key: fact.value for key, fact in effective_facts(db, lead_id).items()}
    rendered = render_message.run(
        render_message.RenderMessageInput(
            registry=registry,
            lead_label=lead_label(db, lead_id),
            asks=planned.asks,
            to_applicant=_source(db, lead_id) == "direct_web",
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
    """Draft the quote packet when the plan holds no decline and nothing open, and the lead holds no
    blocker and no unsettled message (8). An ask that remains is held by an unsettled request or a
    blocker, so the last two checks cover it. The draft waits for the underwriter."""
    plan = stored_plan(db, lead_id)
    if (
        not build_quote_packet.is_ready(plan)
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
