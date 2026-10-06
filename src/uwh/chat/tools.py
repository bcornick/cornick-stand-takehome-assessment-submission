# ABOUTME: The chat assistant's lookups (section 11): named read functions over the views the pages use, each returning what the model is shown and the one line the underwriter sees for the step.
# ABOUTME: Every result item carries a reference number of the turn; `References` maps a number to the lead, kind and immutable id it stands for, so the model cites numbers and never sees an event id.
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from uwh.api.leads import lead_events as events_of_lead
from uwh.api.leads import open_items
from uwh.api.pages import plan_pages
from uwh.api.run import run_summary
from uwh.api.views import Citation, CitationKind, Item
from uwh.rules.graphs import load_graphs
from uwh.rules.models import ActionPlan
from uwh.runtime.event_types import REQUEST_KINDS, EventType
from uwh.runtime.facts import effective_facts
from uwh.skills.steps import lead_label


class References:
    """The reference numbers of one chat turn, handed out in the order results show their items."""

    def __init__(self) -> None:
        self._citations: list[Citation] = []

    def number(self, lead_id: str, kind: CitationKind, id: int | str) -> int:
        """The number that stands for the thing; the same thing shown twice keeps its number."""
        for citation in self._citations:
            if (citation.lead_id, citation.kind, citation.id) == (lead_id, kind, id):
                return citation.number
        number = len(self._citations) + 1
        self._citations.append(Citation(number=number, lead_id=lead_id, kind=kind, id=id))
        return number

    def resolve(self, numbers: Iterable[int]) -> list[Citation]:
        """What the numbers stand for, each once and in the order given; a number no result of the
        turn showed is dropped."""
        shown = {citation.number: citation for citation in self._citations}
        return [shown[number] for number in dict.fromkeys(numbers) if number in shown]


@dataclass(frozen=True)
class Lookup:
    shown: dict[str, Any]  # the result the model is shown
    summary: str  # the line the underwriter sees: what was read and what it held


def short_name(lead_id: str) -> str:
    """The lead as an underwriter says it: "lead 008" for LEAD-00000042-008."""
    return f"lead {lead_id.rsplit('-', 1)[-1]}"


def _count(number: int, one: str, many: str) -> str:
    """The number with its noun: "1 reply", "2 replies"."""
    return f"{number} {one if number == 1 else many}"


