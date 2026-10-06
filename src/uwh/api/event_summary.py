# ABOUTME: The one-line summary of an event payload (section 11): a plain sentence per event type, shown in the event list and read by the chat panel's tools.
# ABOUTME: Values are written as words and numbers; a summary holds no `name: value` dump, no JSON and no object repr.
from pydantic import JsonValue

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


def _words(name: str) -> str:
    return name.replace("_", " ")


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


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


def event_summary(payload: StrictModel) -> str:
    """What the event says in one sentence."""
    match payload:
        case RunStarted(seed=seed, lead_count=count):
            return f"Run started with {count} leads from seed {seed}."
        case ReplayMiss(skill=skill):
            return f"No recording was found for a {skill} call."
        case DraftEdited(kind=kind, reason=reason):
            return f"Edited the {_words(kind)} draft. {_sentence(reason)}"
        case ProposalCreated():
            return "The assistant proposed a command for the underwriter to apply."
        case LeadReceived(source=source):
            return f"Received from {source}."
        case FactObserved(key=key, value=value, source=source, status=status):
            held = " and is held for review" if status == "pending_review" else ""
            return f"{key} recorded as {_value(value)} ({source}){held}."
        case FactSelected(key=key, value=value, source=source):
            return f"{key} is {_value(value)} ({source})."
        case ConflictOpened(fields=fields):
            return f"The values given for {', '.join(fields)} disagree."
        case ConflictClosed(fields=fields):
            return f"The values given for {', '.join(fields)} agree."
        case TriageCompleted(fields=fields):
            return f"Triaged {len(fields)} fields."
        case ProviderCalled(key=key, result=result):
            return f"Looked up {key}; the lookup {_words(result.status)}."
        case PlanBuilt():
            return "Built the action plan."
        case BlockerOpened(owner=owner, detail=detail):
            return f"Waiting on {_OWNERS[owner]}. {_sentence(detail.text)}"
        case BlockerClosed(kind=kind):
            return f"The {_words(kind)} wait is over."
        case IntentCreated(kind=kind, recipient=recipient, subject=subject):
            return f"Drafted a {_words(kind)} to {recipient} with the subject {subject}."
        case MessageSent():
            return "The message was posted to the mailbox."
        case DeliveryUnknown():
            return "The mailbox did not confirm the message, so it may not have been delivered."
        case ReplyReceived(body=body):
            return f"The producer replied in {len(body)} characters."
        case ReplyRead(classification=classification, abstention=abstention, candidates=found):
            if classification is None:
                return f"The reply could not be read ({_words(str(abstention))})."
            return f"The reply {_READINGS[classification]}; {len(found)} answers found."
        case ApprovalRecorded(decision=decision, item_kind=kind, reason=reason):
            return f'{decision.capitalize()} a {_words(kind)} with the reason "{reason.strip()}".'
        case RulingRecorded(kind=kind, reason=reason):
            return f"Recorded a {_words(kind)} ruling. {_sentence(reason)}"
        case CommandRefused(command_type=command, reason=reason):
            return f"Refused {_words(command)}. {_sentence(reason)}"
        case SkillFallbackUsed(skill=skill, fallback=fallback):
            return f"The {_words(skill)} skill was unavailable, so the fallback applied. {_sentence(fallback)}"
        case ModelCalled(skill=skill, tokens_in=tokens_in, tokens_out=tokens_out):
            return f"The {_words(skill)} skill called the model, using {tokens_in} tokens in and {tokens_out} out."
        case FaultInjected(fault=fault):
            return f"Injected the {_words(fault)} fault."
        case _:
            raise TypeError(f"no summary for a {type(payload).__name__}")
