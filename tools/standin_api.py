# ABOUTME: A stand-in for the app's HTTP surface that serves the A.5 read routes from tests/fixtures/ui; the start and command routes keep the app's handlers and the other routes answer 501.
# ABOUTME: It is the app's own application with each read handler replaced, so paths, response models and OpenAPI are the app's; run it with --port.
import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from pydantic import TypeAdapter

from uwh.api import commands, run
from uwh.api.app import create_app
from uwh.api.routes import router
from uwh.api.runtime import get_runtime
from uwh.api.views import (
    Item,
    LeadDetail,
    LeadEvents,
    ProposalView,
    QueueRow,
    RunView,
    SettingsView,
    SkillView,
)
from uwh.settings import Settings

DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ui"
DEFAULT_PORT = 8765
HOST = "127.0.0.1"


@dataclass(frozen=True)
class Fixtures:
    """The fixture files, each parsed into its response model."""

    run: RunView
    queue: list[QueueRow]
    leads: dict[str, LeadDetail]
    events: dict[str, LeadEvents]
    items: list[Item]
    settings: SettingsView
    skills: list[SkillView]
    proposals: list[ProposalView]


def load_fixtures(directory: Path) -> Fixtures:
    """Parse every fixture file; a file that does not fit its model, or a lead file that holds
    another lead, is an error."""

    def read(name: str) -> bytes:
        return (directory / name).read_bytes()

    queue = TypeAdapter(list[QueueRow]).validate_json(read("leads.json"))
    leads: dict[str, LeadDetail] = {}
    events: dict[str, LeadEvents] = {}
    for row in queue:
        detail = LeadDetail.model_validate_json(read(f"lead/{row.lead_id}.json"))
        history = LeadEvents.model_validate_json(read(f"events/{row.lead_id}.json"))
        for found in (detail.lead_id, history.lead_id):
            if found != row.lead_id:
                raise ValueError(f"the fixture files of {row.lead_id} hold {found}")
        leads[row.lead_id] = detail
        events[row.lead_id] = history
    return Fixtures(
        run=RunView.model_validate_json(read("run.json")),
        queue=queue,
        leads=leads,
        events=events,
        items=TypeAdapter(list[Item]).validate_json(read("items.json")),
        settings=SettingsView.model_validate_json(read("settings.json")),
        skills=TypeAdapter(list[SkillView]).validate_json(read("skills.json")),
        proposals=TypeAdapter(list[ProposalView]).validate_json(read("proposals.json")),
    )


def lead_of[T](records: dict[str, T], lead_id: str) -> T:
    if lead_id not in records:
        raise HTTPException(status_code=404, detail=f"no lead {lead_id}")
    return records[lead_id]


def no_runtime() -> NoReturn:
    """The stand-in runs no runtime, so a route that needs one answers 501 as the app's other
    unserved routes do."""
    raise HTTPException(status_code=501, detail="not implemented by the stand-in")


def create_standin_app(fixtures_dir: Path = DEFAULT_FIXTURES) -> FastAPI:
    """An application that declares each of the app's routes again from the app's own route
    objects (path, methods, response model, responses), so its OpenAPI document is the app's.
    A read route is served from the fixtures; every other route keeps the app's handler and
    answers 501."""
    fixtures = load_fixtures(fixtures_dir)

    def get_run() -> RunView:
        return fixtures.run

    def list_leads() -> list[QueueRow]:
        return fixtures.queue

    def get_lead(id: str) -> LeadDetail:
        return lead_of(fixtures.leads, id)

    def get_lead_events(id: str) -> LeadEvents:
        return lead_of(fixtures.events, id)

    def list_items() -> list[Item]:
        return fixtures.items

    def get_settings() -> SettingsView:
        return fixtures.settings

    def list_skills() -> list[SkillView]:
        return fixtures.skills

    def list_proposals() -> list[ProposalView]:
        return fixtures.proposals

    served: dict[str, Callable[..., Any]] = {
        "/api/run": get_run,
        "/api/leads": list_leads,
        "/api/leads/{id}": get_lead,
        "/api/leads/{id}/events": get_lead_events,
        "/api/items": list_items,
        "/api/settings": get_settings,
        "/api/skills": list_skills,
        "/api/proposals": list_proposals,
    }
    real = create_app(Settings.load({"UWH_DB": "unused.db"}))
    declared = [
        r
        for r in (*router.routes, *run.router.routes, *commands.router.routes)
        if isinstance(r, APIRoute)
    ]
    standin = FastAPI(title=real.title, version=real.version)
    standin.dependency_overrides[get_runtime] = no_runtime
    served_paths: set[str] = set()
    for route in declared:
        reads = route.methods == {"GET"} and route.path in served
        if reads:
            served_paths.add(route.path)
        standin.add_api_route(
            route.path,
            served[route.path] if reads else route.endpoint,
            methods=sorted(route.methods or ()),
            response_model=route.response_model,
            status_code=route.status_code,
            name=route.name,
            summary=route.summary,
            description=route.description,
            responses=route.responses,
            response_class=route.response_class,
        )
    if served_paths != set(served):
        raise RuntimeError(
            f"the app declares no GET route for {sorted(set(served) - served_paths)}"
        )
    return standin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="default 8765")
    args = parser.parse_args(argv)
    uvicorn.run(create_standin_app(), host=HOST, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
