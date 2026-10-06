# ABOUTME: The graders of what the producer receives and where each lead stands: Coverage, One open request, Asks in both directions, Forbidden asks and Packet fidelity (section 13.3).
# ABOUTME: Each reads the mailbox and the application database through the evidence, and the expectations of the phase where the check is against a label.
from evals.graders.evidence import (
    Evidence,
    Expectations,
    Result,
    ask_classes,
    delivered_asks,
    duplicate_sends,
    field_asks,
    lead_ids,
    messages,
    plan_of,
    status_of,
)
from uwh.rules.models import (
    AdvisoryEffect,
    CoverageAdjustmentEffect,
    ExclusionOrEndorsementEffect,
    ObligationEffect,
    PlannedEffect,
    RequirementEffect,
    SurchargeEffect,
)
from uwh.runtime.event_types import REQUEST_KINDS
from uwh.runtime.waits import open_blockers, primary_next_action
from uwh.skills.vertical import TERMINAL_STATUSES

# The sections of a quote packet, by the label's name for them; each opens with this heading.
PACKET_HEADINGS = {
    "surcharges": "Surcharges",
    "coverage_adjustments": "Coverage adjustments",
    "requirements": "Requirements",
    "exclusions_and_endorsements": "Exclusions and endorsements",
    "advisories": "Advisories",
    "obligations": "Obligations after binding",
}


def outcome_of(ev: Evidence, lead_id: str) -> str:
    """Where the lead stands, in the label's terms: `quote_sent`, `proposed_decline`,
    `underwriter_card`, `request_sent`, or `none`."""
    if status_of(ev, lead_id) == "quote_sent":
        return "quote_sent"
    plan = plan_of(ev, lead_id)
    if plan is not None and plan.proposed_decline:
        return "proposed_decline"
    if any(b.kind == "underwriter_question" for b in open_blockers(ev.db, lead_id)):
        return "underwriter_card"
    if messages(ev, lead_id, REQUEST_KINDS):
        return "request_sent"
    return "none"


def open_items(ev: Evidence, lead_id: str) -> set[str]:
    """The underwriter's open items in the label's terms: the choice ids of an open question card,
    `decline_notice` for a decline notice awaiting approval, and the cause of an open review."""
    items: set[str] = set()
    for blocker in open_blockers(ev.db, lead_id):
        detail = blocker.detail
        items |= set(detail.choice_ids)
        if detail.item_kind == "review" and detail.cause is not None:
            items.add(detail.cause)
        if detail.item_kind == "draft" and detail.intent_id is not None:
            (kind,) = ev.db.execute(
                "SELECT kind FROM intents WHERE id = ?", (detail.intent_id,)
            ).fetchone()
            if kind == "decline_notice":
                items.add(kind)
    return items


def coverage(ev: Evidence, expected: Expectations) -> Result:
    """Every lead has a primary next action or is terminal, none is skipped, and each lead the labels
    describe is at the labelled status and outcome, with the labelled open items and the labelled
    not-evaluated notes."""
    held = lead_ids(ev)
    failures = [
        f"{lead_id} has no next action and is not terminal"
        for lead_id in held
        if status_of(ev, lead_id) not in TERMINAL_STATUSES
        and primary_next_action(ev.db, lead_id) is None
    ]
    for lead_id, expectation in expected.items():
        if lead_id not in held:
            failures.append(f"{lead_id} is skipped")
            continue
        for name, found in (
            ("status", status_of(ev, lead_id)),
            ("outcome", outcome_of(ev, lead_id)),
        ):
            if expectation[name] != found:
                failures.append(f"{lead_id} {name} is {found}, expected {expectation[name]}")
        plan = plan_of(ev, lead_id)
        for key, what, held_now in (
            ("underwriter_items", "open item", open_items(ev, lead_id)),
            (
                "not_evaluated",
                "not-evaluated note",
                {n.ref for n in plan.not_evaluated} if plan is not None else set(),
            ),
        ):
            if key in expectation:
                failures += _differences(what, lead_id, set(expectation[key]), held_now)
    return Result(failures)


def one_open_request(ev: Evidence, expected: Expectations) -> Result:
    """At most one unanswered request per lead, and no duplicate as section 7.5 defines it."""
    failures = duplicate_sends(ev)
    for lead_id in lead_ids(ev):
        waiting = [b for b in open_blockers(ev.db, lead_id) if b.kind == "producer_reply"]
        if len(waiting) > 1:
            failures.append(f"{lead_id} has {len(waiting)} unanswered requests")
    return Result(failures)


