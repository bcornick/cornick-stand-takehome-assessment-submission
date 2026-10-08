# ABOUTME: GET /api/leads, /api/leads/{id}, /api/leads/{id}/events and /api/items (A.5, section 11): the queue rows in display order, one lead's detail and event list, and the open items across leads, built from stored state.
# ABOUTME: The queue groups leads by who the primary next action waits on, and orders a group by effective date, then lead id.
import json
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException

from uwh.api.event_summary import event_summary
from uwh.api.pages import plan_pages
from uwh.api.readings import choice_readings
from uwh.api.runtime import RuntimeDependency
from uwh.api.summary import ask_count, summary_line
from uwh.api.views import (
    BlockerView,
    DraftView,
    EventMessage,
    EventRow,
    FactView,
    Item,
    LeadDetail,
    LeadEvents,
    LookupView,
    QueueGroup,
    QueueRow,
)
from uwh.rules.graphs import load_graphs
from uwh.rules.models import ActionPlan, FieldTriage, Resolution, StrictModel, ValueStatus
from uwh.rules.registry import Registry, fact_fields
from uwh.runtime.clock import age_business_days
from uwh.runtime.event_types import (
    ApprovalRecorded,
    BlockerClosed,
    BlockerOpened,
    EventType,
    FactObserved,
    MessageSent,
    ProviderCalled,
    ReplyReceived,
    RulingRecorded,
    TriageCompleted,
)
from uwh.runtime.events import StoredEvent, read_events
from uwh.runtime.facts import effective_facts
from uwh.runtime.runs import current_run, run_sim_now
from uwh.runtime.waits import Blocker, open_blockers, primary_next_action
from uwh.skills.steps import lead_label

router = APIRouter()

# The assumed service level of section 11: Stand's distributor page promises estimates inside two business days.
SERVICE_LEVEL_BUSINESS_DAYS = 2

# The blocker kinds an underwriter acts on; a data or producer wait is not an item.
ITEM_KINDS = ("underwriter_review", "underwriter_question", "delivery_unknown")

# The longest event summary the pane shows.

_GROUP_ORDER: tuple[QueueGroup, ...] = (
    "blocked_on_underwriter",
    "waiting_on_data_or_producer",
    "finished",
)


def _group(status: str, action: Blocker | None) -> QueueGroup:
    if action is None and status in ("quote_sent", "declined"):
        return "finished"
    if action is not None and action.owner == "underwriter":
        return "blocked_on_underwriter"
    return "waiting_on_data_or_producer"


def queue_rows(db: sqlite3.Connection, now: datetime) -> list[QueueRow]:
    """One row per lead, in the order of section 11; `now` is the simulated time."""
    rows: list[QueueRow] = []
    for lead_id, status, received_at in db.execute(
        "SELECT lead_id, status, received_at FROM leads"
    ).fetchall():
        action = primary_next_action(db, lead_id)
        facts = effective_facts(db, lead_id)
        effective_date = facts["effective_date"].value if "effective_date" in facts else None
        age = age_business_days(datetime.fromisoformat(received_at), now)
        rows.append(
            QueueRow(
                lead_id=lead_id,
                label=lead_label(db, lead_id),
                status=status,
                primary_next_action=None if action is None else action.kind,
                waits_on=None if action is None else action.owner,
                age_business_days=age,
                service_level_breached=age > SERVICE_LEVEL_BUSINESS_DAYS,
                effective_date=effective_date if isinstance(effective_date, str) else None,
                ask_count=ask_count(db, lead_id),
                group=_group(status, action),
            )
        )
    # A lead with no effective date follows those with one.
    return sorted(
        rows,
        key=lambda r: (
            _GROUP_ORDER.index(r.group),
            r.effective_date is None,
            r.effective_date or "",
            r.lead_id,
        ),
    )


def _pending_observation(db: sqlite3.Connection, observation_id: int) -> FactView:
    key, value, source, status, evidence, event_id = db.execute(
        "SELECT key, value_json, source, status, evidence_json, event_id FROM observations"
        " WHERE id = ?",
        (observation_id,),
    ).fetchone()
    return FactView(
        key=key,
        value=json.loads(value),
        source=source,
        status=status,
        confirmed=False,
        evidence=json.loads(evidence),
        observation_id=observation_id,
        event_id=event_id,
    )


def _blocker_view(db: sqlite3.Connection, blocker: Blocker) -> BlockerView:
    observation_id = blocker.detail.observation_id
    return BlockerView(
        item_id=blocker.id,
        kind=blocker.kind,
        owner=blocker.owner,
        detail=blocker.detail,
        observation=None
        if blocker.detail.item_kind != "observation" or observation_id is None
        else _pending_observation(db, observation_id),
    )


def _missing_fields(db: sqlite3.Connection, lead_id: str) -> list[str]:
    """The fields the lead's latest triage found missing and not set aside (not required or deferred),
    in registry order; empty before the lead is triaged."""
    row = db.execute(
        "SELECT payload_json FROM events WHERE lead_id = ? AND type = ? ORDER BY id DESC LIMIT 1",
        (lead_id, EventType.triage_completed.value),
    ).fetchone()
    if row is None:
        return []
    triage = TriageCompleted.model_validate_json(row[0]).fields
    return [
        name
        for name, result in ((name, FieldTriage.model_validate(t)) for name, t in triage.items())
        if result.value_status == ValueStatus.missing
        and result.resolution not in (Resolution.not_required, Resolution.defer)
    ]


