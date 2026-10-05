# ABOUTME: Tests of tools/standin_api.py: it serves the A.5 read routes from tests/fixtures/ui through the app's own route declarations, and the fixtures fit their response models and agree with each other.
# ABOUTME: Each agreement check also runs against a deliberately broken copy of the fixtures, so a check that cannot fail is caught.
import hashlib
import importlib.util
import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from uwh.api.app import create_app
from uwh.api.views import (
    Item,
    LeadDetail,
    LeadEvents,
    ProposalView,
    ProposeCommandPayload,
    QueueRow,
    RunView,
    SettingsView,
    SkillView,
)
from uwh.settings import Settings
from uwh.skills import vertical

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "ui"
LEAD_IDS = [f"LEAD-00000042-{n:03d}" for n in range(10)]

GROUP_ORDER = ("blocked_on_underwriter", "waiting_on_data_or_producer", "finished")
REQUEST_KINDS = ("routine_request", "sensitive_request")
SERVICE_LEVEL_DAYS = 2
# Kinds that are approvals or question items (A.11): every other blocker is not an item.
ITEM_BLOCKER_KINDS = ("underwriter_review", "underwriter_question", "delivery_unknown")


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("standin_api", ROOT / "tools" / "standin_api.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def standin_client(fixtures: Path = FIXTURES) -> TestClient:
    return TestClient(load_tool().create_standin_app(fixtures))


@pytest.fixture(scope="module")
def client() -> TestClient:
    return standin_client()


def get_json(client: TestClient, path: str) -> Any:
    response = client.get(path)
    assert response.status_code == 200, f"GET {path}: {response.status_code} {response.text}"
    return response.json()


# ---- routes -----------------------------------------------------------------------------------

# Each GET route the stand-in serves with data, with the response model its body is parsed as.
LIST_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "/api/leads": TypeAdapter(list[QueueRow]),
    "/api/items": TypeAdapter(list[Item]),
    "/api/skills": TypeAdapter(list[SkillView]),
    "/api/proposals": TypeAdapter(list[ProposalView]),
}
OBJECT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "/api/run": TypeAdapter(RunView),
    "/api/settings": TypeAdapter(SettingsView),
}


def test_the_standin_has_the_apps_routes() -> None:
    app = create_app(Settings.load({"UWH_DB": "unused.db"}))
    assert load_tool().create_standin_app(FIXTURES).openapi() == app.openapi()


