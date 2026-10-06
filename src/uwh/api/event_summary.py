# ABOUTME: The narrative sentence of an event payload (section 11): what happened, its result and what follows, one per event type, shown as a timeline bullet and read by the chat assistant.
# ABOUTME: A field is named by its key; values are words and numbers. A sentence has no full stop unless it holds two; there is no `name: value` dump, no JSON and no object repr.
from collections import Counter

from pydantic import JsonValue

from uwh.providers.models import ProviderResult
from uwh.rules.models import StrictModel
from uwh.runtime.event_types import (
    ApprovalRecorded,
    BlockerClosed,
    BlockerOpened,
    CommandRefused,
    ConflictClosed,
    ConflictOpened,
    DeliveryUnknown,
    DraftEdited,
    FactObserved,
    FactSelected,
    FaultInjected,
    IntentCreated,
    LeadReceived,
    MessageSent,
    ModelCalled,
    PlanBuilt,
    ProposalCreated,
    ProviderCalled,
    ReplayMiss,
    ReplyRead,
    ReplyReceived,
    RulingRecorded,
    RunStarted,
    SkillFallbackUsed,
    TriageCompleted,
)
from uwh.skills.read_reply.jev import threshold

_OWNERS = {
    "underwriter": "the underwriter",
    "producer": "the producer",
    "data_team": "the data team",
}
_READINGS = {
    "answers_all": "answers every question asked",
    "answers_some": "answers some of the questions asked",
    "declines_to_answer": "declines to answer",
    "off_topic": "is off topic",
}
# What a provider key fetches, in the words an underwriter uses.
_FETCHED = {
    "broker_tier": "the broker tier",
    "has_primary_policy_with_stand": "whether the insured has a primary policy with Stand",
    "replacement_cost": "the replacement cost",
    "protection_class": "the protection class",
    "kyc_score": "the identity screen score",
    "p_f": "the fire probability",
    "slope_angle_deg": "the slope angle",
    "min_distance_to_neighbor_ft": "the distance to the nearest neighbor",
    "vegetation_clearance": "the vegetation clearance",
    "road_access": "the road access",
}


def _words(name: str) -> str:
    return name.replace("_", " ")


def _sentence(text: str) -> str:
    """The text closed with a full stop, for a bullet that holds two sentences."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _unfinished(text: str) -> str:
    """The text without its closing full stop, for a bullet that holds one sentence."""
    return text.strip().removesuffix(".")


def _value(value: JsonValue) -> str:
    """A fact's value as it reads in a sentence."""
    match value:
        case None:
            return "empty"
        case bool():
            return "yes" if value else "no"
        case list():
            return ", ".join(_value(item) for item in value)
        case dict():
            return ", ".join(f"{key} {_value(item)}" for key, item in value.items())
        case _:
            return str(value)


def _triaged(fields: dict[str, JsonValue]) -> str:
    """How many fields triage found missing or in conflict."""
    counts = Counter(
        triage["value_status"] for triage in fields.values() if isinstance(triage, dict)
    )
    parts = [
        f"{counts[status]} {status}" for status in ("missing", "conflicting") if counts[status]
    ]
    return ", ".join(parts) or "none missing"


def _fetched(key: str, result: ProviderResult) -> str:
    what = _FETCHED.get(key, _words(key))
    match result.status:
        case "found":
            return f"Fetched {what}: {_value(result.value)}"
        case "blocked":
            return f"Could not fetch {what}: it needs {', '.join(result.missing_inputs)}"
        case _ if key == "p_f":
            return "The fire simulation failed, so you need to choose"
        case _:
            return f"Could not fetch {what}: the lookup was {_words(result.status)}"


