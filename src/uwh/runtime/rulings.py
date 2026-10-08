# ABOUTME: The underwriter's rulings on a lead (A.11): `ruling_recorded` events are written here, and the rulings in force are read back from them for the graphs, for the rejection of a decline notice and for the reason a decline already has on file.
# ABOUTME: A ruling moves the lead revision, so a draft built before it is replaced; a withdrawal or a reopened choice removes the ruling it refers to from those in force.
import sqlite3
from collections.abc import Sequence

from uwh.rules.models import ActionPlan, DeclineEffect, Rulings
from uwh.runtime.event_types import EventType, RulingKind, RulingRecorded
from uwh.runtime.events import EventContext, append_event, read_events
from uwh.runtime.workflow import lead_revision_and_plan_hash


def write_ruling(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    kind: RulingKind,
    reason: str,
    *,
    choice_id: str | None = None,
    option: str | None = None,
    suppressed_rule_ids: Sequence[str] = (),
    refers_to_event_id: int | None = None,
) -> int:
    """Write `ruling_recorded` and move the lead revision; return the event's id. The caller commits."""
    revision, plan_hash = lead_revision_and_plan_hash(db, lead_id)
    event_id = append_event(
        db,
        context,
        EventType.ruling_recorded,
        RulingRecorded(
            kind=kind,
            choice_id=choice_id,
            option=option,
            reason=reason,
            lead_revision=revision,
            plan_hash=plan_hash or "",
            suppressed_rule_ids=list(suppressed_rule_ids),
            refers_to_event_id=refers_to_event_id,
        ),
        lead_id=lead_id,
    )
    db.execute("UPDATE leads SET revision = revision + 1 WHERE lead_id = ?", (lead_id,))
    return event_id


def active_rulings(db: sqlite3.Connection, lead_id: str) -> dict[int, RulingRecorded]:
    """The rulings in force, by the id of the event that recorded each: a withdrawal or a reopened
    choice removes the ruling it refers to."""
    active: dict[int, RulingRecorded] = {}
    for event in read_events(db, lead_id=lead_id):
        ruling = event.payload
        if isinstance(ruling, RulingRecorded):
            if ruling.refers_to_event_id is None:
                active[event.id] = ruling
            else:
                active.pop(ruling.refers_to_event_id, None)
    return active


def rulings_in_force(db: sqlite3.Connection, lead_id: str) -> Rulings:
    active = active_rulings(db, lead_id).values()
    return Rulings(
        choices={r.choice_id: r.option for r in active if r.choice_id and r.option},
        suppressed_rules=[rule for r in active for rule in r.suppressed_rule_ids],
        decline_reason=next((r.reason for r in active if r.kind == "decline"), None),
    )


def declines_of(plan: ActionPlan) -> list[tuple[str, list[str]]]:
    """Each decline of the plan: its rule id and the choice whose option leads straight to it, if any."""
    declines = [
        (p.effect.rule, p.trace.choice_ids)
        for p in plan.effects
        if p.committed and isinstance(p.effect, DeclineEffect)
    ]
    for trace in plan.declines_on_every_branch:
        declines += [(branch.rule, []) for branch in trace.alternatives]
    return declines


def decline_reason_on_file(
    db: sqlite3.Connection, lead_id: str, plan: ActionPlan | None
) -> str | None:
    """The underwriter's reason for the lead's decline when a ruling made it: a `decline_lead`
    ruling's, or that of the choice whose option leads straight to a committed decline. None for a
    decline the playbook reached alone, whose reason the underwriter gives on the notice."""
    choices = {c for _, choice_ids in (declines_of(plan) if plan else []) for c in choice_ids}
    return next(
        (
            r.reason
            for r in active_rulings(db, lead_id).values()
            if r.reason and (r.kind == "decline" or r.choice_id in choices)
        ),
        None,
    )


def choice_reasons(db: sqlite3.Connection, lead_id: str) -> dict[str, str]:
    """The underwriter's reason for each choice ruled on the lead and in force, by choice id."""
    return {
        r.choice_id: r.reason
        for r in active_rulings(db, lead_id).values()
        if r.choice_id is not None and r.reason
    }