def test_every_get_route_but_the_stream_is_covered(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    get_paths = {path for path, methods in paths.items() if "get" in methods}
    covered = {*LIST_ADAPTERS, *OBJECT_ADAPTERS, "/api/leads/{id}", "/api/leads/{id}/events"}
    assert get_paths - {"/api/events/stream"} == covered


@pytest.mark.parametrize("path", [*LIST_ADAPTERS, *OBJECT_ADAPTERS])
def test_a_read_route_serves_fixture_data_that_fits_its_model(
    client: TestClient, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    adapter = {**LIST_ADAPTERS, **OBJECT_ADAPTERS}[path]
    parsed = adapter.validate_json(response.content)
    if path in LIST_ADAPTERS and path != "/api/proposals":
        assert parsed, f"{path} is empty"


@pytest.mark.parametrize("lead_id", LEAD_IDS)
def test_a_lead_serves_its_detail_and_events(client: TestClient, lead_id: str) -> None:
    detail = LeadDetail.model_validate_json(client.get(f"/api/leads/{lead_id}").content)
    events = LeadEvents.model_validate_json(client.get(f"/api/leads/{lead_id}/events").content)
    assert detail.lead_id == lead_id
    assert events.lead_id == lead_id
    assert events.events


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_an_unknown_lead_is_a_404(client: TestClient, suffix: str) -> None:
    assert client.get(f"/api/leads/LEAD-00000042-099{suffix}").status_code == 404


POST_REQUESTS: list[tuple[str, dict[str, Any] | None]] = [
    ("/api/run/start", None),
    ("/api/commands", {"type": "emergency_stop", "payload": {"engaged": True}}),
    ("/api/replies", {"lead_id": LEAD_IDS[1], "intent_id": "x", "body": "The roof is slate."}),
    ("/api/replies/fixtures", None),
    ("/api/chat", {"message": "why is lead 003 held?"}),
]


@pytest.mark.parametrize(("path", "body"), POST_REQUESTS)
def test_a_post_route_answers_501(
    client: TestClient, path: str, body: dict[str, Any] | None
) -> None:
    assert client.post(path, json=body).status_code == 501


def test_the_event_stream_answers_501(client: TestClient) -> None:
    assert client.get("/api/events/stream").status_code == 501


# ---- fixtures fit their models, loudly --------------------------------------------------------


def copy_fixtures(destination: Path) -> Path:
    target = destination / "ui"
    shutil.copytree(FIXTURES, target)
    return target


def edit_json(path: Path, change: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_a_fixture_that_does_not_fit_its_model_fails_at_load(tmp_path: Path) -> None:
    broken = copy_fixtures(tmp_path)
    edit_json(broken / "run.json", lambda run: run.update(mode="bogus"))
    with pytest.raises(ValidationError, match="mode"):
        load_tool().create_standin_app(broken)


def test_a_lead_file_named_for_another_lead_fails_at_load(tmp_path: Path) -> None:
    broken = copy_fixtures(tmp_path)
    edit_json(
        broken / "lead" / f"{LEAD_IDS[1]}.json", lambda detail: detail.update(lead_id=LEAD_IDS[2])
    )
    with pytest.raises(ValueError, match=LEAD_IDS[1]):
        load_tool().create_standin_app(broken)


# ---- the fixtures agree with each other -------------------------------------------------------


def canonical_hash(value: dict[str, Any]) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def primary_blocker(detail: LeadDetail) -> Any:
    rank = vertical.BLOCKER_KINDS_BY_PRIORITY.index
    return min(detail.blockers, key=lambda blocker: rank(blocker.kind), default=None)


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def lead_problems(
    row: QueueRow, detail: LeadDetail, events: LeadEvents, sim_now: datetime
) -> list[str]:
    lead = row.lead_id
    problems: list[str] = []
    primary = primary_blocker(detail)
    expected_action = None if primary is None else primary.kind
    expected_owner = None if primary is None else primary.owner
    if row.status != detail.status:
        problems.append(f"{lead}: row status {row.status} but detail status {detail.status}")
    if row.primary_next_action != expected_action:
        problems.append(
            f"{lead}: primary_next_action {row.primary_next_action} != {expected_action}"
        )
    if row.waits_on != expected_owner:
        problems.append(f"{lead}: waits_on {row.waits_on} != {expected_owner}")
    expected_group = (
        "finished"
        if detail.status in vertical.TERMINAL_STATUSES
        else "blocked_on_underwriter"
        if expected_owner == "underwriter"
        else "waiting_on_data_or_producer"
    )
    if row.group != expected_group:
        problems.append(f"{lead}: group {row.group} != {expected_group}")
    asks = sum(
        len(event.payload["ask_ids"])  # type: ignore[arg-type]
        for event in events.events
        if event.type.value == "intent_created" and event.payload["kind"] in REQUEST_KINDS
    )
    if row.ask_count != asks:
        problems.append(f"{lead}: ask_count {row.ask_count} != {asks} asks in the requests")
    effective = next((f.value for f in detail.facts if f.key == "effective_date"), None)
    if row.effective_date != effective:
        problems.append(f"{lead}: effective_date {row.effective_date} != fact {effective}")
    received = next(e for e in events.events if e.type.value == "lead_received")
    age = (sim_now - parse_time(str(received.payload["received_at"]))).total_seconds() / 86400
    if abs(row.age_business_days - age) > 0.01:
        problems.append(f"{lead}: age {row.age_business_days} != {age:.2f} days since receipt")
    if row.service_level_breached != (row.age_business_days > SERVICE_LEVEL_DAYS):
        problems.append(f"{lead}: service_level_breached does not follow the age")
    return problems


def plan_problems(detail: LeadDetail) -> list[str]:
    lead = detail.lead_id
    problems: list[str] = []
    if detail.plan is None:
        return [f"{lead}: no plan"]
    undecided_pages = {p.graph: sorted(set(p.waits_on)) for p in detail.playbook if p.waits_on}
    plan_undecided = {u.graph: u.waits_on for u in detail.plan.undecided}
    if undecided_pages != plan_undecided:
        problems.append(f"{lead}: the plan's undecided pages differ from the playbook's")
    notes = {n.ref: n.text for n in detail.notes if n.kind == "not_evaluated"}
    plan_notes = {n.ref: n.text for n in detail.plan.not_evaluated}
    if notes != plan_notes:
        problems.append(f"{lead}: the not_evaluated notes differ from the plan's")
    choices = [c.model_dump(exclude={"shown_values"}) for c in detail.open_choices]
    if choices != [c.model_dump() for c in detail.plan.open_choices]:
        problems.append(f"{lead}: open_choices differ from the plan's")
    if detail.plan_hash != canonical_hash(detail.plan.model_dump(mode="json")):
        problems.append(f"{lead}: plan_hash is not the hash of the plan")
    return problems


def draft_problems(detail: LeadDetail, events: LeadEvents) -> list[str]:
    lead = detail.lead_id
    problems: list[str] = []
    created = {
        e.payload["intent_id"]: e.payload for e in events.events if e.type.value == "intent_created"
    }
    sent = {e.payload["intent_id"] for e in events.events if e.type.value == "message_sent"}
    for draft in detail.drafts:
        digest = canonical_hash(
            {"recipient": draft.recipient, "subject": draft.subject, "body": draft.body}
        )
        if draft.payload_hash != digest:
            problems.append(f"{lead}: {draft.intent_id} payload_hash is not the hash of its text")
        if draft.intent_id not in created:
            problems.append(f"{lead}: {draft.intent_id} has no intent_created event")
        elif created[draft.intent_id]["payload_hash"] != draft.payload_hash:
            problems.append(f"{lead}: {draft.intent_id} differs from its intent_created event")
        if (draft.state == "sent") != (draft.intent_id in sent):
            problems.append(
                f"{lead}: {draft.intent_id} state {draft.state} and message_sent differ"
            )
    intents = {d.intent_id for d in detail.drafts}
    for blocker in detail.blockers:
        if blocker.detail.intent_id is not None and blocker.detail.intent_id not in intents:
            problems.append(f"{lead}: blocker {blocker.item_id} names an unknown draft")
    return problems


def event_problems(events: LeadEvents) -> list[str]:
    ids = [e.id for e in events.events]
    problems = [
        f"{events.lead_id}: event {e.id} is for {e.lead_id}"
        for e in events.events
        if e.lead_id != events.lead_id
    ]
    if ids != sorted(set(ids)):
        problems.append(f"{events.lead_id}: event ids are not increasing and unique")
    return problems


def item_problems(items: list[Any], details: dict[str, LeadDetail]) -> list[str]:
    problems: list[str] = []
    open_items = {
        (lead, blocker.item_id): blocker
        for lead, detail in details.items()
        for blocker in detail.blockers
        if blocker.kind in ITEM_BLOCKER_KINDS
    }
    listed = {(item.lead_id, item.item_id) for item in items}
    if listed != set(open_items):
        problems.append(
            f"items {sorted(listed)} differ from open item blockers {sorted(open_items)}"
        )
    for item in items:
        blocker = open_items.get((item.lead_id, item.item_id))
        if blocker is None:
            continue
        shared = type(blocker).model_fields
        if {k: getattr(item, k) for k in shared} != {k: getattr(blocker, k) for k in shared}:
            problems.append(f"item {item.item_id} differs from its blocker")
        detail = details[item.lead_id]
        if item.type == "review" and item.draft is not None:
            if item.draft not in detail.drafts:
                problems.append(f"item {item.item_id} carries a draft the lead does not hold")
        if item.type == "question" and item.choices != detail.open_choices:
            problems.append(f"item {item.item_id} holds choices other than the lead's open choices")
    return problems


def follow_ups_sent(events: dict[str, LeadEvents]) -> int:
    """Messages sent for a request of round 2 or later."""
    count = 0
    for lead_events in events.values():
        rounds = {
            e.payload["intent_id"]: e.payload["round"]
            for e in lead_events.events
            if e.type.value == "intent_created" and e.payload["kind"] in REQUEST_KINDS
        }
        count += sum(
            1
            for e in lead_events.events
            if e.type.value == "message_sent" and int(rounds[e.payload["intent_id"]]) >= 2  # type: ignore[call-overload]
        )
    return count


def run_problems(
    run: RunView,
    rows: list[QueueRow],
    details: dict[str, LeadDetail],
    events: dict[str, LeadEvents],
) -> list[str]:
    expected = {
        "quotes_sent": sum(r.status == "quote_sent" for r in rows),
        "follow_ups_sent": follow_ups_sent(events),
        "declines_approved": sum(r.status == "declined" for r in rows),
        "waiting_on_underwriter": sum(r.group == "blocked_on_underwriter" for r in rows),
        "waiting_on_data": sum(r.group == "waiting_on_data_or_producer" for r in rows),
        "delivery_unknown": sum(
            any(b.kind == "delivery_unknown" for b in d.blockers) for d in details.values()
        ),
    }
    return [
        f"run summary {key} is {getattr(run.summary, key)}, the leads give {value}"
        for key, value in expected.items()
        if getattr(run.summary, key) != value
    ]


def queue_order_problems(rows: list[QueueRow]) -> list[str]:
    def order(row: QueueRow) -> tuple[int, str, str]:
        return (GROUP_ORDER.index(row.group), row.effective_date or "9999", row.lead_id)

    problems: list[str] = []
    if sorted(r.lead_id for r in rows) != LEAD_IDS:
        problems.append("the queue does not hold the ten seed-42 leads once each")
    if rows != sorted(rows, key=order):
        problems.append("the queue is not in section 11 order")
    return problems


def all_problems(client: TestClient) -> list[str]:
    run = RunView.model_validate(get_json(client, "/api/run"))
    rows = TypeAdapter(list[QueueRow]).validate_python(get_json(client, "/api/leads"))
    items = TypeAdapter(list[Item]).validate_python(get_json(client, "/api/items"))
    details = {
        row.lead_id: LeadDetail.model_validate(get_json(client, f"/api/leads/{row.lead_id}"))
        for row in rows
    }
    events = {
        row.lead_id: LeadEvents.model_validate(get_json(client, f"/api/leads/{row.lead_id}/events"))
        for row in rows
    }
    assert run.sim_now is not None
    sim_now = parse_time(run.sim_now)
    problems = queue_order_problems(rows)
    for row in rows:
        detail, lead_events = details[row.lead_id], events[row.lead_id]
        problems += lead_problems(row, detail, lead_events, sim_now)
        problems += plan_problems(detail)
        problems += draft_problems(detail, lead_events)
        problems += event_problems(lead_events)
    problems += item_problems(items, details)
    problems += run_problems(run, rows, details, events)
    return problems


def test_the_fixtures_agree_with_each_other(client: TestClient) -> None:
    assert all_problems(client) == []


def drop_ask_count(rows: Any) -> None:
    rows[0]["ask_count"] += 1


def drop_an_item(items: Any) -> None:
    items.pop()


def change_a_count(run: Any) -> None:
    run["summary"]["waiting_on_underwriter"] += 1


def change_a_payload_hash(detail: Any) -> None:
    detail["drafts"][0]["payload_hash"] = "0" * 64


def move_an_event(events: Any) -> None:
    events["events"][0]["lead_id"] = LEAD_IDS[9]


def swap_the_first_rows(rows: Any) -> None:
    rows[0], rows[1] = rows[1], rows[0]


# Each break touches one file, and the check that owns the agreement reports it.
BREAKS: list[tuple[str, Callable[[Any], None], str]] = [
    ("leads.json", drop_ask_count, "ask_count"),
    ("leads.json", swap_the_first_rows, "section 11 order"),
    ("items.json", drop_an_item, "differ from open item blockers"),
    ("run.json", change_a_count, "waiting_on_underwriter"),
    (f"lead/{LEAD_IDS[0]}.json", change_a_payload_hash, "payload_hash"),
    (f"events/{LEAD_IDS[0]}.json", move_an_event, "is for"),
]


@pytest.mark.parametrize(("name", "change", "expected"), BREAKS)
def test_a_broken_agreement_is_reported(
    tmp_path: Path, name: str, change: Callable[[Any], None], expected: str
) -> None:
    broken = copy_fixtures(tmp_path)
    edit_json(broken / name, change)
    problems = all_problems(standin_client(broken))
    assert any(expected in problem for problem in problems), problems


# ---- the fixtures show the variety section 5 describes ----------------------------------------


@pytest.fixture(scope="module")
def details(client: TestClient) -> dict[str, LeadDetail]:
    return {
        lead_id: LeadDetail.model_validate(get_json(client, f"/api/leads/{lead_id}"))
        for lead_id in LEAD_IDS
    }


def test_the_leads_follow_section_5(details: dict[str, LeadDetail]) -> None:
    def kinds(lead: int) -> set[str]:
        return {b.kind for b in details[LEAD_IDS[lead]].blockers}

    def draft_kinds(lead: int) -> set[str]:
        return {d.kind for d in details[LEAD_IDS[lead]].drafts}

    assert draft_kinds(0) == {"decline_notice"}
    assert details[LEAD_IDS[0]].plan is not None and details[LEAD_IDS[0]].plan.proposed_decline  # type: ignore[union-attr]
    for lead in (3, 6):
        choices = [c.choice_id for c in details[LEAD_IDS[lead]].open_choices]
        assert choices == ["I13.fire_fail"]
        assert kinds(lead) == {"underwriter_question", "producer_reply"}
    for lead in (1, 2, 4, 5, 7, 8, 9):
        assert kinds(lead) == {"producer_reply"}
        assert draft_kinds(lead) == {"routine_request"}
    assert kinds(0) == {"underwriter_review"}


def test_the_fixtures_show_every_kind_the_detail_pane_renders(
    details: dict[str, LeadDetail],
) -> None:
    every = list(details.values())
    facts = [f for d in every for f in d.facts]
    pages = [p for d in every for p in d.playbook]
    assert {f.source for f in facts} >= {"submitted", "fetched", "derived", "assumed"}
    assert any(f.is_stub for f in facts)
    assert any(f.key == "p_f" and not f.is_stub for f in facts)
    assert {n.kind for d in every for n in d.notes} >= {"not_evaluated", "unevaluated_skill"}
    assert {d.state for dd in every for d in dd.drafts} >= {"sent", "draft"}
    assert {link.kind for d in every for link in d.links} == {"search", "map"}
    assert {p.result for p in pages} == {
        None,
        "decided",
        "undecided",
        "declines_on_every_branch",
        "not_evaluated",
    }
    assert {p.applies for p in pages} == {"yes", "no", "unknown"}
    assert any(p.exception for p in pages) and any(not p.exception for p in pages)
    assert all(
        any(n.ref == "plumbing" for n in d.notes) and any(n.ref == "electrical" for n in d.notes)
        for d in every
    )


def test_the_proposed_commands_fit_their_command_payloads(client: TestClient) -> None:
    proposals = TypeAdapter(list[ProposalView]).validate_python(get_json(client, "/api/proposals"))
    commands = [p for p in proposals if p.kind == "command"]
    assert commands
    for proposal in commands:
        ProposeCommandPayload.model_validate(proposal.payload)
