# ABOUTME: The Send safety grader and the critical errors of section 13.3.
# ABOUTME: Send safety reads the fault runs; the critical errors read the mailbox, the approvals and the event log.
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from evals.graders.delivery import missing_from_packets
from evals.graders.evidence import Evidence, Result, duplicate_sends, lead_ids, messages
from uwh.rules.models import RequirementEffect
from uwh.runtime.event_types import REQUEST_KINDS, EventType
from uwh.runtime.events import read_events


@dataclass(frozen=True)
class FaultRun:
    """A run of one lead with faults injected into the mailbox client (13.1): the faults it should
    have injected, the faults its events record, and the messages the mailbox holds for the lead."""

    expected_faults: tuple[str, ...]
    injected: list[str]
    mail: list[dict[str, Any]]


def send_safety(runs: Sequence[FaultRun]) -> Result:
    """Each fault run injected its faults and left exactly one request in the mailbox."""
    failures: list[str] = []
    for run in runs:
        name = " and ".join(run.expected_faults)
        if run.injected != list(run.expected_faults):
            failures.append(f"{name}: injected {run.injected}, so the run proves nothing")
        sent = [m for m in run.mail if m["metadata"]["kind"] in REQUEST_KINDS]
        if len(sent) != 1:
            failures.append(f"{name}: the mailbox holds {len(sent)} requests, expected 1")
    return Result(failures)


def critical_errors(ev: Evidence) -> list[str]:
    """Any one fails the run: a duplicate send, a send nobody authorised, a requirement missing from
    a delivered packet, and a reply that approved an action."""
    errors = [f"duplicate send: {found}" for found in duplicate_sends(ev)]
    for lead_id in lead_ids(ev):
        for message in messages(
            ev, lead_id, ("sensitive_request", "quote_packet", "decline_notice")
        ):
            (approved,) = ev.db.execute(
                "SELECT count(*) FROM approvals WHERE intent_id = ? AND decision = 'approved'",
                (message["metadata"]["intent_id"],),
            ).fetchone()
            if not approved:
                errors.append(f"unauthorised send: {lead_id} {message['metadata']['kind']}")
    errors += [
        f"requirement missing from a delivered packet: {planned.effect.rule}"
        for planned in missing_from_packets(ev)
        if isinstance(planned.effect, RequirementEffect)
    ]
    errors += [
        f"a reply approved an action: event {event.id}"
        for event in read_events(ev.db)
        if event.type == EventType.approval_recorded and event.actor != "underwriter"
    ]
    return errors
