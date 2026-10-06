# ABOUTME: Groups a stored plan by playbook page, so a page view and the chat's playbook lookup read one thing.
# ABOUTME: The plan holds no per-page record; the page of each entry is read from its board path, its graph name or its note's ref, and no graph is walked again.
from collections.abc import Sequence

from uwh.api.views import PlanPage
from uwh.rules.graphs import Graph
from uwh.rules.models import ActionPlan


def _page_number(board_path: list[str]) -> str:
    """The page number a board path starts on: "04" for ["04:ROOT", "04:N1"]."""
    return board_path[0].split(":", 1)[0]


def plan_pages(plan: ActionPlan, graphs: Sequence[Graph]) -> list[PlanPage]:
    """The pages the plan has content for: graph pages in graph order, then the pages with no graph."""
    key_of_number = {graph.page.split("/")[2].split("-", 1)[0]: graph.id for graph in graphs}
    pages: dict[str, PlanPage] = {}

    def page(key: str) -> PlanPage:
        return pages.setdefault(
            key,
            PlanPage(
                key=key, effects=[], declines_on_every_branch=[], waits_on=[], not_evaluated=[]
            ),
        )

    for planned in plan.effects:
        page(key_of_number[_page_number(planned.trace.board_path)]).effects.append(planned)
    for trace in plan.declines_on_every_branch:
        first_branch = trace.alternatives[0]
        page(key_of_number[_page_number(first_branch.board_path)]).declines_on_every_branch.append(
            trace
        )
    for undecided in plan.undecided:
        page(undecided.graph).waits_on.extend(undecided.waits_on)
    for note in plan.not_evaluated:
        page(note.ref).not_evaluated.append(note)

    graph_keys = [graph.id for graph in graphs]
    in_graph_order = [pages[key] for key in graph_keys if key in pages]
    without_graph = [pages[key] for key in sorted(pages) if key not in graph_keys]
    return in_graph_order + without_graph
