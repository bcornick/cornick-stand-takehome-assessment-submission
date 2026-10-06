# ABOUTME: The chat assistant's lookups (section 11): named read functions over the views the pages use, each returning what the model is shown and the one line the underwriter sees for the step.
# ABOUTME: Every result item carries a reference number of the turn; `References` maps a number to the lead, kind and immutable id it stands for, so the model cites numbers and never sees an event id.
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from uwh.api.leads import lead_events as events_of_lead
from uwh.api.leads import open_items
from uwh.api.run import run_summary
from uwh.api.views import Citation, CitationKind, Item
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
        {"events": events}, f"Read the events of {short_name(lead_id)}: {len(events)} events"
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
    """The lead's status, its effective facts with their sources and its open items. A fact is cited
    by the event that recorded it."""
    (status,) = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    facts = effective_facts(db, lead_id).values()
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
    }
    from_reply = sum(fact.source == "reply" for fact in facts)
    return Lookup(
        shown,
        f"Read the facts of {short_name(lead_id)}: {len(facts)} values, {from_reply} from the reply",
    )


def queue_summary(db: sqlite3.Connection, references: References) -> Lookup:
    """The run's summary counts and the open items of every lead."""
    items = open_items(db)
    shown = {
        "summary": run_summary(db).model_dump(),
        "open_items": [_item(db, item, references) for item in items],
    }
    leads = len({item.lead_id for item in items})
    return Lookup(shown, f"Read the queue: {len(items)} open items on {leads} leads")


# The lookups about one lead, by the action of the chat step that asks for them.
LEAD_LOOKUPS: dict[str, Callable[[sqlite3.Connection, str, References], Lookup]] = {
    "lead_events": lead_events,
    "lead_summary": lead_summary,
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
