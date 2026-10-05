# ABOUTME: The command layer of 7.4 and A.11: one entry point that takes the actor from the transport, applies the actor and class rules and the skill manifest, runs the handler and the lead's re-evaluation in one transaction, and writes `command_refused` for a refusal.
# ABOUTME: Handlers exist for resolve_fact, approve and reject of an observation or an event-raised review, and record_ruling; every other command class raises NotImplementedError after the checks.
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from uwh.runtime.event_types import (
    Actor,
    ApprovalDecision,
    ApprovalRecorded,
    CommandRefused,
    EventType,
    RulingRecorded,
)
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.facts import (
    LedgerRules,
    approve_observation,
    reject_late_reply_values,
    reject_observation,
    resolve_fact,
)
from uwh.runtime.runs import command_context
from uwh.runtime.waits import Blocker, close_blocker, open_blockers
from uwh.runtime.workflow import Step, run_steps, unit_of_work
from uwh.settings import RunMode
from uwh.skills.manifest import SkillFolderError, load_manifest
from uwh.skills.vertical import (
    COMMAND_CLASSES,
    HELD_DRAFT_CAUSES,
    TERMINAL_STATUSES,
)

# The reviews raised by a reply that arrived after its round closed or after the lead's final status
# (7.3 rule 9): acknowledging one rejects that reply's pending values.
_LATE_REPLY_CAUSES = ("late_reply", "reply_after_terminal_status")


@dataclass(frozen=True)
class CommandEnvironment:
    """What the command layer needs from its caller: the run mode, the active ruleset hash, the ledger
    rules and workflow steps a re-evaluation uses, the folder that holds the skills and the real clock."""

    mode: RunMode
    ruleset_hash: str
    ledger_rules: LedgerRules
    steps: Sequence[Step]
    skills_root: Path
    now: Callable[[], datetime]


@dataclass(frozen=True)
class CommandResult:
    """The A.11 response. `event_id` is the event the command produced, or the `command_refused` event."""

    accepted: bool
    event_id: int
    reason: str | None


@dataclass(frozen=True)
class _Outcome:
    event_id: int
    lead_id: str


class _Refusal(Exception):
    """A command the layer refuses; the message is the reason."""


Handler = Callable[
    [sqlite3.Connection, EventContext, CommandEnvironment, Mapping[str, JsonValue]], _Outcome
]


def submit_command(
    db: sqlite3.Connection,
    env: CommandEnvironment,
    actor: Actor,
    command_type: str,
    payload: Mapping[str, JsonValue],
    *,
    skill: str | None = None,
) -> CommandResult:
    """Apply one command. `actor` is the transport's binding, never a payload value; `skill` names the
    issuing skill of a `workflow` command.

    An accepted command and the re-evaluation of its lead commit together. A refusal rolls back
    whatever the handler wrote and commits one `command_refused` event. A command type whose handler
    is not built raises NotImplementedError after the checks, writing nothing.
    """
    context = command_context(db, actor, env.mode, env.ruleset_hash, env.now())
    reason = _gate(env, actor, skill, command_type, payload)
    if reason is None:
        handler = _HANDLERS.get(command_type)
        if handler is None:
            raise NotImplementedError(f"the {command_type} command is not built")
        try:
            with unit_of_work(db):
                outcome = handler(db, context, env, payload)
                _reevaluate(db, env, outcome.lead_id)
            return CommandResult(True, outcome.event_id, None)
        except _Refusal as refusal:
            reason = str(refusal)
    with unit_of_work(db):
        event_id = append_event(
            db,
            context,
            EventType.command_refused,
            CommandRefused(command_type=command_type, command_payload=dict(payload), reason=reason),
            lead_id=_lead_named(db, payload),
        )
    return CommandResult(False, event_id, reason)


def _gate(
    env: CommandEnvironment,
    actor: Actor,
    skill: str | None,
    command_type: str,
    payload: Mapping[str, JsonValue],
) -> str | None:
    """The reason the actor may not submit the command, or None. The actor comes from the transport (7.4)."""
    if "actor" in payload:
        return "the payload names no actor; the transport binds it"
    declared = next((c for c in COMMAND_CLASSES if c.name == command_type), None)
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
    if command_type not in manifest.command_classes:
        return f"the manifest of {skill} does not declare {command_type}"
    return None


def _lead_named(db: sqlite3.Connection, payload: Mapping[str, JsonValue]) -> str | None:
    """The lead a command's payload names, directly or through its item, for the event of a refusal."""
    lead_id = payload.get("lead_id")
    if isinstance(lead_id, str):
        return lead_id
    item_id = payload.get("item_id")
    if isinstance(item_id, int) and not isinstance(item_id, bool):
        row = db.execute("SELECT lead_id FROM blockers WHERE id = ?", (item_id,)).fetchone()
        return None if row is None else str(row[0])
    return None


def _reevaluate(db: sqlite3.Connection, env: CommandEnvironment, lead_id: str) -> None:
    """Every accepted command re-evaluates its lead in the command's transaction (A.11) unless the
    lead is terminal. A re-evaluation builds drafts and dispatches nothing."""
    if _lead_status(db, lead_id) in TERMINAL_STATUSES:
        return
    run_steps(
        db,
        lambda: command_context(db, "workflow", env.mode, env.ruleset_hash, env.now()),
        lead_id,
        env.steps,
    )


