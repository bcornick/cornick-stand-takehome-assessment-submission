# ABOUTME: The confirmations of open conflicts (10.2, A.7): one ask per conflict with its stored question, the two dwelling-use conflicts combined into one, and the fields a confirmation's question reports.
# ABOUTME: The plan of asks builds them to put to the producer, and the reading of a reply rebuilds them to know which field each answer is for.
from string import Formatter

from uwh.rules.data_files import read_yaml
from uwh.rules.models import Ask, AskKind
from uwh.runtime.event_types import ConflictOpened

# The ask id of the combined dwelling-use confirmation, which stands for two validators.
COMBINED_DWELLING_USE_ID = "dwelling_use_conflict"


def confirmation_asks(conflicts: list[ConflictOpened]) -> list[Ask]:
    """One confirmation per conflict; when both dwelling-use conflicts are open, one question in place of the two."""
    combined = read_yaml("wording.yaml")["combined_confirmation"]
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


def reported_fields(ask_id: str) -> list[str]:
    """The fields a confirmation's question gives a value for: the producer's answer is a value for each."""
    wording = read_yaml("wording.yaml")
    question = (
        wording["combined_confirmation"]["question"]
        if ask_id == COMBINED_DWELLING_USE_ID
        else wording["confirmations"][ask_id]["question"]
    )
    return [name for _, name, _, _ in Formatter().parse(question) if name]
