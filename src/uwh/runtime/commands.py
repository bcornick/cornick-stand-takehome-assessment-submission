# ABOUTME: The command layer of 7.4 and A.11: one entry point that takes the actor from the transport, applies the actor and class rules, runs the handler and the lead's re-evaluation in one transaction, and writes `command_refused` for a refusal.
# ABOUTME: The handlers are start_run, deliver_reply, resolve_fact, edit_draft, record_ruling, decline_lead, propose_command, and approve and reject of an observation, a draft, a delivery_unknown item or an event-raised review; a command type with no handler raises NotImplementedError after the checks.
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial

import anthropic
from pydantic import JsonValue

from uwh.rules.models import FieldTriage
from uwh.runtime.event_types import (
    Actor,
    ApprovalDecision,
    ApprovalRecorded,
    BlockerDetail,
    CommandRefused,
    EventType,
    IntentState,
    ModelCalled,
    ReplayMiss,
    ReplyRead,
    ReplyReceived,
    ReviewCause,
    SkillFallbackUsed,
)
from uwh.runtime.events import EventContext, MakeContext, StaleRun, append_event, read_events
from uwh.runtime.facts import (
    LATE_REPLY_CAUSES,
    ReplyValue,
    approve_observation,
    open_conflicts,
    reject_late_reply_values,
    reject_observation,
    resolve_fact,
    usable_facts,
)
from uwh.runtime.hashing import sha256_hex
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.runs import RunEnvironment, begin_run, command_context, current_run, pass_context
from uwh.runtime.proposals import create_proposal
from uwh.runtime.rulings import active_rulings, declines_of, write_ruling
from uwh.runtime.send import (
    Intent,
    close_unsent,
    dispatch_ready,
    edit_draft,
    intent_in_state,
    read_intent,
    reconcile,
    void_approvals,
)
from uwh.runtime.recordings import Exchange
from uwh.runtime.waits import (
    Blocker,
    close_blocker,
    open_blocker,
    open_blocker_by_id,
    open_blockers,
)
from uwh.runtime.workflow import (
    is_terminal,
    lead_revision_and_plan_hash,
    record_reply,
    reevaluate,
    stored_plan,
    unit_of_work,
)
from uwh.skills.manifest import load_manifest
from uwh.skills.read_reply import skill as read_reply
from uwh.skills.triage_fields import skill as triage_fields
from uwh.skills.vertical import ROUND_REVIEW_CAUSES, command_class


@dataclass(frozen=True)
class CommandResult:
    """The A.11 response. `event_id` is the event the command produced, or the `command_refused` event."""

    accepted: bool
    event_id: int
    reason: str | None


@dataclass(frozen=True)
class _Outcome:
    """What a handler did: `event_id` is the event the command produced. `lead_id` is the lead the
    command is about, or None for a command about no lead, which is neither re-evaluated nor
    dispatched. `recheck_intent_id` names an `unknown` intent whose mailbox check the command asks for."""

    event_id: int
    lead_id: str | None
    recheck_intent_id: str | None = None


class _Refusal(Exception):
    """A command the layer refuses; the message is the reason."""


Handler = Callable[
    [sqlite3.Connection, EventContext, RunEnvironment, Mapping[str, JsonValue]], _Outcome
]