def _differences(what: str, lead_id: str, expected: set[str], found: set[str]) -> list[str]:
    return [f"{lead_id}: {what} {name} is missing" for name in sorted(expected - found)] + [
        f"{lead_id}: {what} {name} is extra" for name in sorted(found - expected)
    ]


def asks(ev: Evidence, expected: Expectations) -> Result:
    """The asks delivered since the last phase equal the labelled ones: field asks, confirmations and
    catalogue questions, none missing and none extra. A label whose `request` is null expects no request."""
    confirmations, catalogue = ask_classes()
    failures: list[str] = []
    for lead_id, expectation in expected.items():
        if "request" not in expectation:
            continue
        request = expectation["request"] or {}
        got = delivered_asks(ev, lead_id, new_only=True)
        for what, wanted, found in (
            ("ask", request.get("asks", []), field_asks(got)),
            ("confirmation", request.get("confirmations", []), got & confirmations),
            ("catalogue question", request.get("catalogue_questions", []), got & catalogue),
        ):
            failures += _differences(what, lead_id, set(wanted), found)
        kinds = {m["metadata"]["kind"] for m in messages(ev, lead_id, REQUEST_KINDS, new_only=True)}
        if request and kinds != {request["kind"]}:
            failures.append(f"{lead_id}: request kinds {sorted(kinds)}, expected {request['kind']}")
    return Result(failures)


def forbidden_asks(ev: Evidence, expected: Expectations) -> Result:
    """No delivered request asks for a field the system owns or one the label lists as not to be
    asked (bind only, fetched, blocked, derived, an inactive condition, never asked)."""
    failures: list[str] = []
    for lead_id in lead_ids(ev):
        got = field_asks(delivered_asks(ev, lead_id))
        failures += [
            f"{lead_id}: asked {name}, which the system owns"
            for name in sorted(got)
            if name in ev.registry and not ev.registry[name].producer_editable
        ]
        forbidden = set(expected.get(lead_id, {}).get("not_asked", {}))
        failures += [
            f"{lead_id}: asked {name}, labelled not asked" for name in sorted(got & forbidden)
        ]
    return Result(failures)


def _in_packet(effect: PlannedEffect) -> str | None:
    """What the packet must carry of the effect, or None for an effect the packet leaves out."""
    match effect.effect:
        case RequirementEffect() | ExclusionOrEndorsementEffect() | ObligationEffect():
            return f"- {effect.effect.text}"
        case AdvisoryEffect() if not effect.effect.internal:
            return f"- {effect.effect.text}"
        case SurchargeEffect():
            return f"- {effect.effect.percent}% surcharge"
        case CoverageAdjustmentEffect():
            return f"proposed ${int(effect.effect.proposed_value):,}"
        case _:
            return None


def missing_from_packets(ev: Evidence) -> list[PlannedEffect]:
    """The committed effects of a plan that a delivered packet to its lead does not carry."""
    missing: list[PlannedEffect] = []
    for lead_id in lead_ids(ev):
        plan = plan_of(ev, lead_id)
        for message in messages(ev, lead_id, ("quote_packet",)):
            for planned in plan.effects if plan is not None else []:
                carried = _in_packet(planned)
                if planned.committed and carried is not None and carried not in message["body"]:
                    missing.append(planned)
    return missing


def packet_fidelity(ev: Evidence, expected: Expectations) -> Result:
    """Every committed, non-internal effect of the plan appears in the delivered packet; where a label
    describes the packet, its coverages and not-evaluated notes appear and its empty sections do not."""
    failures = [
        f"a delivered packet lacks {planned.effect.type} {planned.effect.rule}"
        for planned in missing_from_packets(ev)
    ]
    for lead_id, expectation in expected.items():
        labelled = expectation.get("packet")
        if labelled is None:
            continue
        sent = messages(ev, lead_id, ("quote_packet",))
        if not sent:
            failures.append(f"{lead_id}: no packet was delivered")
            continue
        body = sent[0]["body"]
        plan = plan_of(ev, lead_id)
        notes = {n.ref: n.producer_text for n in plan.not_evaluated} if plan else {}
        failures += [
            f"{lead_id}: the packet lacks coverage {name} {value}"
            for name, value in labelled["coverages"].items()
            if f"- {ev.registry[name].label}: ${int(value):,}" not in body
        ]
        failures += [
            f"{lead_id}: the packet lacks the note for {ref}"
            for ref in labelled["not_evaluated"]
            if notes.get(ref, ref) not in body
        ]
        failures += [
            f"{lead_id}: the packet has a {heading} section the label leaves empty"
            for key, heading in PACKET_HEADINGS.items()
            if not labelled[key] and f"\n{heading}\n" in f"\n{body}"
        ]
    return Result(failures)
