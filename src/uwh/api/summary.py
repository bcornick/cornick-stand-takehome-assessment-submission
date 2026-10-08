# ABOUTME: The sentence a lead's conversation opens with, written by code from the lead's status, its open items, its plan and the asks sent to the producer.
# ABOUTME: It leads with what the underwriter must do, then what the system is waiting on; a finished lead states its outcome.
import json
import sqlite3
from collections.abc import Mapping

from pydantic import JsonValue

from uwh.api.readings import decline_reason
from uwh.rules.graphs import load_graphs
from uwh.rules.models import ActionPlan
from uwh.rules.registry import FactField
from uwh.runtime.event_types import REQUEST_KINDS, EventType, MessageSent
from uwh.runtime.events import read_events
from uwh.runtime.facts import effective_facts
from uwh.runtime.rulings import choice_reasons
from uwh.runtime.waits import Blocker

# The choices that name the fact that raised them: what failed, and the fact it failed on.
_NAMED_CHOICES = {"I13.fire_fail": ("the fire simulation", "p_f")}
_FINISHED_KINDS = {"quote_sent": "quote_packet", "declined": "decline_notice"}


def ask_count(db: sqlite3.Connection, lead_id: str) -> int:
    """The number of distinct asks on the lead's requests to the producer."""
    asks: set[str] = set()
    placeholders = ", ".join("?" for _ in REQUEST_KINDS)
    for (ask_ids,) in db.execute(
        f"SELECT ask_ids_json FROM intents WHERE lead_id = ? AND kind IN ({placeholders})",
        (lead_id, *REQUEST_KINDS),
    ):
        asks.update(json.loads(ask_ids))
    return len(asks)


def _sentence(text: str) -> str:
    return text if text.endswith(".") else f"{text}."


def _words(option: str) -> str:
    return option.replace("_", " ")


def _choice_sentence(
    blocker: Blocker, plan: ActionPlan | None, facts: Mapping[str, JsonValue]
) -> str:
    choice = next(
        (
            c
            for c in (plan.open_choices if plan else [])
            if c.choice_id in blocker.detail.choice_ids
        ),
        None,
    )
    if choice is None:
        return f"I need you to choose. {_sentence(blocker.detail.text)}"
    options = [_words(option) for option in choice.options]
    named = _NAMED_CHOICES.get(choice.choice_id)
    if named is not None and named[1] in facts:
        what, key = named
        return (
            f"This lead failed {what} at {facts[key]}. "
            f"I need you to choose between a {' and '.join(options)}."
        )
    return f"I need you to choose. {choice.prompt} The options are {' or '.join(options)}."


def _observation_sentence(
    db: sqlite3.Connection,
    blocker: Blocker,
    facts: Mapping[str, JsonValue],
    fields: dict[str, FactField],
) -> str:
    key, value = db.execute(
        "SELECT key, value_json FROM observations WHERE id = ?", (blocker.detail.observation_id,)
    ).fetchone()
    label = fields[key].label if key in fields else key
    sentence = f"The producer's reply gives {label} as {json.loads(value)}"
    if key in facts:
        sentence += f", which differs from the value in use, {facts[key]}"
    return f"{sentence}. I need you to accept or reject it."


def _decline_reason(
    db: sqlite3.Connection,
    lead_id: str,
    plan: ActionPlan | None,
    facts: Mapping[str, JsonValue],
    fields: dict[str, FactField],
) -> str:
    if plan is None:
        return "no reason is recorded"
    return decline_reason(plan, load_graphs(), facts, fields, choice_reasons(db, lead_id))


def _draft_sentence(
    db: sqlite3.Connection,
    blocker: Blocker,
    plan: ActionPlan | None,
    facts: Mapping[str, JsonValue],
    fields: dict[str, FactField],
    first: bool,
) -> str:
    row = db.execute(
        "SELECT kind FROM intents WHERE id = ?", (blocker.detail.intent_id,)
    ).fetchone()
    if row is not None and row[0] == "quote_packet":
        return "The quote packet is ready. I need you to send it to the producer."
    if row is not None and row[0] in REQUEST_KINDS:
        # The item's text says why the request waits: the underwriter's open choice, or its class.
        drafted = "I drafted" if first else "I also drafted"
        return (
            f"{drafted} a request to the producer for the missing information. "
            f"{_sentence(blocker.detail.text)}"
        )
    return (
        f"I propose to decline this lead: {_decline_reason(db, blocker.lead_id, plan, facts, fields)}. "
        "I need you to send the decline notice, or withdraw the decline."
    )


def _underwriter_sentence(
    db: sqlite3.Connection,
    blocker: Blocker,
    plan: ActionPlan | None,
    facts: Mapping[str, JsonValue],
    fields: dict[str, FactField],
    first: bool,
) -> str:
    """The sentence of one item asked of the underwriter; `first` is whether it opens the line."""
    if blocker.kind == "underwriter_question":
        return _choice_sentence(blocker, plan, facts)
    if blocker.kind == "delivery_unknown":
        return "The mailbox did not confirm a message. I need you to check it before anything else goes."
    if blocker.detail.item_kind == "draft":
        return _draft_sentence(db, blocker, plan, facts, fields, first)
    if blocker.detail.item_kind == "observation":
        return _observation_sentence(db, blocker, facts, fields)
    return f"I need you to review this: {_sentence(blocker.detail.text)}"


def _sent_on(db: sqlite3.Connection, lead_id: str, kind: str) -> str:
    """The day the lead's message of that kind went out, as "Jul 1"."""
    kinds = dict(db.execute("SELECT id, kind FROM intents WHERE lead_id = ?", (lead_id,)))
    sent = [
        e
        for e in read_events(db, lead_id=lead_id)
        if e.type == EventType.message_sent
        and isinstance(e.payload, MessageSent)
        and kinds.get(e.payload.intent_id) == kind
    ]
    return f"{sent[-1].sim_ts:%b} {sent[-1].sim_ts.day}"


def summary_line(
    db: sqlite3.Connection,
    lead_id: str,
    status: str,
    plan: ActionPlan | None,
    blockers: list[Blocker],
    fields: dict[str, FactField],
) -> str:
    """The opening line of the lead's conversation."""
    facts = {key: fact.value for key, fact in effective_facts(db, lead_id).items()}
    if not blockers and status in _FINISHED_KINDS:
        when = _sent_on(db, lead_id, _FINISHED_KINDS[status])
        if status == "quote_sent":
            return f"Quote packet sent on {when}."
        return f"Declined on {when}: {_decline_reason(db, lead_id, plan, facts, fields)}."
    asked_of_underwriter = [b for b in blockers if b.owner == "underwriter"]
    sentences = [
        _underwriter_sentence(db, b, plan, facts, fields, first=index == 0)
        for index, b in enumerate(asked_of_underwriter)
    ]
    for blocker in blockers:
        if blocker.owner == "underwriter":
            continue
        if blocker.kind == "producer_reply":
            count = ask_count(db, lead_id)
            noun = "field" if count == 1 else "fields"
            lead_in = "Meanwhile I" if asked_of_underwriter else "I"
            sentences.append(
                f"{lead_in} asked the producer for the {count} missing {noun}"
                " and am waiting for the reply."
            )
        else:
            sentences.append(f"I am waiting on data: {_sentence(blocker.detail.text)}")
    return " ".join(sentences) or "Triage is running."