def submit_command(
    db: sqlite3.Connection,
    env: RunEnvironment,
    actor: Actor,
    command_type: str,
    payload: Mapping[str, JsonValue],
) -> CommandResult:
    """Apply one command. `actor` is the transport's binding, never a payload value.

    An accepted command and the re-evaluation of its lead commit together; after that commit the
    lead's drafts that can go are dispatched, as the run the command ran in; when a start has replaced
    that run, nothing is sent and the command is still accepted (A.11, 14). A refusal rolls back whatever the handler wrote
    and commits one `command_refused` event. A command type with no handler raises
    NotImplementedError after the checks, writing nothing. A `deliver_reply` reads the reply with the
    model before its transaction opens, so no model call holds the write lock.
    """
    if db.in_transaction:
        raise RuntimeError(
            "a command opens its own transaction, so the connection must not be in one"
        )
    reason = _gate(actor, command_type, payload)
    if reason is None:
        try:
            handler = _handler_for(db, env, actor, command_type, payload)
            with unit_of_work(db):
                context = _context(db, env, actor)
                outcome = handler(db, context, env, payload)
                if outcome.lead_id is not None:
                    # Every accepted command re-evaluates its lead in the command's transaction
                    # (A.11); a re-evaluation builds drafts and dispatches nothing.
                    reevaluate(
                        db, lambda: _context(db, env, "workflow"), outcome.lead_id, env.steps
                    )
                run = current_run(db)
            if outcome.lead_id is not None:
                assert run is not None  # a command about a lead runs inside a run
                make_context = pass_context(run, env)
                try:
                    _send_after_commit(
                        db, env, make_context, outcome.lead_id, outcome.recheck_intent_id
                    )
                except StaleRun:
                    pass  # a start replaced the run; its drafts are gone, so there is nothing to send
            return CommandResult(True, outcome.event_id, None)
        except _Refusal as refusal:
            reason = str(refusal)
    with unit_of_work(db):
        event_id = append_event(
            db,
            _context(db, env, actor),
            EventType.command_refused,
            CommandRefused(command_type=command_type, command_payload=dict(payload), reason=reason),
            lead_id=_lead_named(db, payload),
        )
    return CommandResult(False, event_id, reason)


def _context(db: sqlite3.Connection, env: RunEnvironment, actor: Actor) -> EventContext:
    """The context of an event written now. Built inside the command's transaction, so a wait for
    the write lock cannot leave stale timestamps or a stale run on the event."""
    return command_context(db, actor, env.mode, env.ruleset_hash, env.now())


def _send_after_commit(
    db: sqlite3.Connection,
    env: RunEnvironment,
    make_context: MakeContext,
    lead_id: str,
    recheck_intent_id: str | None,
) -> None:
    """Re-check the delivery an approval asked about, unless another command has settled it since, then
    dispatch every draft of the lead that can go. The command has committed, so what the mailbox or a
    draft's state makes impossible is recorded on the intent or the draft and never raised; only
    StaleRun raises. `make_context` carries the command's
    run and builds each event's context when the event is written, after its own post."""
    if recheck_intent_id is not None:
        rechecked = read_intent(db, recheck_intent_id)
        if rechecked is not None and rechecked.state == "unknown":
            reconcile(db, env.mailbox, make_context, recheck_intent_id)
    dispatch_ready(db, env.mailbox, make_context, lead_id)


def _gate(actor: Actor, command_type: str, payload: Mapping[str, JsonValue]) -> str | None:
    """The reason the actor may not submit the command, or None. The actor comes from the transport (7.4)."""
    if "actor" in payload:
        return "the payload names no actor; the transport binds it"
    declared = command_class(command_type)
    if declared is None:
        return f"{command_type} is not a command"
    if actor not in declared.actors:
        return f"{actor} may not submit {command_type}"
    return None


def _lead_exists(db: sqlite3.Connection, lead_id: str) -> bool:
    return db.execute("SELECT 1 FROM leads WHERE lead_id = ?", (lead_id,)).fetchone() is not None


def _lead_named(db: sqlite3.Connection, payload: Mapping[str, JsonValue]) -> str | None:
    """The lead a command's payload names, directly or through its item or intent, when that lead
    exists; the lead of a refusal's event."""
    lead_id = payload.get("lead_id")
    if isinstance(lead_id, str):
        return lead_id if _lead_exists(db, lead_id) else None
    item_id = payload.get("item_id")
    if isinstance(item_id, int) and not isinstance(item_id, bool):
        row = db.execute("SELECT lead_id FROM blockers WHERE id = ?", (item_id,)).fetchone()
        return None if row is None else str(row[0])
    intent_id = payload.get("intent_id")
    if isinstance(intent_id, str):
        intent = read_intent(db, intent_id)
        return None if intent is None else intent.lead_id
    return None


def _lead_binding(db: sqlite3.Connection, lead_id: str) -> tuple[int, str]:
    """The lead's revision and plan hash now."""
    try:
        revision, plan_hash = lead_revision_and_plan_hash(db, lead_id)
    except ValueError as error:
        raise _Refusal(str(error)) from error
    if plan_hash is None:
        raise _Refusal(f"lead {lead_id} has no plan to decide against")
    return revision, plan_hash


# ---- payload fields -----------------------------------------------------------------------------


