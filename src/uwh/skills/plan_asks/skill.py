# ABOUTME: The plan_asks skill (10.2): the typed asks a lead's triage and open conflicts call for, each with its stored wording, in registry order with the confirmations after, and the class of the request that carries them.
# ABOUTME: Deterministic. Field requests and follow-on questions come from the triage, confirmations from the conflicts; the combined dwelling-use confirmation replaces the two that both name `dwelling_use_type`.
from typing import Any

from uwh.rules.data_files import read_yaml
from uwh.rules.models import Ask, AskKind, FieldTriage, Resolution, StrictModel
from uwh.rules.registry import Registry
from uwh.runtime.event_types import ConflictOpened, RequestKind
from uwh.skills.vertical import CONFIRMATION_ONLY_CLASS

# The ask id of the combined dwelling-use confirmation, which stands for two validators.
COMBINED_DWELLING_USE_ID = "dwelling_use_conflict"


class PlanAsksInput(StrictModel):
    registry: Registry
    triage: dict[str, FieldTriage]
    conflicts: list[ConflictOpened]  # the open conflicts, each to be confirmed


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


def _confirmations(conflicts: list[ConflictOpened], wording: dict[str, Any]) -> list[Ask]:
    combined = wording["combined_confirmation"]
    merged = [c for c in conflicts if c.validator in combined["replaces"]]
    combine = len(merged) == len(combined["replaces"])
    asks = [
        Ask(
            ask_id=conflict.validator,
            kind=AskKind.confirmation,
            fields=conflict.fields,
            reason="Values reported for these fields conflict.",
            wording=conflict.question,
        )
        for conflict in conflicts
        if not (combine and conflict in merged)
    ]
    if combine:
        values = {name: value for conflict in merged for name, value in conflict.values.items()}
        asks.append(
            Ask(
                ask_id=COMBINED_DWELLING_USE_ID,
                kind=AskKind.confirmation,
                fields=combined["fields"],
                reason="Values reported for these fields conflict.",
                wording=combined["question"].format_map(values),
            )
        )
    return asks


def run(input: PlanAsksInput) -> PlanAsksOutput:
    wording = read_yaml("wording.yaml")
    asks = _field_asks(input, wording) + _confirmations(input.conflicts, wording)
    confirmation_only = bool(asks) and all(ask.kind == AskKind.confirmation for ask in asks)
    return PlanAsksOutput(
        asks=asks,
        message_class=CONFIRMATION_ONLY_CLASS if confirmation_only else "routine_request",
    )
