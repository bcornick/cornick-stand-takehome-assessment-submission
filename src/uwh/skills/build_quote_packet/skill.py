# ABOUTME: The build_quote_packet skill (10.5): the quote packet rendered in code from the action plan: coverages as submitted, each effect on its own line with its deadline, and a note for each page not evaluated. No price and no rule id.
# ABOUTME: Deterministic. The skill refuses a plan that holds a decline, an undecided page, an open choice or a catalogue question, since the workflow builds a packet only when none of those remain (9.6).
from pydantic import JsonValue

from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    CoverageAdjustmentEffect,
    Deadline,
    DeclineEffect,
    Effect,
    ExclusionOrEndorsementEffect,
    NoActionEffect,
    ObligationEffect,
    RequirementEffect,
    StrictModel,
    SurchargeEffect,
)

OPENING = "Thank you for your submission. Your quote is set out below."

# When a requirement is due.
_DUE_TEXT: dict[Deadline, str] = {
    Deadline.within_60_days: "within 60 days",
    Deadline.first_term: "within the first term",
    Deadline.underwriting_period: "within the underwriting period",
    Deadline.within_30_days_of_bind: "within 30 days of bind",
    Deadline.duration_of_non_occupancy: "for the duration of non-occupancy",
}
# How long a surcharge or a coverage adjustment lasts.
_DURATION_TEXT: dict[Deadline, str] = {
    Deadline.first_term: "for the first term",
    Deadline.underwriting_period: "for the underwriting period",
    Deadline.duration_of_non_occupancy: "for the duration of non-occupancy",
}


class Coverage(StrictModel):
    label: str
    value: JsonValue


class BuildQuotePacketInput(StrictModel):
    lead_label: str  # the property address, or the short lead id (LEAD-001) when there is none
    plan: ActionPlan
    coverages: dict[str, Coverage]  # the submitted coverages by field name, in the order shown


class BuildQuotePacketOutput(StrictModel):
    subject: str
    body: str


# The sections of the packet in the order it shows them.
_HEADINGS = (
    "Surcharges",
    "Coverage adjustments",
    "Requirements",
    "Exclusions and endorsements",
    "Advisories",
    "Obligations after binding",
)


def _dollars(value: JsonValue) -> str:
    """A coverage amount, which the registry holds as an integer or as digits, as `$875,000`."""
    return f"${int(str(value)):,}"


def _after(deadline: Deadline | None, wording: dict[Deadline, str]) -> str:
    return "" if deadline is None else f" ({wording[deadline]})"


def _entry(effect: Effect, coverages: dict[str, Coverage]) -> tuple[str, str] | None:
    """The section an effect belongs to and its line; None for an effect that adds nothing to the
    producer's packet: a no_action, and an advisory for the underwriter alone. No rule id is shown:
    the rule trace is the internal view's."""
    match effect:
        case SurchargeEffect():
            return (
                "Surcharges",
                f"{effect.percent}% surcharge{_after(effect.deadline, _DURATION_TEXT)}",
            )
        case CoverageAdjustmentEffect():
            submitted = coverages.get(effect.field)
            label = effect.field if submitted is None else submitted.label
            shown = "" if submitted is None else f"submitted {_dollars(submitted.value)}, "
            return (
                "Coverage adjustments",
                f"{label}: {shown}proposed {_dollars(effect.proposed_value)}{_after(effect.deadline, _DURATION_TEXT)}",
            )
        case RequirementEffect():
            return "Requirements", f"{effect.text}{_after(effect.deadline, _DUE_TEXT)}"
        case ExclusionOrEndorsementEffect():
            return "Exclusions and endorsements", effect.text
        case AdvisoryEffect():
            return None if effect.internal else ("Advisories", effect.text)
        case ObligationEffect():
            return "Obligations after binding", f"{effect.text} {effect.trigger}."
        case NoActionEffect():
            return None
        case DeclineEffect():
            raise ValueError("a quote packet holds no decline")


def is_ready(plan: ActionPlan) -> bool:
    """Whether the plan can be a quote packet: no decline, no undecided page, no open choice, no
    catalogue question and every effect committed (9.6)."""
    return not (
        plan.proposed_decline
        or plan.undecided
        or plan.open_choices
        or plan.catalogue_questions
        or not all(planned.committed for planned in plan.effects)
    )


def run(input: BuildQuotePacketInput) -> BuildQuotePacketOutput:
    plan = input.plan
    if not is_ready(plan):
        raise ValueError("a quote packet is built only from a plan with nothing declined or open")
    sections: dict[str, list[str]] = {heading: [] for heading in _HEADINGS}
    for planned in plan.effects:
        entry = _entry(planned.effect, input.coverages)
        if entry is not None:
            heading, line = entry
            sections[heading].append(f"- {line}")
    blocks = [
        OPENING,
        "\n".join(
            [
                "Coverages as submitted",
                *(f"- {c.label}: {_dollars(c.value)}" for c in input.coverages.values()),
            ]
        ),
        *("\n".join([heading, *lines]) for heading, lines in sections.items() if lines),
    ]
    if plan.not_evaluated:
        blocks.append(
            "\n".join(["Not reviewed", *(f"- {note.producer_text}" for note in plan.not_evaluated)])
        )
    return BuildQuotePacketOutput(
        subject=f"Your quote: {input.lead_label}", body="\n\n".join(blocks)
    )