def _text(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise _Refusal(f"the payload needs {key}, a string")
    return value


def _nonempty_text(payload: Mapping[str, JsonValue], key: str) -> str:
    value = _text(payload, key)
    if not value:
        raise _Refusal(f"the payload needs a non-empty {key}")
    return value


def _integer(payload: Mapping[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Refusal(f"the payload needs {key}, an integer")
    return value


def _open_item(db: sqlite3.Connection, payload: Mapping[str, JsonValue]) -> Blocker:
    """The open blocker `item_id` names (A.11)."""
    item_id = payload.get("item_id")
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        raise _Refusal("the payload needs item_id, an integer")
    item = open_blocker_by_id(db, item_id)
    if item is None:
        raise _Refusal(f"item {item_id} is not an open item")
    return item


def _intent_in_state(db: sqlite3.Connection, intent_id: str, state: IntentState) -> Intent:
    """The intent, which must be in the state."""
    try:
        return intent_in_state(db, intent_id, state)
    except ValueError as error:
        raise _Refusal(str(error)) from error


# ---- handlers -----------------------------------------------------------------------------------


def _start_run(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    """Start a run (14). The first pass runs after this command commits, started by the caller."""
    seed = _integer(payload, "seed")
    run = current_run(db)
    if run is not None and run.status == "processing":
        raise _Refusal(f"run {run.run_id} is still processing")
    if db.execute("SELECT 1 FROM intents WHERE state = 'dispatching'").fetchone() is not None:
        raise _Refusal("a message is being sent; a run starts when its delivery is settled")
    return _Outcome(begin_run(db, context, env.leadgen, env.mailbox, seed, env.ledger_rules), None)


# ---- replies ------------------------------------------------------------------------------------

_REVIEW_TEXT: dict[ReviewCause, str] = {
    "unread_reply": "A reply arrived and was not read.",
    "off_topic_reply": "A reply arrived that does not answer the request.",
    "declining_reply": "A reply arrived that declines to answer.",
}


def _reply_target(db: sqlite3.Connection, payload: Mapping[str, JsonValue]) -> Intent:
    """The sent request a reply answers. Refuses an intent that is not `sent`, one of another lead,
    and a body already delivered for it (10.4)."""
    lead_id, body = _text(payload, "lead_id"), _text(payload, "body")
    intent = _intent_in_state(db, _text(payload, "intent_id"), "sent")
    if intent.lead_id != lead_id:
        raise _Refusal(f"intent {intent.id} is not a message to lead {lead_id}")
    body_hash = sha256_hex(body.encode())
    for event in read_events(db, lead_id=lead_id):
        if (
            isinstance(event.payload, ReplyReceived)
            and event.payload.intent_id == intent.id
            and event.payload.body_hash == body_hash
        ):
            raise _Refusal(f"this reply to intent {intent.id} is already delivered")
    return intent


# What `read_reply` returned and the exchanges it made; None when the model is not available.
type _ReplyReading = tuple[read_reply.Reading | read_reply.Abstention, list[Exchange]] | None


def _triage_with_reply(
    db: sqlite3.Connection, env: RunEnvironment, lead_id: str, reading: read_reply.Reading
) -> dict[str, FieldTriage]:
    """The lead's field triage over its usable facts with the reading's values applied."""
    facts = {key: fact.value for key, fact in usable_facts(db, lead_id).items()}
    facts |= {candidate.field: candidate.value for candidate in reading.candidates}
    conflicting = [name for conflict in open_conflicts(db, lead_id) for name in conflict.fields]
    return triage_fields.run(
        triage_fields.TriageFieldsInput(
            registry=env.registry, facts=facts, conflicting_fields=conflicting
        )
    ).fields


def _read_reply_first(
    db: sqlite3.Connection,
    env: RunEnvironment,
    actor: Actor,
    payload: Mapping[str, JsonValue],
) -> Handler:
    """Read the reply with the model, outside any transaction, and return the handler that records it.
    A replay with no recording for the reply records the miss and refuses (7.7); a provider error leaves
    the reply unread."""
    intent = _reply_target(db, payload)
    reading: _ReplyReading = None
    if env.model.available:
        asks = read_reply.open_asks(
            intent.ask_ids,
            env.registry,
            [conflict.opened for conflict in open_conflicts(db, intent.lead_id)],
        )
        try:
            reading = read_reply.run(
                read_reply.ReadReplyInput(body=_text(payload, "body"), asks=asks), env.model
            )
            if isinstance(reading[0], read_reply.Reading):
                reading = (
                    read_reply.decide_classification(
                        reading[0], asks, _triage_with_reply(db, env, intent.lead_id, reading[0])
                    ),
                    reading[1],
                )
        except RecordingMiss as miss:
            with unit_of_work(db):
                append_event(
                    db,
                    _context(db, env, actor),
                    EventType.replay_miss,
                    ReplayMiss(
                        skill=miss.key.skill,
                        prompt_version=miss.key.prompt_version,
                        input_hash=miss.key.input_hash,
                    ),
                    lead_id=intent.lead_id,
                )
            raise _Refusal(str(miss)) from miss
        except anthropic.APIError:
            reading = (
                None  # the provider is unavailable: the reply is recorded unread, as with no key
            )
    return partial(_record_reply, reading=reading)


def _record_reply_events(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    intent: Intent,
    body_hash: str,
    reading: _ReplyReading,
) -> None:
    """The events of the reading: each model call, then the reading or the abstention. With no model
    available the skill's fallback is used and nothing was read."""
    if reading is None:
        fallback = load_manifest(env.skills_root / "read_reply").fallback
        append_event(
            db,
            context,
            EventType.skill_fallback_used,
            SkillFallbackUsed(skill="read_reply", status="unavailable", fallback=fallback),
            lead_id=intent.lead_id,
        )
        return
    result, exchanges = reading
    for exchange in exchanges:
        append_event(
            db,
            context,
            EventType.model_called,
            ModelCalled(
                skill=exchange.skill,
                prompt_version=exchange.prompt_version,
                input_hash=exchange.input_hash,
                tokens_in=exchange.tokens_in,
                tokens_out=exchange.tokens_out,
                stop_reason=exchange.stop_reason,
            ),
            lead_id=intent.lead_id,
            model_id=exchange.model_id,
            request_id=exchange.request_id or None,
            prompt_versions={exchange.skill: exchange.prompt_version},
        )
    if isinstance(result, read_reply.Abstention):
        read = ReplyRead(
            intent_id=intent.id,
            body_hash=body_hash,
            classification=None,
            abstention=result.reason,
            candidates=[],
            dropped=[],
        )
    else:
        read = ReplyRead(
            intent_id=intent.id,
            body_hash=body_hash,
            classification=result.classification,
            abstention=None,
            candidates=result.candidates,
            dropped=result.dropped,
        )
    append_event(db, context, EventType.reply_read, read, lead_id=intent.lead_id)


def _answers(result: read_reply.Reading | read_reply.Abstention | None) -> list[ReplyValue] | None:
    """The values a reading answers, or None when the reply is unread, off topic or a refusal."""
    if not isinstance(result, read_reply.Reading) or result.classification not in (
        "answers_all",
        "answers_some",
    ):
        return None
    return [
        ReplyValue(
            c.field,
            c.value,
            {"quote": c.quote, "span_start": c.span_start, "span_end": c.span_end},
        )
        for c in result.candidates
    ]


def _settle_round(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    intent: Intent,
    result: read_reply.Reading | read_reply.Abstention | None,
    answers: list[ReplyValue] | None,
) -> None:
    """Apply the answers to the ledger and close the round the reply answers, or raise the review
    that holds an unanswered round for the underwriter."""
    lead_id = intent.lead_id
    round_item = next(
        (
            b
            for b in open_blockers(db, lead_id)
            if b.kind == "producer_reply" and b.detail.intent_id == intent.id
        ),
        None,
    )
    values = answers or []
    if round_item is None or is_terminal(db, lead_id):
        record_reply(
            db,
            context,
            lead_id,
            values,
            env.ledger_rules,
            round_closed=round_item is None,
            intent_id=intent.id,
        )
    elif answers is not None:
        record_reply(
            db, context, lead_id, values, env.ledger_rules, round_closed=False, intent_id=intent.id
        )
        close_blocker(db, context, round_item.id)
    else:
        cause: ReviewCause = "unread_reply"
        if isinstance(result, read_reply.Reading):
            cause = "off_topic_reply" if result.classification == "off_topic" else "declining_reply"
        open_blocker(
            db,
            context,
            lead_id,
            "underwriter_review",
            "underwriter",
            BlockerDetail(
                item_kind="review",
                cause=cause,
                resume_trigger="an underwriter acknowledges the reply",
                intent_id=intent.id,
                text=_REVIEW_TEXT[cause],
            ),
        )


def _record_reply(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
    *,
    reading: _ReplyReading,
) -> _Outcome:
    """Record the reply and its reading, apply the values it answers by the ledger's rules and settle
    the round (10.4). A reply to a closed round or a final lead only raises a late-reply review. An
    unread reply, an off-topic one and a declining one leave the round open for the underwriter."""
    intent = _reply_target(db, payload)
    body = _text(payload, "body")
    body_hash = sha256_hex(body.encode())
    event_id = append_event(
        db,
        context,
        EventType.reply_received,
        ReplyReceived(intent_id=intent.id, body=body, body_hash=body_hash),
        lead_id=intent.lead_id,
    )
    _record_reply_events(db, context, env, intent, body_hash, reading)
    result = None if reading is None else reading[0]
    _settle_round(db, context, env, intent, result, _answers(result))
    return _Outcome(event_id, intent.lead_id)


def _resolve_fact(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    lead_id, key = _text(payload, "lead_id"), _text(payload, "key")
    reason = _text(payload, "reason")
    if "value" not in payload:
        raise _Refusal("the payload needs value")
    if not _lead_exists(db, lead_id):
        raise _Refusal(f"there is no lead {lead_id}")
    event_id = resolve_fact(db, context, lead_id, key, payload["value"], reason, env.ledger_rules)
    return _Outcome(event_id, lead_id)


def _record_ruling(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    lead_id, choice_id = _text(payload, "lead_id"), _text(payload, "choice_id")
    option, reason = _text(payload, "option"), _nonempty_text(payload, "reason")
    if not _lead_exists(db, lead_id):
        raise _Refusal(f"there is no lead {lead_id}")
    if not any(
        b.kind == "underwriter_question" and choice_id in b.detail.choice_ids
        for b in open_blockers(db, lead_id)
    ):
        raise _Refusal(f"{choice_id} is not an open choice of lead {lead_id}")
    (choice,) = [c for c in stored_plan(db, lead_id).open_choices if c.choice_id == choice_id]
    if option not in choice.options:
        raise _Refusal(f"{option} is not an option of {choice_id}: {', '.join(choice.options)}")
    event_id = write_ruling(
        db, context, lead_id, "choice", reason, choice_id=choice_id, option=option
    )
    return _Outcome(event_id, lead_id)


def _decline_lead(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    """The underwriter's decline: the plan becomes a proposed decline with the reason as its trace and
    the decline notice is drafted by the lead's re-evaluation (A.11)."""
    lead_id, reason = _text(payload, "lead_id"), _nonempty_text(payload, "reason")
    if not _lead_exists(db, lead_id):
        raise _Refusal(f"there is no lead {lead_id}")
    if is_terminal(db, lead_id):
        raise _Refusal(f"lead {lead_id} is already final")
    return _Outcome(write_ruling(db, context, lead_id, "decline", reason), lead_id)


def _propose_command(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    """Store a card for a command the underwriter may apply and run nothing (A.11). The proposed
    command is one the underwriter submits, never `approve` or `reject`: those are the underwriter's
    own decisions. The card's command is checked in full when the underwriter applies it."""
    proposed, rationale = _text(payload, "type"), _nonempty_text(payload, "rationale")
    declared = command_class(proposed)
    if declared is None:
        raise _Refusal(f"{proposed} is not a command")
    if proposed in ("approve", "reject") or "underwriter" not in declared.actors:
        raise _Refusal(f"a proposal cannot carry {proposed}; the underwriter decides that")
    proposed_payload = payload.get("payload")
    if not isinstance(proposed_payload, dict):
        raise _Refusal("the payload needs payload, an object")
    return _Outcome(
        create_proposal(
            db,
            context,
            {"type": proposed, "payload": proposed_payload, "rationale": rationale},
            _lead_named(db, proposed_payload),
        ),
        None,
    )


def _settle(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
    *,
    approve: bool,
) -> _Outcome:
    """`approve` or `reject` of an item, by the A.11 table."""
    command = "approve" if approve else "reject"
    item = _open_item(db, payload)
    reason = _text(payload, "reason") if approve else _nonempty_text(payload, "reason")
    detail = item.detail
    if item.kind not in ("underwriter_review", "delivery_unknown"):
        raise _Refusal(f"item {item.id} is a {item.kind}, not an item to {command}")
    if payload.get("artifact_hash") is not None and not (approve and detail.item_kind == "draft"):
        raise _Refusal(f"{command} of item {item.id} carries no artifact_hash")
    if detail.item_kind == "no_contact_route":
        raise _Refusal("a missing contact route is resolved with resolve_fact on q:contact_email")
    revision, plan_hash = _lead_binding(db, item.lead_id)
    decision: ApprovalDecision = "approved" if approve else "rejected"
    artifact: Intent | None = None
    recheck: str | None = None
    if detail.item_kind == "draft":
        assert detail.intent_id is not None  # a draft item names its draft
        artifact = _intent_in_state(db, detail.intent_id, "draft")
        _settle_draft(db, context, payload, artifact, reason, approve=approve)
    elif detail.item_kind == "delivery_unknown":
        assert detail.intent_id is not None  # a delivery_unknown item names its intent
        artifact = _intent_in_state(db, detail.intent_id, "unknown")
        if approve:
            recheck = artifact.id
        else:
            close_unsent(db, context, artifact.id)
    elif detail.item_kind == "observation":
        _settle_observation(db, context, env, item, approve=approve)
    else:
        _acknowledge_review(db, context, item, approve=approve)
    event_id = _record_approval(db, context, item, decision, reason, revision, plan_hash, artifact)
    return _Outcome(event_id, item.lead_id, recheck)


def _settle_draft(
    db: sqlite3.Connection,
    context: EventContext,
    payload: Mapping[str, JsonValue],
    intent: Intent,
    reason: str,
    *,
    approve: bool,
) -> None:
    """`approve` needs the payload hash of the draft the underwriter was shown (7.4). `reject` returns
    the draft to editing: it stays a draft with its item open and loses any approval; the rejection
    of a decline notice is a ruling and the notice is replaced by the re-evaluation."""
    if approve:
        if payload.get("artifact_hash") != intent.payload_hash:
            raise _Refusal(
                "the artifact_hash is missing or is not the current payload hash of the draft"
            )
    elif intent.kind == "decline_notice":
        _reject_decline(db, context, intent.lead_id, reason)
    else:
        void_approvals(db, intent.id)


def _reject_decline(
    db: sqlite3.Connection, context: EventContext, lead_id: str, reason: str
) -> None:
    """Rejecting a decline notice overrides what proposed the decline (A.11): the underwriter's own
    decline is withdrawn, a choice whose option led straight to a decline is reopened, and every
    other declining rule is suppressed for this lead (9.6)."""
    active = active_rulings(db, lead_id)
    decline_event = next((i for i, r in active.items() if r.kind == "decline"), None)
    if decline_event is not None:
        write_ruling(db, context, lead_id, "withdrawal", reason, refers_to_event_id=decline_event)
    reopened = {
        choice for _, choices in declines_of(stored_plan(db, lead_id)) for choice in choices
    }
    for choice_id in sorted(reopened):
        (ruling_event,) = [
            i for i, r in active.items() if r.kind == "choice" and r.choice_id == choice_id
        ]
        write_ruling(
            db,
            context,
            lead_id,
            "reopened_choice",
            reason,
            choice_id=choice_id,
            refers_to_event_id=ruling_event,
        )
    suppressed = [rule for rule, choices in declines_of(stored_plan(db, lead_id)) if not choices]
    if suppressed:
        write_ruling(db, context, lead_id, "suppression", reason, suppressed_rule_ids=suppressed)


def _edit_draft(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    intent = _intent_in_state(db, _text(payload, "intent_id"), "draft")
    subject, body, reason = (
        _text(payload, "subject"),
        _text(payload, "body"),
        _text(payload, "reason"),
    )
    event_id = edit_draft(db, context, intent.id, subject, body, reason)
    return _Outcome(event_id, intent.lead_id)


def _settle_observation(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    item: Blocker,
    *,
    approve: bool,
) -> None:
    observation_id = item.detail.observation_id
    assert observation_id is not None  # an observation item names its observation
    if approve:
        approve_observation(db, context, observation_id, env.ledger_rules)
    else:
        reject_observation(db, context, observation_id)


def _acknowledge_review(
    db: sqlite3.Connection, context: EventContext, item: Blocker, *, approve: bool
) -> None:
    """A review raised by an event closes on `approve`, and the round its reply raised closes with it.
    `reject` is refused, and so is any decision on a review whose cause persists (A.11)."""
    cause = item.detail.cause
    if item.detail.cause_persists:
        raise _Refusal(
            "the cause persists; the review closes when resolve_fact supplies the fact or decline_lead ends the lead"
        )
    if not approve:
        raise _Refusal("an underwriter acts through resolve_fact, record_ruling or decline_lead")
    if cause in LATE_REPLY_CAUSES:
        reject_late_reply_values(db, item.id)
    close_blocker(db, context, item.id)
    if cause in ROUND_REVIEW_CAUSES and item.detail.intent_id is not None:
        for blocker in open_blockers(db, item.lead_id):
            if (
                blocker.kind == "producer_reply"
                and blocker.detail.intent_id == item.detail.intent_id
            ):
                close_blocker(db, context, blocker.id)


def _record_approval(
    db: sqlite3.Connection,
    context: EventContext,
    item: Blocker,
    decision: ApprovalDecision,
    reason: str,
    revision: int,
    plan_hash: str,
    artifact: Intent | None,
) -> int:
    """Write `approval_recorded` and the `approvals` row that points at it; return the event id. The
    row binds the recipient and payload hash of the `artifact` the item holds, when it holds one."""
    recipient = None if artifact is None else artifact.recipient
    artifact_hash = None if artifact is None else artifact.payload_hash
    item_kind = item.detail.item_kind
    assert (
        item_kind is not None
    )  # an underwriter_review or delivery_unknown blocker has an item kind
    event_id = append_event(
        db,
        context,
        EventType.approval_recorded,
        ApprovalRecorded(
            item_id=item.id,
            item_kind=item_kind,
            intent_id=item.detail.intent_id,
            lead_revision=revision,
            plan_hash=plan_hash,
            ruleset_hash=context.ruleset_hash,
            recipient=recipient,
            payload_hash=artifact_hash,
            decision=decision,
            reason=reason,
        ),
        lead_id=item.lead_id,
    )
    db.execute(
        "INSERT INTO approvals (lead_id, item_kind, intent_id, lead_revision, plan_hash,"
        " ruleset_hash, recipient, payload_hash, actor, decision, reason, event_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.lead_id,
            item_kind,
            item.detail.intent_id,
            revision,
            plan_hash,
            context.ruleset_hash,
            recipient,
            artifact_hash,
            context.actor,
            decision,
            reason,
            event_id,
        ),
    )
    return event_id


# A command whose handler needs something fetched before its transaction opens is built by a
# preparer, which does the fetch and returns the handler.
_PREPARERS: dict[
    str, Callable[[sqlite3.Connection, RunEnvironment, Actor, Mapping[str, JsonValue]], Handler]
] = {"deliver_reply": _read_reply_first}


def _handler_for(
    db: sqlite3.Connection,
    env: RunEnvironment,
    actor: Actor,
    command_type: str,
    payload: Mapping[str, JsonValue],
) -> Handler:
    """The handler of the command, prepared where it needs a fetch. Raises NotImplementedError for a
    type with no handler."""
    prepare = _PREPARERS.get(command_type)
    if prepare is not None:
        return prepare(db, env, actor, payload)
    handler = _HANDLERS.get(command_type)
    if handler is None:
        raise NotImplementedError(f"the {command_type} command has no handler")
    return handler


# The command types that have a handler apart from the preparers above; a type in neither raises
# NotImplementedError in `submit_command`.
_HANDLERS: dict[str, Handler] = {
    "start_run": _start_run,
    "approve": partial(_settle, approve=True),
    "reject": partial(_settle, approve=False),
    "edit_draft": _edit_draft,
    "resolve_fact": _resolve_fact,
    "record_ruling": _record_ruling,
    "decline_lead": _decline_lead,
    "propose_command": _propose_command,
}