def _plan(db: sqlite3.Connection, lead_id: str) -> ActionPlan | None:
    """The lead's stored plan; None until the lead has been triaged."""
    (plan_json,) = db.execute(
        "SELECT plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    return None if plan_json is None else ActionPlan.model_validate_json(plan_json)


def find_lead(db: sqlite3.Connection, named: str) -> str | None:
    """The id of the lead named in full or by the end of its id ("008"), when exactly one lead is."""
    ids = [
        lead_id
        for (lead_id,) in db.execute("SELECT lead_id FROM leads").fetchall()
        if lead_id.endswith(named)
    ]
    return ids[0] if len(ids) == 1 else None


def lead_events(db: sqlite3.Connection, lead_id: str, references: References) -> Lookup:
    """Every event of the lead, oldest first, each with the sentence the conversation shows."""
    page = events_of_lead(db, lead_id)
    assert page is not None  # the lead was found
    events = [
        {
            "ref": references.number(lead_id, "event", event.id),
            "type": event.type.value,
            "actor": event.actor,
            "summary": event.summary,
        }
        for event in page.events
    ]
    return Lookup(
        {"events": events},
        f"Read the events of {short_name(lead_id)}: {_count(len(events), 'event', 'events')}",
    )


def _item(db: sqlite3.Connection, item: Item, references: References) -> dict[str, Any]:
    """An open item, cited by the event that opened it."""
    (opened_event_id,) = db.execute(
        "SELECT opened_event_id FROM blockers WHERE id = ?", (item.item_id,)
    ).fetchone()
    return {
        "ref": references.number(item.lead_id, "event", opened_event_id),
        "lead_id": item.lead_id,
        "kind": item.kind,
        "text": item.detail.text,
    }


def lead_summary(db: sqlite3.Connection, lead_id: str, references: References) -> Lookup:
    """The lead's status, its effective facts with their sources, its open items and the choices
    the playbook leaves to the underwriter. A fact is cited by the event that recorded it."""
    (status,) = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    facts = effective_facts(db, lead_id).values()
    plan = _plan(db, lead_id)
    shown = {
        "lead_id": lead_id,
        "label": lead_label(db, lead_id),
        "status": status,
        "facts": [
            {
                "ref": references.number(lead_id, "fact", fact.event_id),
                "key": fact.key,
                "value": fact.value,
                "source": fact.source,
            }
            for fact in facts
        ],
        "open_items": [
            _item(db, item, references) for item in open_items(db) if item.lead_id == lead_id
        ],
        "open_choices": [
            {"choice_id": choice.choice_id, "options": choice.options, "prompt": choice.prompt}
            for choice in ([] if plan is None else plan.open_choices)
        ],
    }
    from_reply = sum(fact.source == "reply" for fact in facts)
    return Lookup(
        shown,
        f"Read the facts of {short_name(lead_id)}: {_count(len(facts), 'value', 'values')},"
        f" {from_reply} from the reply",
    )


def queue_summary(db: sqlite3.Connection, references: References) -> Lookup:
    """The run's summary counts and the open items of every lead."""
    items = open_items(db)
    shown = {
        "summary": run_summary(db).model_dump(),
        "open_items": [_item(db, item, references) for item in items],
    }
    leads = len({item.lead_id for item in items})
    return Lookup(
        shown,
        f"Read the queue: {_count(len(items), 'open item', 'open items')} on {_count(leads, 'lead', 'leads')}",
    )


def _intents(db: sqlite3.Connection, lead_id: str) -> list[dict[str, Any]]:
    """The lead's intents in the order of the detail's drafts: round, then insertion."""
    rows = db.execute(
        "SELECT id, kind, state, subject, body FROM intents WHERE lead_id = ?"
        " ORDER BY round, rowid",
        (lead_id,),
    ).fetchall()
    return [
        {"id": id, "kind": kind, "state": state, "subject": subject, "body": body}
        for id, kind, state, subject, body in rows
    ]


def messages(db: sqlite3.Connection, lead_id: str, references: References) -> Lookup:
    """The requests sent on the lead, each cited by its intent, and the replies received, each
    cited by its event."""
    requests = [
        {
            "ref": references.number(lead_id, "message", intent["id"]),
            "kind": intent["kind"],
            "subject": intent["subject"],
            "body": intent["body"],
        }
        for intent in _intents(db, lead_id)
        if intent["kind"] in REQUEST_KINDS and intent["state"] == "sent"
    ]
    page = events_of_lead(db, lead_id)
    assert page is not None  # the lead was found
    replies = [
        {"ref": references.number(lead_id, "reply", event.id), "body": event.message.body}
        for event in page.events
        if event.type == EventType.reply_received and event.message is not None
    ]
    return Lookup(
        {"requests": requests, "replies": replies},
        f"Read the messages of {short_name(lead_id)}: {_count(len(requests), 'request', 'requests')} sent,"
        f" {_count(len(replies), 'reply', 'replies')}",
    )


def current_draft(db: sqlite3.Connection, lead_id: str, references: References) -> Lookup:
    """The lead's latest intent, cited by its id; it keeps the id when edited. The id is shown,
    since an `edit_draft` proposal names it."""
    intents = _intents(db, lead_id)
    if not intents:
        return Lookup({"draft": None}, f"Read the draft of {short_name(lead_id)}: no draft")
    latest = intents[-1]
    draft = {
        "ref": references.number(lead_id, "message", latest["id"]),
        "intent_id": latest["id"],
        "kind": latest["kind"],
        "state": latest["state"],
        "subject": latest["subject"],
        "body": latest["body"],
    }
    return Lookup(
        {"draft": draft},
        f"Read the draft of {short_name(lead_id)}: {latest['kind']}, {latest['state']}",
    )


def playbook_path(db: sqlite3.Connection, lead_id: str, references: References) -> Lookup:
    """The lead's stored plan grouped by playbook page, each page cited by its key."""
    plan = _plan(db, lead_id)
    pages = [] if plan is None else plan_pages(plan, load_graphs())
    shown = [
        {
            "ref": references.number(lead_id, "page", page.key),
            "page": page.key,
            "effects": [effect.model_dump(mode="json") for effect in page.effects],
            "declines_on_every_branch": [
                trace.model_dump(mode="json") for trace in page.declines_on_every_branch
            ],
            "waits_on": page.waits_on,
            "not_evaluated": [note.model_dump(mode="json") for note in page.not_evaluated],
        }
        for page in pages
    ]
    return Lookup(
        {"pages": shown},
        f"Read the playbook path of {short_name(lead_id)}: {_count(len(shown), 'page', 'pages')}",
    )


# The lookups about one lead, by the action of the chat step that asks for them.
LEAD_LOOKUPS: dict[str, Callable[[sqlite3.Connection, str, References], Lookup]] = {
    "lead_events": lead_events,
    "lead_summary": lead_summary,
    "messages": messages,
    "current_draft": current_draft,
    "playbook_path": playbook_path,
}


def look_up(
    db: sqlite3.Connection, action: str, named_lead: str | None, references: References
) -> Lookup:
    """Answer a lookup step. A lead that cannot be found is an error result, shown to the model."""
    if action == "queue_summary":
        return queue_summary(db, references)
    lead_id = None if named_lead is None else find_lead(db, named_lead)
    if lead_id is None:
        return Lookup({"error": f"there is no lead {named_lead}"}, f"Found no lead {named_lead}")
    return LEAD_LOOKUPS[action](db, lead_id, references)