def lead_detail(db: sqlite3.Connection, lead_id: str, registry: Registry) -> LeadDetail | None:
    """The lead's detail, or None when there is no such lead."""
    lead = db.execute(
        "SELECT status, revision, plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    if lead is None:
        return None
    status, revision, plan_json = lead
    plan = None if plan_json is None else ActionPlan.model_validate_json(plan_json)
    blockers = open_blockers(db, lead_id)
    facts = effective_facts(db, lead_id)
    drafts = db.execute(
        "SELECT id, payload_hash, kind, recipient, subject, body, state, round FROM intents"
        " WHERE lead_id = ? ORDER BY round, rowid",
        (lead_id,),
    ).fetchall()
    graphs = load_graphs()
    return LeadDetail(
        lead_id=lead_id,
        label=lead_label(db, lead_id),
        status=status,
        summary=summary_line(db, lead_id, status, plan, blockers, fact_fields(registry)),
        revision=revision,
        facts=[FactView(**vars(fact)) for fact in facts.values()],
        plan=plan,
        pages=[] if plan is None else plan_pages(plan, graphs),
        readings={}
        if plan is None
        else {
            choice.choice_id: choice_readings(
                choice, graphs, {key: fact.value for key, fact in facts.items()}
            )
            for choice in plan.open_choices
        },
        blockers=[_blocker_view(db, blocker) for blocker in blockers],
        drafts=[
            DraftView(
                intent_id=d[0],
                payload_hash=d[1],
                kind=d[2],
                recipient=d[3],
                subject=d[4],
                body=d[5],
                state=d[6],
                round=d[7],
            )
            for d in drafts
        ],
        fields=list(fact_fields(registry).values()),
        missing_fields=_missing_fields(db, lead_id),
    )


def _event_message(db: sqlite3.Connection, payload: StrictModel) -> EventMessage | None:
    """The words of a sent request, read from its intent, or of a reply; None for any other event."""
    match payload:
        case MessageSent(intent_id=intent_id):
            subject, body = db.execute(
                "SELECT subject, body FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()
            return EventMessage(subject=subject, body=body)
        case ReplyReceived(body=body):
            return EventMessage(subject=None, body=body)
        case _:
            return None


def _item_id(payload: StrictModel) -> int | None:
    """The underwriter's item the event names; a wait on the producer or on data is no item."""
    match payload:
        case BlockerOpened(blocker_id=id, kind=kind) | BlockerClosed(blocker_id=id, kind=kind):
            return id if kind in ITEM_KINDS else None
        case ApprovalRecorded(item_id=id):
            return id
        case _:
            return None


def _choice_ids(payload: StrictModel) -> list[str]:
    """The choices a question card opened with, or the one a ruling answers."""
    match payload:
        case BlockerOpened(detail=detail):
            return detail.choice_ids
        case RulingRecorded(choice_id=str(choice_id)):
            return [choice_id]
        case _:
            return []


def _event_row(db: sqlite3.Connection, event: StoredEvent) -> EventRow:
    payload = event.payload
    return EventRow(
        id=event.id,
        type=event.type,
        mode=event.mode,
        actor=event.actor,
        sim_ts=event.sim_ts.isoformat(),
        summary=event_summary(payload),
        item_id=_item_id(payload),
        choice_ids=_choice_ids(payload),
        fact_key=payload.key if isinstance(payload, FactObserved) else None,
        message=_event_message(db, payload),
        lookup=LookupView(
            status=payload.result.status, missing_inputs=payload.result.missing_inputs
        )
        if isinstance(payload, ProviderCalled)
        else None,
    )


def lead_events(db: sqlite3.Connection, lead_id: str) -> LeadEvents | None:
    """The lead's events in id order, or None when there is no such lead."""
    if db.execute("SELECT 1 FROM leads WHERE lead_id = ?", (lead_id,)).fetchone() is None:
        return None
    return LeadEvents(
        lead_id=lead_id,
        events=[_event_row(db, event) for event in read_events(db, lead_id=lead_id)],
    )


def open_items(db: sqlite3.Connection) -> list[Item]:
    """The open reviews, question cards and unknown deliveries of every lead, by lead id then item id."""
    items = [
        Item(item_id=b.id, lead_id=b.lead_id, kind=b.kind, detail=b.detail)
        for (lead_id,) in db.execute("SELECT lead_id FROM leads").fetchall()
        for b in open_blockers(db, lead_id)
        if b.kind in ITEM_KINDS
    ]
    return sorted(items, key=lambda item: (item.lead_id, item.item_id))


# The handlers carry no docstring: FastAPI copies one into the OpenAPI document.
@router.get("/api/leads")
def list_leads(runtime: RuntimeDependency) -> list[QueueRow]:
    with runtime.database() as db:
        run = current_run(db)
        if run is None:
            return []
        return queue_rows(db, run_sim_now(run, runtime.env.now()))


@router.get("/api/leads/{id}")
def get_lead(id: str, runtime: RuntimeDependency) -> LeadDetail:
    with runtime.database() as db:
        detail = lead_detail(db, id, runtime.env.registry)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no lead {id}")
    return detail


@router.get("/api/leads/{id}/events")
def get_lead_events(id: str, runtime: RuntimeDependency) -> LeadEvents:
    with runtime.database() as db:
        events = lead_events(db, id)
    if events is None:
        raise HTTPException(status_code=404, detail=f"no lead {id}")
    return events


@router.get("/api/items")
def list_items(runtime: RuntimeDependency) -> list[Item]:
    with runtime.database() as db:
        return open_items(db)
