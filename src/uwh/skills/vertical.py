# ABOUTME: The tables built on the underwriting names: status transitions, blocker priority, command classes, review causes, the confirmation-only class and the reference morning.
# ABOUTME: Each table is typed with the Literal value sets of uwh.runtime.event_types, so a name outside a set fails type checking.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from uwh.runtime.event_types import Actor, BlockerKind, ReviewCause, Status

TERMINAL_STATUSES: tuple[Status, ...] = ("quote_sent", "declined")

# Highest priority first: the first open kind is a lead's primary next action.
BLOCKER_KINDS_BY_PRIORITY: tuple[BlockerKind, ...] = (
    "delivery_unknown",
    "underwriter_question",
    "underwriter_review",
    "data",
    "producer_reply",
)

# Allowed (from, to) status pairs. in_progress re-enters itself on re-evaluation.
TRANSITIONS: tuple[tuple[Status, Status], ...] = (
    ("received", "triaged"),
    ("triaged", "in_progress"),
    ("in_progress", "in_progress"),
    ("in_progress", "quote_sent"),
    ("in_progress", "declined"),
)

AutonomyLevel = Literal["auto", "review", "off"]


@dataclass(frozen=True)
class CommandClass:
    """One command class. `default_level` is None where autonomy does not apply (human only)."""

    name: str
    default_level: AutonomyLevel | None
    locked: bool  # True: never runs without an underwriter approval
    human_only: bool
    actors: tuple[Actor, ...]  # who may submit it


def _human_only(name: str) -> CommandClass:
    return CommandClass(name, None, False, True, ("underwriter",))


COMMAND_CLASSES = (
    CommandClass("fetch_data", "auto", False, False, ("workflow",)),
    CommandClass("send_routine_request", "auto", False, False, ("workflow",)),
    CommandClass("send_sensitive_request", "review", False, False, ("workflow",)),
    CommandClass("send_quote_packet", "review", True, False, ("workflow",)),
    CommandClass("send_decline_notice", "review", True, False, ("workflow",)),
    CommandClass("deliver_reply", "auto", False, False, ("inbound", "underwriter")),
    _human_only("approve"),
    _human_only("reject"),
    _human_only("edit_draft"),
    _human_only("resolve_fact"),
    _human_only("decline_lead"),
    _human_only("record_ruling"),
    _human_only("propose_rule_change"),
    _human_only("apply_rule_change"),
    _human_only("change_setting"),
    _human_only("emergency_stop"),
    _human_only("start_run"),
    CommandClass("propose_command", "auto", False, False, ("assistant", "mcp_client")),
)

# What raised an `underwriter_review` item of item kind `review`, with whether the cause persists
# (A.11's two review rows). An event raised a cause that does not persist: `approve` acknowledges it
# (7.3 rule 9, 7.1, 10.4 step 5, A.3, 7.4). A persistent cause is refused until it is removed.
REVIEW_CAUSES: tuple[tuple[ReviewCause, bool], ...] = (
    ("late_reply", False),
    ("unread_reply", False),
    ("off_topic_reply", False),
    ("declining_reply", False),
    ("reply_after_terminal_status", False),
    ("draft_held_by_stop", False),
    ("draft_held_class_off", False),
    ("round_limit", True),
    ("identity_score_missing", True),
    ("identity_score_unsupported", True),
)

# The class a request made only of confirmations takes. Setting it to "sensitive_request" makes an
# underwriter see confirmations first.
CONFIRMATION_ONLY_CLASS: Literal["routine_request", "sensitive_request"] = "routine_request"

# The generator's reference morning, the start of simulated time.
REFERENCE_MORNING = datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
