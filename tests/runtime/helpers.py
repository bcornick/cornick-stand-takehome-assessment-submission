# ABOUTME: The constants the runtime tests share: the run start, the ruleset hash, the lead and its plan, and the skill that drafts every kind of message.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
from datetime import UTC, datetime

from uwh.skills.manifest import SkillManifest

RUN_START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
RULESET = "r" * 64
LEAD_ID = "L-1"
PLAN_HASH = "p" * 64
REVISION = 3
# The skill that issues every send class.
ASKER = SkillManifest(
    name="asker",
    version="1",
    purpose="Drafts the messages a lead needs.",
    trigger="a fact is missing or a decision is made",
    command_classes=[
        "send_routine_request",
        "send_sensitive_request",
        "send_quote_packet",
        "send_decline_notice",
    ],
    fallback="none",
    pass_threshold=1.0,
)
