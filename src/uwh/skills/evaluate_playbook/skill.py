# ABOUTME: The evaluate_playbook skill (9.6): the pages that apply to a lead are walked over its usable facts, and the effects, the undecided pages and the pages not evaluated make the action plan.
# ABOUTME: Deterministic. A page whose graph is not encoded stops the lead (NotBuilt); a page of the five cut pages that applies becomes a `not_evaluated` note.
from pydantic import JsonValue

from uwh.rules.graphs import (
    applies,
    evaluate_graph,
    load_graphs,
    load_not_encoded_pages,
    unknown_fields,
)
from uwh.rules.models import (
    ActionPlan,
    NotBuilt,
    NotEvaluatedNote,
    PlannedEffect,
    StrictModel,
    UndecidedPage,
)


class EvaluatePlaybookInput(StrictModel):
    facts: dict[str, JsonValue]  # usable facts only; a missing key is unknown


def run(input: EvaluatePlaybookInput) -> ActionPlan:
    facts = input.facts
    effects: list[PlannedEffect] = []
    undecided: list[UndecidedPage] = []
    for graph in load_graphs():
        holds = applies(graph.applies_when, facts)
        if holds is None:
            undecided.append(
                UndecidedPage(graph=graph.id, waits_on=unknown_fields(graph.applies_when, facts))
            )
        elif holds and graph.root is None:
            raise NotBuilt(f"the {graph.id} page applies and its graph is not built")
        elif holds:
            result = evaluate_graph(graph, facts)
            if isinstance(result, UndecidedPage):
                undecided.append(result)
            else:
                effects += result
    notes = [
        NotEvaluatedNote(
            ref=page.id,
            text=f"The {page.title} page is not evaluated.",
            producer_text=page.producer_text,
        )
        for page in load_not_encoded_pages()
        if applies(page.applies_when, facts)
    ]
    return ActionPlan(effects=effects, undecided=undecided, not_evaluated=notes)
