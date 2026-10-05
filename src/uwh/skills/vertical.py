# ABOUTME: The underwriting vertical's registration: statuses, blocker kinds, transitions, command classes and message kinds.
# ABOUTME: Plain data that the runtime reads, gathered into UNDERWRITING, the Registration the store and the runtime take their names from.
from dataclasses import dataclass
from datetime import UTC, datetime

from uwh.runtime.registration import Registration

STATUSES = ("received", "triaged", "in_progress", "quote_sent", "declined")
TERMINAL_STATUSES = ("quote_sent", "declined")

# Highest priority first: the first open kind is a lead's primary next action.
BLOCKER_KINDS_BY_PRIORITY = (
    "delivery_unknown",
    "underwriter_question",
    "underwriter_review",
    "data",
    "producer_reply",
)

# Allowed (from, to) status pairs. in_progress re-enters itself on re-evaluation.
TRANSITIONS = (
    ("received", "triaged"),
    ("triaged", "in_progress"),
    ("in_progress", "in_progress"),
    ("in_progress", "quote_sent"),
    ("in_progress", "declined"),
)

# A.1: who a blocker waits on, and the kinds of item an approval settles.
BLOCKER_OWNERS = ("underwriter", "producer", "data_team")
ITEM_KINDS = ("draft", "observation", "delivery_unknown", "no_contact_route", "review")

# 7.3: where an observation comes from.
OBSERVATION_SOURCES = ("submitted", "fetched", "derived", "assumed", "reply", "underwriter")

ACTORS = ("workflow", "underwriter", "assistant", "mcp_client", "inbound")
AUTONOMY_LEVELS = ("auto", "review", "off")


@dataclass(frozen=True)
class CommandClass:
    """One command class. `default_level` is None where autonomy does not apply (human only)."""

    name: str
    default_level: str | None
    locked: bool  # True: never runs without an underwriter approval
    human_only: bool
    actors: tuple[str, ...]  # who may submit it


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

# The intent kinds; each is one section 10.1 message class.
MESSAGE_KINDS = ("routine_request", "sensitive_request", "quote_packet", "decline_notice")

# What raised an `underwriter_review` item of item kind `review`, with whether the cause persists
# (A.11's two review rows). An event raised a cause that does not persist: `approve` acknowledges it
# (7.3 rule 9, 7.1, 10.4 step 5, A.3, 7.4). A persistent cause is refused until it is removed.
REVIEW_CAUSES = (
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

# The class a request made only of confirmations takes: "routine_request" or "sensitive_request".
# Setting it to "sensitive_request" makes an underwriter see confirmations first.
CONFIRMATION_ONLY_CLASS = "routine_request"

# The generator's reference morning, the start of simulated time.
REFERENCE_MORNING = datetime(2026, 6, 29, 8, 0, tzinfo=UTC)

# The names the runtime reads (7): the lists above, and the name this vertical gives each role.
UNDERWRITING = Registration(
    statuses=STATUSES,
    terminal_statuses=TERMINAL_STATUSES,
    transitions=TRANSITIONS,
    blocker_kinds_by_priority=BLOCKER_KINDS_BY_PRIORITY,
    blocker_owners=BLOCKER_OWNERS,
    message_kinds=MESSAGE_KINDS,
    item_kinds=ITEM_KINDS,
    observation_sources=OBSERVATION_SOURCES,
    delivery_unknown_kind="delivery_unknown",
    human_review_kind="underwriter_review",
    data_kind="data",
    human_owner="underwriter",
    data_owner="data_team",
    draft_item_kind="draft",
    observation_item_kind="observation",
    delivery_unknown_item_kind="delivery_unknown",
    review_item_kind="review",
    human_source="underwriter",
)