def _lead_status(db: sqlite3.Connection, lead_id: str) -> str:
    row = db.execute("SELECT status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if row is None:
        raise _Refusal(f"there is no lead {lead_id}")
    return str(row[0])


def _lead_binding(db: sqlite3.Connection, lead_id: str) -> tuple[int, str]:
    """The lead's revision and plan hash now."""
    _lead_status(db, lead_id)
    revision, plan_hash = db.execute(
        "SELECT revision, plan_hash FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    if plan_hash is None:
        raise _Refusal(f"lead {lead_id} has no plan to decide against")
    return int(revision), str(plan_hash)


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


def _open_item(db: sqlite3.Connection, payload: Mapping[str, JsonValue]) -> Blocker:
    """The open blocker `item_id` names (A.11)."""
    item_id = payload.get("item_id")
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        raise _Refusal("the payload needs item_id, an integer")
    row = db.execute("SELECT lead_id FROM blockers WHERE id = ?", (item_id,)).fetchone()
    if row is not None:
        for blocker in open_blockers(db, row[0]):
            if blocker.id == item_id:
                return blocker
    raise _Refusal(f"item {item_id} is not an open item")


# ---- handlers -----------------------------------------------------------------------------------


def _resolve_fact(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    lead_id, key = _text(payload, "lead_id"), _text(payload, "key")
    reason = _text(payload, "reason")
    if "value" not in payload:
        raise _Refusal("the payload needs value")
    _lead_status(db, lead_id)
    resolve_fact(db, context, lead_id, key, payload["value"], reason, env.ledger_rules)
    (event_id,) = db.execute(
        "SELECT event_id FROM observations"
        " WHERE lead_id = ? AND key = ? AND source = 'underwriter' ORDER BY id DESC LIMIT 1",
        (lead_id, key),
    ).fetchone()
    return _Outcome(event_id, lead_id)


def _record_ruling(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
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


def _approve(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    return _settle(db, context, env, payload, approve=True)


def _reject(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
    payload: Mapping[str, JsonValue],
) -> _Outcome:
    return _settle(db, context, env, payload, approve=False)


def _settle(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
    payload: Mapping[str, JsonValue],
    *,
    approve: bool,
) -> _Outcome:
    """`approve` or `reject` of an item that holds no draft, by the A.11 table. An item that holds a
    draft, and `delivery_unknown`, raise NotImplementedError."""
    command = "approve" if approve else "reject"
    item = _open_item(db, payload)
    reason = _text(payload, "reason") if approve else _nonempty_text(payload, "reason")
    detail = item.detail
    if item.kind == "delivery_unknown" or detail.item_kind == "draft":
        raise NotImplementedError(f"{command} of a {detail.item_kind} item")
    if item.kind != "underwriter_review":
        raise _Refusal(f"item {item.id} is a {item.kind}, not an item to {command}")
    if payload.get("artifact_hash") is not None:
        raise _Refusal(f"item {item.id} holds no draft, so {command} carries no artifact_hash")
    if detail.item_kind == "no_contact_route":
        raise _Refusal("a missing contact route is resolved with resolve_fact on q:contact_email")
    revision, plan_hash = _lead_binding(db, item.lead_id)
    if detail.item_kind == "observation":
        _settle_observation(db, context, env, item, approve=approve)
    else:
        _acknowledge_review(db, context, item, approve=approve)
    event_id = _record_approval(
        db, context, item, "approved" if approve else "rejected", reason, revision, plan_hash
    )
    return _Outcome(event_id, item.lead_id)


def _settle_observation(
    db: sqlite3.Connection,
    context: EventContext,
    env: CommandEnvironment,
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
    """A review raised by an event closes on `approve`. `reject` is refused, and so is any decision on
    a review whose cause persists (A.11)."""
    cause = item.detail.cause
    if item.detail.cause_persists:
        raise _Refusal(
            "the cause persists; the review closes when resolve_fact supplies the fact or decline_lead ends the lead"
        )
    if not approve:
        raise _Refusal("an underwriter acts through resolve_fact, record_ruling or decline_lead")
    if cause in HELD_DRAFT_CAUSES:
        raise NotImplementedError(f"approve of a {cause} review")
    if cause in _LATE_REPLY_CAUSES:
        reject_late_reply_values(db, item.id)
    close_blocker(db, context, item.id)


def _record_approval(
    db: sqlite3.Connection,
    context: EventContext,
    item: Blocker,
    decision: ApprovalDecision,
    reason: str,
    revision: int,
    plan_hash: str,
) -> int:
    """Write `approval_recorded` and the `approvals` row that points at it; return the event id. The item
    holds no draft, so the row has no recipient or payload hash."""
    item_kind = item.detail.item_kind
    assert item_kind is not None  # an underwriter_review blocker has an item kind
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
            recipient=None,
            payload_hash=None,
            decision=decision,
            reason=reason,
        ),
        lead_id=item.lead_id,
    )
    db.execute(
        "INSERT INTO approvals (lead_id, item_kind, intent_id, lead_revision, plan_hash,"
        " ruleset_hash, recipient, payload_hash, actor, decision, reason, event_id)"
        " VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
        (
            item.lead_id,
            item_kind,
            item.detail.intent_id,
            revision,
            plan_hash,
            context.ruleset_hash,
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
    "approve": _approve,
    "reject": _reject,
    "resolve_fact": _resolve_fact,
    "record_ruling": _record_ruling,
}
