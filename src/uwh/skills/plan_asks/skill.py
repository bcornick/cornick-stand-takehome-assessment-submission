# ABOUTME: The plan_asks skill (10.2): the typed asks a lead's triage and open conflicts call for, each with its stored wording, in registry order with the confirmations after, and the class of the request that carries them.
# ABOUTME: Deterministic. Field requests and follow-on questions come from the triage, confirmations from the conflicts; the combined dwelling-use confirmation replaces the two that both name `dwelling_use_type`.
from typing import Any

from uwh.rules.confirmations import confirmation_asks
from uwh.rules.data_files import read_yaml
from uwh.rules.models import Ask, AskKind, FieldTriage, Resolution, StrictModel
from uwh.rules.registry import Registry
from uwh.runtime.event_types import ConflictOpened, RequestKind
from uwh.skills.vertical import CONFIRMATION_ONLY_CLASS


class PlanAsksInput(StrictModel):
    registry: Registry
    triage: dict[str, FieldTriage]
    conflicts: list[ConflictOpened]  # the open conflicts, each to be confirmed
    catalogue_questions: list[str]  # the catalogue ids the playbook asks the producer


class PlanAsksOutput(StrictModel):
    asks: list[Ask]  # the outstanding asks
    message_class: RequestKind  # the class of the request that carries them (10.1)


def _follow_on_wording(question: str, preamble: str | None) -> str:
    return question if preamble is None else f"{preamble}: {question[0].lower()}{question[1:]}"


def _field_asks(input: PlanAsksInput, wording: dict[str, Any]) -> list[Ask]:
    asks: list[Ask] = []
    for name, triage in input.triage.items():
        question = wording["fields"].get(name)
        if triage.resolution == Resolution.ask:
            asks.append(
                Ask(
                    ask_id=name,
                    kind=AskKind.field_request,
                    fields=[name],
                    reason="The registry requires it to quote.",
                    wording=question,
                )
            )
        elif triage.resolution == Resolution.ask_follow_on:
            preamble = wording["preambles"].get(input.registry[name].required_when)
            asks.append(
                Ask(
                    ask_id=name,
                    kind=AskKind.follow_on_question,
                    fields=[name],
                    reason=f"Needed if the answer to {', '.join(triage.depends_on)} calls for it.",
                    wording=_follow_on_wording(question, preamble),
                )
            )
    return asks


def _catalogue_asks(catalogue_ids: list[str]) -> list[Ask]:
    questions = read_yaml("catalogue.yaml")["questions"]
    return [
        Ask(
            ask_id=catalogue_id,
            kind=AskKind.catalogue_question,
            fields=[f"q:{catalogue_id}"],
            reason="The playbook needs it to decide.",
            wording=questions[catalogue_id]["wording"],
        )
        for catalogue_id in catalogue_ids
    ]


def _message_class(asks: list[Ask]) -> RequestKind:
    """A catalogue question makes a sensitive request (10.1); a request of confirmations alone takes
    the configured class."""
    if any(ask.kind == AskKind.catalogue_question for ask in asks):
        return "sensitive_request"
    if asks and all(ask.kind == AskKind.confirmation for ask in asks):
        return CONFIRMATION_ONLY_CLASS
    return "routine_request"


def run(input: PlanAsksInput) -> PlanAsksOutput:
    wording = read_yaml("wording.yaml")
    asks = (
        _field_asks(input, wording)
        + confirmation_asks(input.conflicts)
        + _catalogue_asks(input.catalogue_questions)
    )
    return PlanAsksOutput(asks=asks, message_class=_message_class(asks))
