# ABOUTME: The evaluate_playbook skill (9.6): the pages that apply to a lead are walked over its usable facts and the underwriter's rulings, and the effects, the choices and questions they leave open, the undecided pages and the pages not evaluated make the action plan.
# ABOUTME: Deterministic. A decline makes the plan a proposed decline and drops the choices and questions; a page of the five cut pages that applies becomes a `not_evaluated` note.
from pydantic import JsonValue

from uwh.rules.graphs import (
    Walk,
    applies,
    evaluate_graph,
    load_graphs,
    load_not_encoded_pages,
    unknown_fields,
)
from uwh.rules.models import (
    ActionPlan,
    DeclineEffect,
    NotEvaluatedNote,
    PlannedEffect,
    Rulings,
    StrictModel,
    UndecidedPage,
)


class EvaluatePlaybookInput(StrictModel):
    facts: dict[str, JsonValue]  # usable facts only; a missing key is unknown
    rulings: Rulings = Rulings()


def _one_effect_per_type_and_rule(walk: Walk) -> list[PlannedEffect]:
    """The effects of the walk, a committed copy kept in place of a possible one (9.6)."""
    kept: dict[tuple[str, str], PlannedEffect] = {}
    for planned in walk.effects + walk.possible:
        kept.setdefault((planned.effect.type, planned.effect.rule), planned)
    return list(kept.values())


def run(input: EvaluatePlaybookInput) -> ActionPlan:
    facts = input.facts
    undecided: list[UndecidedPage] = []
    walks: list[Walk] = []
    for graph in load_graphs():
        holds = applies(graph.applies_when, facts)
        if holds is None:
            undecided.append(
                UndecidedPage(graph=graph.id, waits_on=unknown_fields(graph.applies_when, facts))
            )
        elif holds:
            walk = evaluate_graph(graph, facts, input.rulings)
            if walk.waits_on:
                undecided.append(UndecidedPage(graph=graph.id, waits_on=list(walk.waits_on)))
            walks.append(walk)
    total = sum(walks, Walk())
    effects = _one_effect_per_type_and_rule(total)
    declines = list(total.every_branch)
    decline_reason = input.rulings.decline_reason
    proposed_decline = (
        any(p.committed and isinstance(p.effect, DeclineEffect) for p in effects)
        or bool(declines)
        or decline_reason is not None
    )
    # A proposed decline holds the underwriter's attention and the producer's mailbox alone.
    choices = {} if proposed_decline else {c.choice_id: c for c in total.choices}
    notes = [
        NotEvaluatedNote(
            ref=page.id,
            text=f"The {page.title} page is not evaluated.",
            producer_text=page.producer_text,
        )
        for page in load_not_encoded_pages()
        if applies(page.applies_when, facts)
    ]
    return ActionPlan(
        effects=effects,
        declines_on_every_branch=declines,
        proposed_decline=proposed_decline,
        underwriter_decline=decline_reason,
        undecided=undecided,
        open_choices=list(choices.values()),
        catalogue_questions=[] if proposed_decline else list(total.questions),
        not_evaluated=notes,
    )
