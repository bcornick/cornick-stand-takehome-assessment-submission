# ABOUTME: What the graders read after a phase of a run: the application database, the registry and the producer's mailbox, plus the reads over them that several graders share.
# ABOUTME: A grader is a plain function of this evidence and the expectations of the phase; it returns its failures and any measures it reports.
import json
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import JsonValue

from uwh.rules.confirmations import COMBINED_DWELLING_USE_ID
from uwh.rules.data_files import read_yaml
from uwh.rules.models import ActionPlan
from uwh.rules.registry import Registry
from uwh.runtime.event_types import REQUEST_KINDS
from uwh.runtime.waits import open_blockers
from uwh.runtime.workflow import stored_plan

# The label of one lead for a phase: its `first_pass` or its `after_actions`.
Expectation = Mapping[str, Any]
# The expectations of a phase by lead id; a lead with none for the phase is absent.
Expectations = Mapping[str, Expectation]


@dataclass(frozen=True)
class Evidence:
    db: sqlite3.Connection
    registry: Registry
    mail: Mapping[str, list[dict[str, Any]]]  # lead id -> the messages the mailbox holds for it
    earlier: frozenset[str] = frozenset()  # intents delivered in an earlier phase


@dataclass
class Result:
    """What a grader found: one message per failure, and the numbers it reports."""

    failures: list[str]
    measures: dict[str, JsonValue] = field(default_factory=dict)


def lead_ids(ev: Evidence) -> list[str]:
    return [lead_id for (lead_id,) in ev.db.execute("SELECT lead_id FROM leads ORDER BY lead_id")]


def status_of(ev: Evidence, lead_id: str) -> str:
    (status,) = ev.db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    return str(status)


def plan_of(ev: Evidence, lead_id: str) -> ActionPlan | None:
    """The lead's stored plan; None before the lead has one."""
    (plan_hash,) = ev.db.execute(
        "SELECT plan_hash FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    return None if plan_hash is None else stored_plan(ev.db, lead_id)


def messages(
    ev: Evidence, lead_id: str, kinds: tuple[str, ...], *, new_only: bool = False
) -> list[dict[str, Any]]:
    """The mailbox's messages of the lead of these kinds; `new_only` leaves out those of an earlier phase."""
    return [
        m
        for m in ev.mail.get(lead_id, [])
        if m["metadata"]["kind"] in kinds
        and not (new_only and m["metadata"]["intent_id"] in ev.earlier)
    ]


def held_requests(ev: Evidence, lead_id: str) -> list[tuple[str, set[str]]]:
    """The kind and ask ids of each request draft the lead holds for the underwriter's review."""
    held: list[tuple[str, set[str]]] = []
    for blocker in open_blockers(ev.db, lead_id):
        if blocker.detail.item_kind != "draft" or blocker.detail.intent_id is None:
            continue
        kind, ask_ids_json = ev.db.execute(
            "SELECT kind, ask_ids_json FROM intents WHERE id = ?", (blocker.detail.intent_id,)
        ).fetchone()
        if kind in REQUEST_KINDS:
            held.append((kind, set(json.loads(ask_ids_json))))
    return held


def delivered_asks(ev: Evidence, lead_id: str, *, new_only: bool = False) -> set[str]:
    """The ask ids of the requests the mailbox holds for the lead."""
    ask_ids: set[str] = set()
    for message in messages(ev, lead_id, REQUEST_KINDS, new_only=new_only):
        (ask_ids_json,) = ev.db.execute(
            "SELECT ask_ids_json FROM intents WHERE id = ?", (message["metadata"]["intent_id"],)
        ).fetchone()
        ask_ids |= set(json.loads(ask_ids_json))
    return ask_ids


def ask_classes() -> tuple[frozenset[str], frozenset[str]]:
    """The ask ids that are confirmations and those that are catalogue questions."""
    confirmations = frozenset(read_yaml("wording.yaml")["confirmations"]) | {
        COMBINED_DWELLING_USE_ID
    }
    return confirmations, frozenset(read_yaml("catalogue.yaml")["questions"])


def field_asks(ask_ids: set[str]) -> set[str]:
    """The ask ids that name registry fields: neither a confirmation nor a catalogue question."""
    confirmations, catalogue = ask_classes()
    return ask_ids - confirmations - catalogue


def duplicate_sends(ev: Evidence) -> list[str]:
    """Section 7.5: more than one request in the mailbox for one run, lead and round, or more than one
    quote packet, or more than one decline notice, for one run and lead."""
    found: list[str] = []
    for lead_id, held in ev.mail.items():
        counts = Counter(
            (m["metadata"]["run_id"], "request", m["metadata"]["round"])
            if m["metadata"]["kind"] in REQUEST_KINDS
            else (m["metadata"]["run_id"], m["metadata"]["kind"], None)
            for m in held
        )
        found += [
            f"{lead_id}: {n} {kind} messages for one round or run"
            for (_, kind, _), n in counts.items()
            if n > 1
        ]
    return found
