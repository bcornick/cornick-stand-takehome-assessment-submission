# ABOUTME: The command layer of 7.4 and A.11: one entry point that takes the actor from the transport, applies the actor and class rules and the skill manifest, runs the handler and the lead's re-evaluation in one transaction, and writes `command_refused` for a refusal.
# ABOUTME: The handlers are start_run, resolve_fact, edit_draft, record_ruling, and approve and reject of an observation, a draft, a delivery_unknown item or an event-raised review; a command class with no handler raises NotImplementedError after the checks.
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial

from pydantic import JsonValue

from uwh.runtime.event_types import (
    Actor,
    ApprovalDecision,
    ApprovalRecorded,
    CommandRefused,
    EventType,
    IntentState,
    RulingRecorded,
)
from uwh.runtime.events import EventContext, MakeContext, StaleRun, append_event
from uwh.runtime.facts import (
    LATE_REPLY_CAUSES,
    approve_observation,
    reject_late_reply_values,
    reject_observation,
    resolve_fact,
)
from uwh.runtime.policy import manifest_refusal
from uwh.runtime.runs import RunEnvironment, begin_run, command_context, current_run, pass_context
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
from uwh.runtime.waits import Blocker, close_blocker, open_blocker_by_id, open_blockers
from uwh.runtime.workflow import lead_revision_and_plan_hash, reevaluate, unit_of_work
from uwh.skills.manifest import SkillFolderError, load_manifest
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
    *,
    skill: str | None = None,
) -> CommandResult:
    """Apply one command. `actor` is the transport's binding, never a payload value; `skill` names the
    issuing skill of a `workflow` command.

    An accepted command and the re-evaluation of its lead commit together; after that commit the
    lead's drafts that can go are dispatched, as the run the command ran in; when a start has replaced
    that run, nothing is sent and the command is still accepted (A.11, 14). A refusal rolls back whatever the handler wrote
    and commits one `command_refused` event. A command type with no handler raises
    NotImplementedError after the checks, writing nothing.
    """
    if db.in_transaction:
        raise RuntimeError(
            "a command opens its own transaction, so the connection must not be in one"
        )
    reason = _gate(env, actor, skill, command_type, payload)
    if reason is None:
        handler = _HANDLERS.get(command_type)
        if handler is None:
            raise NotImplementedError(f"the {command_type} command has no handler")
        try:
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


def _gate(
    env: RunEnvironment,
    actor: Actor,
    skill: str | None,
    command_type: str,
    payload: Mapping[str, JsonValue],
) -> str | None:
    """The reason the actor may not submit the command, or None. The actor comes from the transport (7.4)."""
    if "actor" in payload:
        return "the payload names no actor; the transport binds it"
    declared = command_class(command_type)
    if declared is None:
        return f"{command_type} is not a command"
    if actor not in declared.actors:
        return f"{actor} may not submit {command_type}"
    if actor != "workflow":
        return None
    if skill is None:
        return f"a workflow {command_type} names the skill that issues it"
    try:
        manifest = load_manifest(env.skills_root / skill)
    except SkillFolderError as error:
        return str(error)
    return manifest_refusal(manifest, command_type)


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
    return _Outcome(begin_run(db, context, env.leadgen, env.mailbox, seed, env.ledger_rules), None)


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
    revision, plan_hash = _lead_binding(db, lead_id)
    if not any(
        b.kind == "underwriter_question" and choice_id in b.detail.choice_ids
        for b in open_blockers(db, lead_id)
    ):
        raise _Refusal(f"{choice_id} is not an open choice of lead {lead_id}")
    event_id = append_event(
        db,
        context,
        EventType.ruling_recorded,
        RulingRecorded(
            kind="choice",
            choice_id=choice_id,
            option=option,
            reason=reason,
            lead_revision=revision,
            plan_hash=plan_hash,
            suppressed_rule_ids=[],
            refers_to_event_id=None,
        ),
        lead_id=lead_id,
    )
    return _Outcome(event_id, lead_id)


def _settle(
    db: sqlite3.Connection,
    context: EventContext,
    env: RunEnvironment,
    payload: Mapping[str, JsonValue],
    *,
    approve: bool,
) -> _Outcome:
    """`approve` or `reject` of an item, by the A.11 table. `reject` of a draft decline notice raises
    NotImplementedError."""
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
        _settle_draft(db, payload, artifact, approve=approve)
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
    db: sqlite3.Connection, payload: Mapping[str, JsonValue], intent: Intent, *, approve: bool
) -> None:
    """`approve` needs the payload hash of the draft the underwriter was shown (7.4). `reject` returns
    the draft to editing: it stays a draft with its item open and loses any approval."""
    if approve:
        if payload.get("artifact_hash") != intent.payload_hash:
            raise _Refusal(
                "the artifact_hash is missing or is not the current payload hash of the draft"
            )
    elif intent.kind == "decline_notice":
        raise NotImplementedError("reject of a draft decline notice")
    else:
        void_approvals(db, intent.id)


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


# The one place that lists which command types have a handler; a type absent here raises
# NotImplementedError in `submit_command`.
_HANDLERS: dict[str, Handler] = {
    "start_run": _start_run,
    "approve": partial(_settle, approve=True),
    "reject": partial(_settle, approve=False),
    "edit_draft": _edit_draft,
    "resolve_fact": _resolve_fact,
    "record_ruling": _record_ruling,
}
