# ABOUTME: GET /api/leads and GET /api/leads/{id} (A.5, section 11): the queue rows in display order, and one lead's facts with their source tags, plan, open blockers and messages, built from stored state.
# ABOUTME: The queue groups leads by who the primary next action waits on, and orders a group by effective date, then lead id.
import json
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException

from uwh.api.runtime import RuntimeDependency
from uwh.api.views import BlockerView, DraftView, FactView, LeadDetail, QueueGroup, QueueRow
from uwh.rules.models import ActionPlan
from uwh.runtime.clock import age_business_days
from uwh.runtime.event_types import REQUEST_KINDS
from uwh.runtime.facts import effective_facts
from uwh.runtime.runs import current_run, run_sim_now
from uwh.runtime.waits import Blocker, open_blockers, primary_next_action
from uwh.skills.steps import lead_label

router = APIRouter()

# The assumed service level of section 11: Stand's distributor page promises estimates inside two business days.
SERVICE_LEVEL_BUSINESS_DAYS = 2

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


def _ask_count(db: sqlite3.Connection, lead_id: str) -> int:
    asks: set[str] = set()
    placeholders = ", ".join("?" for _ in REQUEST_KINDS)
    for (ask_ids,) in db.execute(
        f"SELECT ask_ids_json FROM intents WHERE lead_id = ? AND kind IN ({placeholders})",
        (lead_id, *REQUEST_KINDS),
    ):
        asks.update(json.loads(ask_ids))
    return len(asks)


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
                ask_count=_ask_count(db, lead_id),
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
    key, value, source, status, evidence = db.execute(
        "SELECT key, value_json, source, status, evidence_json FROM observations WHERE id = ?",
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


def lead_detail(db: sqlite3.Connection, lead_id: str) -> LeadDetail | None:
    """The lead's detail, or None when there is no such lead."""
    lead = db.execute(
        "SELECT status, revision, plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    if lead is None:
        return None
    status, revision, plan_json = lead
    facts = effective_facts(db, lead_id)
    drafts = db.execute(
        "SELECT id, payload_hash, kind, recipient, subject, body, state, round FROM intents"
        " WHERE lead_id = ? ORDER BY round, rowid",
        (lead_id,),
    ).fetchall()
    return LeadDetail(
        lead_id=lead_id,
        label=lead_label(db, lead_id),
        status=status,
        revision=revision,
        facts=[FactView(**vars(fact)) for fact in facts.values()],
        plan=None if plan_json is None else ActionPlan.model_validate_json(plan_json),
        blockers=[_blocker_view(db, blocker) for blocker in open_blockers(db, lead_id)],
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
    )


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
        detail = lead_detail(db, id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no lead {id}")
    return detail
