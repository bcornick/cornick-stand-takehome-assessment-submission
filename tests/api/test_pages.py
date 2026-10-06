# ABOUTME: Tests that a stored plan is grouped by playbook page: an effect by the page its board path starts on, a decline on every branch by its first branch, a wait by its graph and a note on a page without a graph as a page of its own.
# ABOUTME: The plans are built by hand over the real graphs, so a page number maps to a graph id as the rules data has it.
from uwh.api.pages import plan_pages
from uwh.rules.graphs import load_graphs
from uwh.rules.models import (
    ActionPlan,
    Assumption,
    DeclineEffect,
    NotEvaluatedNote,
    PlannedEffect,
    RequirementEffect,
    RuleTrace,
    TraceBranch,
    UndecidedPage,
)


def requirement(rule: str, board_path: list[str]) -> PlannedEffect:
    return PlannedEffect(
        effect=RequirementEffect(type="requirement", rule=rule, text="Send a photo."),
        trace=RuleTrace(board_path=board_path),
        committed=True,
    )


def every_branch_decline(*branches: tuple[str, list[str]]) -> RuleTrace:
    return RuleTrace(
        board_path=[],
        alternatives=[
            TraceBranch(
                assumed=[Assumption(field="roof_age", when={"equals": True})],
                board_path=path,
                rule=rule,
            )
            for rule, path in branches
        ],
    )


def note(ref: str) -> NotEvaluatedNote:
    return NotEvaluatedNote(ref=ref, text=f"{ref} is not evaluated.", producer_text="Not reviewed.")


def test_an_effect_lands_on_the_page_its_board_path_names() -> None:
    plan = ActionPlan(
        effects=[
            requirement("R-FIRE", ["04:ROOT", "04:N1"]),
            requirement("R-ROOF", ["05:ROOT"]),
            requirement("R-FIRE-2", ["04:ROOT"]),
        ]
    )

    pages = plan_pages(plan, load_graphs())

    assert [(p.key, sorted(e.effect.rule for e in p.effects)) for p in pages] == [
        ("fire_simulation", ["R-FIRE", "R-FIRE-2"]),
        ("roof", ["R-ROOF"]),
    ]


def test_a_decline_on_every_branch_lands_on_the_page_of_its_first_branch() -> None:
    trace = every_branch_decline(("R-D1", ["06:ROOT", "06:N2"]), ("R-D2", ["06:ROOT"]))
    plan = ActionPlan(declines_on_every_branch=[trace], proposed_decline=True)

    (page,) = plan_pages(plan, load_graphs())

    assert page.key == "siding" and page.declines_on_every_branch == [trace]
    assert page.effects == []


def test_a_decline_effect_and_a_wait_share_the_page_of_their_graph() -> None:
    decline = PlannedEffect(
        effect=DeclineEffect(type="decline", rule="R-D"),
        trace=RuleTrace(board_path=["03:ROOT"]),
        committed=True,
    )
    plan = ActionPlan(
        effects=[decline],
        proposed_decline=True,
        undecided=[UndecidedPage(graph="occupancy", waits_on=["occupancy_type"])],
    )

    (page,) = plan_pages(plan, load_graphs())

    assert (page.key, page.waits_on) == ("occupancy", ["occupancy_type"])
    assert len(page.effects) == 1


def test_a_note_on_a_page_without_a_graph_is_a_page_of_its_own_after_the_graph_pages() -> None:
    plan = ActionPlan(
        effects=[requirement("R-ROOF", ["05:ROOT"])],
        not_evaluated=[note("electrical"), note("plumbing")],
    )

    pages = plan_pages(plan, load_graphs())

    assert [p.key for p in pages] == ["roof", "electrical", "plumbing"]
    assert [n.ref for n in pages[1].not_evaluated] == ["electrical"]
    assert pages[1].effects == [] and pages[1].waits_on == []


def test_a_plan_with_nothing_has_no_pages() -> None:
    assert plan_pages(ActionPlan(), load_graphs()) == []