def _reading(
    classification: str, classified_by: str | None, confidence: float | None, found: int
) -> str:
    """A reply reading: who classified it, with Jev's confidence against the threshold, and what it says."""
    says = f"It {_READINGS[classification]}; {found} answers found."
    if classified_by == "jev" and confidence is not None:
        meaning = "at or above" if confidence >= threshold() else "below"
        return (
            f"Jev classified this reply ({confidence:.2f}, {meaning} the "
            f"{threshold():.2f} threshold). {says}"
        )
    return f"The model classified this reply. {says}"


def event_summary(payload: StrictModel) -> str:
    """What the event says: its fact, result and consequence, in one bullet."""
    match payload:
        case RunStarted(seed=seed, lead_count=count):
            return f"Started the run with {count} leads from seed {seed}"
        case ReplayMiss(skill=skill):
            return f"No recording was found for a {skill} call"
        case DraftEdited(kind=kind, reason=reason):
            return f"Edited the {_words(kind)} draft. {_sentence(reason)}"
        case ProposalCreated():
            return "The assistant proposed a command for the underwriter to apply"
        case LeadReceived(source=source):
            return f"Received the lead from {source}"
        case FactObserved(key=key, value=value, source=source, status=status):
            held = ", held for review" if status == "pending_review" else ""
            return f"Recorded {key} as {_value(value)} ({source}){held}"
        case FactSelected(key=key, value=value, source=source, confirmed=confirmed):
            origin = f"{source}, confirmed" if confirmed else source
            return f"Using {_value(value)} for {key} ({origin})"
        case ConflictOpened(fields=fields):
            return f"The values given for {', '.join(fields)} disagree"
        case ConflictClosed(fields=fields):
            return f"The values given for {', '.join(fields)} agree"
        case TriageCompleted(fields=fields):
            return f"Triaged the fields: {_triaged(fields)}"
        case ProviderCalled(key=key, result=result):
            return _fetched(key, result)
        case PlanBuilt():
            return "Built the action plan"
        case BlockerOpened(owner=owner, detail=detail):
            return f"Waiting on {_OWNERS[owner]}. {_sentence(detail.text)}"
        case BlockerClosed(kind=kind):
            return f"The {_words(kind)} wait is over"
        case IntentCreated(
            kind=kind, recipient=recipient, subject=subject, rewritten_by_model=rewritten
        ):
            drafted = f"Drafted a {_words(kind)} to {recipient} with the subject {subject}"
            if rewritten:
                return f"{drafted}. The opening and closing were written by the model."
            return drafted
        case MessageSent():
            return "Sent the message to the producer"
        case DeliveryUnknown():
            return "The mailbox did not confirm the message, so it may not have been delivered"
        case ReplyReceived():
            return "The producer replied"
        case ReplyRead(
            classification=classification,
            classified_by=classified_by,
            jev_confidence=confidence,
            abstention=abstention,
            candidates=found,
        ):
            if classification is None:
                return f"The reply could not be read ({_words(str(abstention))})"
            return _reading(classification, classified_by, confidence, len(found))
        case ApprovalRecorded(decision=decision, item_kind=kind, reason=reason):
            return (
                f'{decision.capitalize()} a {_words(kind)} with the reason "{_unfinished(reason)}"'
            )
        case RulingRecorded(kind=kind, reason=reason):
            return f"Recorded a {_words(kind)} ruling. {_sentence(reason)}"
        case CommandRefused(command_type=command, reason=reason):
            return f"Refused {_words(command)}. {_sentence(reason)}"
        case SkillFallbackUsed(status="rejected", fallback=fallback):
            return _unfinished(fallback)
        case SkillFallbackUsed(skill=skill, fallback=fallback):
            return f"The {_words(skill)} skill was unavailable, so the fallback applied. {_sentence(fallback)}"
        case ModelCalled(skill=skill, tokens_in=tokens_in, tokens_out=tokens_out):
            return f"The {_words(skill)} skill called the model, using {tokens_in} tokens in and {tokens_out} out"
        case FaultInjected(fault=fault):
            return f"Injected the {_words(fault)} fault"
        case _:
            raise TypeError(f"no summary for a {type(payload).__name__}")
