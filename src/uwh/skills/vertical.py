# ABOUTME: The tables built on the underwriting names: terminal statuses, status transitions, blocker priority, command classes, persisting review causes, the reviews that close a round, the status a sent message gives, the rules for a servable blocker, the confirmation-only class, the order of the workflow's steps and the reference morning.
# ABOUTME: Each table is typed with a Literal value set, those of uwh.runtime.event_types, so a name outside a set fails type checking.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import get_args

from uwh.runtime.event_types import (
    Actor,
    ApprovalItemKind,
    AutonomyLevel,
    BlockerDetail,
    BlockerKind,
    RequestKind,
    ReviewCause,
    Status,
)

TERMINAL_STATUSES: tuple[Status, ...] = ("quote_sent", "declined")

# Highest priority first: the first open kind is a lead's primary next action. The order is that of
# the `BlockerKind` literal.
BLOCKER_KINDS_BY_PRIORITY: tuple[BlockerKind, ...] = get_args(BlockerKind)

# Allowed (from, to) status pairs. in_progress re-enters itself on re-evaluation.
TRANSITIONS: tuple[tuple[Status, Status], ...] = (
    ("received", "triaged"),
    ("triaged", "in_progress"),
    ("in_progress", "in_progress"),
    ("in_progress", "quote_sent"),
    ("in_progress", "declined"),
    ("received", "declined"),
    ("triaged", "declined"),
)


@dataclass(frozen=True)
class CommandClass:
    """One command class. `default_level` is None where autonomy does not apply (human only)."""

    name: str
    default_level: AutonomyLevel | None
    actors: tuple[Actor, ...]  # who may submit it


def _human_only(name: str) -> CommandClass:
    return CommandClass(name, None, ("underwriter",))


COMMAND_CLASSES = (
    CommandClass("fetch_data", "auto", ("workflow",)),
    CommandClass("send_routine_request", "auto", ("workflow",)),
    CommandClass("send_sensitive_request", "review", ("workflow",)),
    CommandClass("send_quote_packet", "review", ("workflow",)),
    CommandClass("send_decline_notice", "review", ("workflow",)),
    CommandClass("deliver_reply", "auto", ("inbound", "underwriter")),
    _human_only("approve"),
    _human_only("reject"),
    _human_only("edit_draft"),
    _human_only("resolve_fact"),
    _human_only("decline_lead"),
    _human_only("record_ruling"),
    _human_only("start_run"),
    CommandClass("propose_command", "auto", ("assistant",)),
)


def command_class(name: str) -> CommandClass | None:
    """The declared command class of that name, or None when no class has it."""
    return next((c for c in COMMAND_CLASSES if c.name == name), None)


# The review causes that persist (A.11's two review rows). An event raised every other cause:
# `approve` acknowledges it (7.3 rule 9, 7.1, 10.4 step 5, A.3, 7.4). A persistent cause is
# refused until it is removed.
PERSISTING_REVIEW_CAUSES: frozenset[ReviewCause] = frozenset(
    {"round_limit", "identity_score_missing", "identity_score_unsupported"}
)

# A.11: the approvals item kinds of an `underwriter_review` blocker.
_REVIEW_ITEM_KINDS: tuple[ApprovalItemKind, ...] = (
    "draft",
    "observation",
    "no_contact_route",
    "review",
)


def refuse_unservable_blocker(kind: BlockerKind, detail: BlockerDetail) -> None:
    """Raise ValueError for a blocker the lead detail view could not serve (A.11): the item kind, cause,
    intent, observation and choices that each kind of blocker carries. The one rule for opening a
    blocker and for serving it."""
    item_kind = detail.item_kind
    if kind == "underwriter_review":
        if item_kind not in _REVIEW_ITEM_KINDS:
            raise ValueError(f"an underwriter_review item_kind is one of {_REVIEW_ITEM_KINDS}")
    elif kind == "delivery_unknown":
        if item_kind != "delivery_unknown":
            raise ValueError("a delivery_unknown blocker has the item_kind delivery_unknown")
    elif item_kind is not None:
        raise ValueError(f"a {kind} blocker has no item_kind")
    if item_kind == "draft" and detail.intent_id is None:
        raise ValueError("a draft review names its draft: intent_id")
    if item_kind == "observation" and detail.observation_id is None:
        raise ValueError("an observation item names its observation: observation_id")
    if detail.cause_persists and item_kind != "review":
        raise ValueError("only a review holds a persistent cause: cause_persists")
    if item_kind == "review":
        if detail.cause is None:
            raise ValueError("a review has a cause")
        persists = detail.cause in PERSISTING_REVIEW_CAUSES
        if detail.cause_persists != persists:
            raise ValueError(f"cause_persists is {persists} for {detail.cause}")
    elif detail.cause is not None:
        raise ValueError("only a review has a cause")
    if kind == "underwriter_question" and not detail.choice_ids:
        raise ValueError("a question blocker names its choices: choice_ids")
    if kind != "underwriter_question" and detail.choice_ids:
        raise ValueError(f"a {kind} blocker has no choice_ids")


# The reviews a reply raises about an open round (7.3 rule 9, A.11): acknowledging one closes that round.
ROUND_REVIEW_CAUSES: tuple[ReviewCause, ...] = (
    "unread_reply",
    "off_topic_reply",
    "declining_reply",
)

# The status a lead takes when a packet or a notice is sent (A.3).
STATUS_AFTER_SEND: dict[str, Status] = {"quote_packet": "quote_sent", "decline_notice": "declined"}

# The class a request made only of confirmations takes. Setting it to "sensitive_request" makes an
# underwriter see confirmations first.
CONFIRMATION_ONLY_CLASS: RequestKind = "routine_request"

# A.10: the requests a lead may be sent before it goes to the underwriter (10.1).
MAX_REQUEST_ROUNDS = 2

# The workflow's steps in the order a lead's pass runs them (7). Each name is a skill, except
# `ask_producer`, which plans the asks, renders them and drafts the request: the three share the asks.
WORKFLOW_STEP_ORDER: tuple[str, ...] = (
    "triage_fields",
    "resolve_data",
    "evaluate_playbook",
    "ask_producer",
    "build_quote_packet",
)

# The generator's reference morning, the start of simulated time.
REFERENCE_MORNING = datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
