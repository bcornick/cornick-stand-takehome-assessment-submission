# ABOUTME: The tables built on the underwriting names: terminal statuses, status transitions, blocker priority, command classes, persisting review causes, the confirmation-only class and the reference morning.
# ABOUTME: Each table is typed with a Literal value set, those of uwh.runtime.event_types and AutonomyLevel defined here, so a name outside a set fails type checking.
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, get_args

from uwh.runtime.event_types import Actor, BlockerKind, RequestKind, ReviewCause, Status

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
)

AutonomyLevel = Literal["auto", "review", "off"]


@dataclass(frozen=True)
class CommandClass:
    """One command class. `default_level` is None where autonomy does not apply (human only)."""

    name: str
    default_level: AutonomyLevel | None
    locked: bool  # True: never runs without an underwriter approval
    actors: tuple[Actor, ...]  # who may submit it


def _human_only(name: str) -> CommandClass:
    return CommandClass(name, None, False, ("underwriter",))


COMMAND_CLASSES = (
    CommandClass("fetch_data", "auto", False, ("workflow",)),
    CommandClass("send_routine_request", "auto", False, ("workflow",)),
    CommandClass("send_sensitive_request", "review", False, ("workflow",)),
    CommandClass("send_quote_packet", "review", True, ("workflow",)),
    CommandClass("send_decline_notice", "review", True, ("workflow",)),
    CommandClass("deliver_reply", "auto", False, ("inbound", "underwriter")),
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
    CommandClass("propose_command", "auto", False, ("assistant", "mcp_client")),
)

# The review causes that persist (A.11's two review rows). An event raised every other cause:
# `approve` acknowledges it (7.3 rule 9, 7.1, 10.4 step 5, A.3, 7.4). A persistent cause is
# refused until it is removed.
PERSISTING_REVIEW_CAUSES: frozenset[ReviewCause] = frozenset(
    {"round_limit", "identity_score_missing", "identity_score_unsupported"}
)

# The class a request made only of confirmations takes. Setting it to "sensitive_request" makes an
# underwriter see confirmations first.
CONFIRMATION_ONLY_CLASS: RequestKind = "routine_request"

# The generator's reference morning, the start of simulated time.
REFERENCE_MORNING = datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
