# ABOUTME: Tests of tools/standin_api.py: it serves the A.5 read routes from tests/fixtures/ui through the app's own route declarations, and the fixtures fit their response models and agree with each other.
# ABOUTME: Each agreement check also runs against a deliberately broken copy of the fixtures, so a check that cannot fail is caught.
import hashlib
import importlib.util
import json
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
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


def business_days_between(start: datetime, end: datetime) -> float:
    """Days from `start` to `end` that fall on a Monday to Friday in UTC (7.6), as a fraction."""
    total = 0.0
    cursor = start
    while cursor < end:
        midnight = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        stop = min(midnight, end)
        if cursor.weekday() < 5:
            total += (stop - cursor).total_seconds() / 86400
        cursor = stop
    return total


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
    age = business_days_between(parse_time(str(received.payload["received_at"])), sim_now)
    if abs(row.age_business_days - age) > 0.01:
        problems.append(
            f"{lead}: age {row.age_business_days} != {age:.2f} business days since receipt"
        )
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
    # No seed-42 lead has a not_found lookup or a year_built below 1950 with the wiring question
    # missing, so no fact is `assumed` (9.3 rule 4).
    assert {f.source for f in facts} == {"submitted", "fetched", "derived"}
    assert any(f.is_stub for f in facts)
    assert any(f.key == "p_f" and not f.is_stub for f in facts)
    assert {n.kind for d in every for n in d.notes} >= {"not_evaluated", "unevaluated_skill"}
    assert {d.state for dd in every for d in dd.drafts} >= {"sent", "draft"}
    assert {link.kind for d in every for link in d.links} == {"search", "map"}
    # An open conflict makes a page undecided (9.6), so no seed-42 page declines on every branch.
    assert {p.result for p in pages} == {None, "decided", "undecided", "not_evaluated"}
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


# ---- the fixtures follow the architecture's rules ---------------------------------------------


@pytest.fixture(scope="module")
def histories(client: TestClient) -> dict[str, LeadEvents]:
    return {
        lead_id: LeadEvents.model_validate(get_json(client, f"/api/leads/{lead_id}/events"))
        for lead_id in LEAD_IDS
    }


def lead_events(histories: dict[str, LeadEvents], lead: int, event_type: str) -> list[Any]:
    return [e for e in histories[LEAD_IDS[lead]].events if e.type.value == event_type]


def test_lead_000_declines_on_post_and_pier_alone(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    # Section 2.2: leads 000 (8 months) and 003 (3 months) hold the occupancy conflict, a primary
    # home with months unoccupied. Section 9.6: a fact in an open conflict is unknown to the
    # graphs, so the Occupancy page is undecided and contributes nothing. Section 5: lead 000
    # declines on the pier foundation that supports living area, rule trace 07:LIVING, 07:D1.
    detail = details[LEAD_IDS[0]]
    assert detail.plan is not None
    declines = [p for p in detail.plan.effects if p.effect.type == "decline"]
    assert [p.trace.board_path for p in declines] == [["07:LIVING", "07:D1"]]
    assert detail.plan.declines_on_every_branch == []
    assert detail.plan.proposed_decline
    occupancy = next(p for p in detail.playbook if p.graph == "occupancy")
    assert (occupancy.applies, occupancy.result) == ("unknown", "undecided")
    assert occupancy.waits_on == ["dwelling_use_type", "months_unoccupied"]
    assert occupancy.effects == [] and not occupancy.declines_on_every_branch
    post_and_pier = next(p for p in detail.playbook if p.graph == "post_and_pier")
    assert [e.effect.type for e in post_and_pier.effects] == ["decline"]
    assert all(p.result != "declines_on_every_branch" for p in detail.playbook)
    for lead in (0, 3):
        opened = lead_events(histories, lead, "conflict_opened")
        assert [e.payload["validator"] for e in opened] == [
            "conf_primary_use_and_months_unoccupied"
        ]


def test_lead_000_sends_only_a_decline_notice_of_round_0(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents], client: TestClient
) -> None:
    # Section 7.5: a decline notice carries round 0 when the lead has had no request. Section 9.6
    # precedence 1: a decline suppresses every request, a confirmation included.
    detail = details[LEAD_IDS[0]]
    intents = lead_events(histories, 0, "intent_created")
    assert [(e.payload["kind"], e.payload["round"]) for e in intents] == [("decline_notice", 0)]
    assert [(d.kind, d.round) for d in detail.drafts] == [("decline_notice", 0)]
    assert not detail.drafts[0].intent_id.endswith("R1")
    assert intents[0].payload["ask_ids"] == []
    rows = get_json(client, "/api/leads")
    assert next(r for r in rows if r["lead_id"] == LEAD_IDS[0])["ask_count"] == 0


# The section 9.4 table: each provider field and the lead fields its lookup needs.
FULL_ADDRESS = ("street_address", "city", "state", "zip")
LOOKUP_INPUTS: dict[str, tuple[str, ...]] = {
    "broker_tier": (),
    "has_primary_policy_with_stand": (),
    "replacement_cost": FULL_ADDRESS,
    "protection_class": FULL_ADDRESS,
    "kyc_score": ("first_name", "last_name", "insured_dob"),
    "p_f": FULL_ADDRESS,
    "slope_angle_deg": FULL_ADDRESS,
    "min_distance_to_neighbor_ft": FULL_ADDRESS,
    "vegetation_clearance": FULL_ADDRESS,
    "road_access": FULL_ADDRESS,
}

# The provider fields each seed-42 payload carries as a value, as the leadgen container serves
# them. Section 9.4: a value an archetype set stays on the lead and is never replaced.
PAYLOAD_PROVIDER_VALUES: dict[int, dict[str, Any]] = {
    0: {"p_f": 0.13, "slope_angle_deg": 10.1},
    1: {
        "broker_tier": "Tier 1",
        "has_primary_policy_with_stand": False,
        "protection_class": "5",
        "road_access": "Multiple Access Points",
    },
    2: {
        "broker_tier": "Tier 2",
        "replacement_cost": 489881,
        "protection_class": "5",
        "kyc_score": 8,
        "slope_angle_deg": 5.6,
        "min_distance_to_neighbor_ft": 30,
    },
    3: {
        "p_f": 0.79,
        "slope_angle_deg": 30.0,
        "min_distance_to_neighbor_ft": 14,
        "vegetation_clearance": "Too Close",
    },
    4: {
        "has_primary_policy_with_stand": False,
        "kyc_score": 4,
        "road_access": "Multiple Access Points",
    },
    5: {"protection_class": "5", "kyc_score": 6},
    6: {
        "p_f": 0.89,
        "slope_angle_deg": 29.4,
        "min_distance_to_neighbor_ft": 14,
        "vegetation_clearance": "Too Close",
    },
    7: {"kyc_score": 9, "p_f": 0.1},
    8: {
        "broker_tier": "Tier 2",
        "has_primary_policy_with_stand": False,
        "protection_class": "5",
        "kyc_score": 2,
        "p_f": 0.14,
        "road_access": "Multiple Access Points",
        "vegetation_clearance": "Adequate",
    },
    9: {
        "broker_tier": "Tier 2",
        "has_primary_policy_with_stand": False,
        "replacement_cost": 978879,
        "protection_class": "4",
        "kyc_score": 1,
        "min_distance_to_neighbor_ft": 115,
        "slope_angle_deg": 10.6,
        "vegetation_clearance": "Adequate",
    },
}


def lookup_problems(
    lead: int, detail: LeadDetail, events: LeadEvents, payload: dict[str, Any]
) -> list[str]:
    """Each provider field follows 9.4: a payload value is a submitted fact with no lookup; the
    input check runs first, so a missing input gives `blocked` and no fact; otherwise the value is
    fetched."""
    problems: list[str] = []
    facts = {f.key: f for f in detail.facts}
    calls: dict[str, list[Any]] = {}
    for event in events.events:
        if event.type.value == "provider_called":
            calls.setdefault(str(event.payload["key"]), []).append(event.payload)
    for field, inputs in LOOKUP_INPUTS.items():
        fact, field_calls = facts.get(field), calls.get(field, [])
        if field in payload:
            if fact is None or fact.source != "submitted" or fact.value != payload[field]:
                problems.append(f"{lead}: {field} is not the submitted payload value")
            if field_calls:
                problems.append(f"{lead}: {field} is on the payload and was looked up")
            continue
        missing = [name for name in inputs if name not in facts]
        if len(field_calls) != 1:
            problems.append(f"{lead}: {field} has {len(field_calls)} provider_called events")
            continue
        call = field_calls[0]
        if missing:
            if fact is not None:
                problems.append(f"{lead}: {field} has a fact though {missing} are missing")
            if (call["status"], call["missing_inputs"]) != ("blocked", missing):
                problems.append(f"{lead}: {field} lookup is not blocked on {missing}")
        else:
            if fact is None or fact.source != "fetched" or fact.value != call["value"]:
                problems.append(f"{lead}: {field} is not the fetched value")
            if call["status"] != "found" or call["missing_inputs"]:
                problems.append(f"{lead}: {field} lookup has all its inputs and is not found")
    return problems


def test_the_lookups_follow_section_9_4(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    problems: list[str] = []
    for lead, payload in PAYLOAD_PROVIDER_VALUES.items():
        lead_id = LEAD_IDS[lead]
        problems += lookup_problems(lead, details[lead_id], histories[lead_id], payload)
    assert problems == []


def test_a_blocked_lookup_leaves_no_fact_and_a_blocked_triage_resolution(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    # Lead 000 has no address, so every address lookup is blocked on the four address fields.
    # Section 9.2: a blocked lookup gives resolution `blocked`, and the four fields conditional on
    # protection class 9 or 10 are blocked on `protection_class`, not asked.
    detail = details[LEAD_IDS[0]]
    keys = {f.key for f in detail.facts}
    assert not keys & {"protection_class", "replacement_cost", "kyc_score", "road_access"}
    triage = lead_events(histories, 0, "triage_completed")[0].payload["fields"]
    for field in ("protection_class", "replacement_cost", "kyc_score", "road_access"):
        assert triage[field]["resolution"] == "blocked", field  # type: ignore[index]
    assert triage["kyc_score"]["depends_on"] == ["first_name", "last_name", "insured_dob"]  # type: ignore[index]
    assert triage["road_access"]["depends_on"] == list(FULL_ADDRESS)  # type: ignore[index]
    conditional = ("fire_dept_response_time", "alternative_water_source")
    conditional += ("interior_sprinklers", "physical_barriers")
    for lead in (0, 3, 6, 7):
        triage = lead_events(histories, lead, "triage_completed")[0].payload["fields"]
        for field in conditional:
            assert triage[field]["resolution"] == "blocked", (lead, field)  # type: ignore[index]
            assert triage[field]["depends_on"] == ["protection_class"]  # type: ignore[index]
        page = next(p for p in details[LEAD_IDS[lead]].playbook if p.graph == "pc_9_and_10")
        assert (page.applies, page.result, page.waits_on) == (
            "unknown",
            "undecided",
            ["protection_class"],
        )
    # Where the lookup is found, the field is not blocked and there is no assumed value.
    triage = lead_events(histories, 4, "triage_completed")[0].payload["fields"]
    assert all(entry["resolution"] != "blocked" for entry in triage.values())  # type: ignore[attr-defined]
    assert all(f.source != "assumed" for d in details.values() for f in d.facts)


def test_a_payload_value_is_never_a_fetched_fact(details: dict[str, LeadDetail]) -> None:
    def source(lead: int, key: str) -> str | None:
        fact = next((f for f in details[LEAD_IDS[lead]].facts if f.key == key), None)
        return None if fact is None else fact.source

    assert [source(lead, "p_f") for lead in (3, 6)] == ["submitted", "submitted"]
    assert [source(lead, "kyc_score") for lead in (2, 5, 7)] == ["submitted"] * 3
    # The one fetched `p_f` that stays: lead 009's payload has none and its address is complete.
    assert source(9, "p_f") == "fetched"


REGISTRY = json.loads((ROOT / "docs" / "brief" / "field_registry.json").read_text("utf-8"))[
    "fields"
]
OPENING = (
    "Thank you for your submission. To complete the quote we need the items below. "
    "One reply covering all of them is ideal."
)


def address_or_id(detail: LeadDetail) -> str:
    street = next((f.value for f in detail.facts if f.key == "street_address"), None)
    return str(street) if street else detail.lead_id


def message_problems(detail: LeadDetail, events: LeadEvents) -> list[str]:
    """A.8 and 10.2: the subject and opening, and the asks grouped by registry section in registry
    order, numbered, with catalogue questions and confirmations in a last group."""
    problems: list[str] = []
    intents = {
        e.payload["intent_id"]: e.payload for e in events.events if e.type.value == "intent_created"
    }
    for draft in detail.drafts:
        lead = detail.lead_id
        subject = {
            "routine_request": "Information needed for your quote: ",
            "sensitive_request": "Information needed for your quote: ",
            "quote_packet": "Your quote: ",
            "decline_notice": "Regarding your submission: ",
        }[draft.kind] + address_or_id(detail)
        if draft.subject != subject:
            problems.append(f"{lead}: subject {draft.subject!r} is not {subject!r}")
        if draft.kind not in REQUEST_KINDS:
            continue
        if not draft.body.startswith(OPENING + "\n\n"):
            problems.append(f"{lead}: the body does not open with A.8's sentence")
        ask_ids = intents[draft.intent_id]["ask_ids"]
        heading, numbers, groups = "", [], []
        for line in draft.body.removeprefix(OPENING).strip().splitlines():
            if not line.strip():
                continue
            number, dot, _ = line.partition(". ")
            if dot and number.isdigit():
                numbers.append(int(number))
                groups.append(heading)
            else:
                heading = line
        if numbers != list(range(1, len(ask_ids) + 1)):
            problems.append(f"{lead}: the asks are not numbered 1 to {len(ask_ids)}")
        if len(groups) == len(ask_ids):
            for ask, group in zip(ask_ids, groups, strict=True):
                expected = REGISTRY[ask]["section"] if ask in REGISTRY else "Additional questions"
                if group != expected:
                    problems.append(f"{lead}: {ask} sits under {group!r}, not {expected!r}")
        registry_asks = [a for a in ask_ids if a in REGISTRY]
        if registry_asks != sorted(registry_asks, key=list(REGISTRY).index):
            problems.append(f"{lead}: the asks are not in registry order")
        if ask_ids[: len(registry_asks)] != registry_asks:
            problems.append(f"{lead}: a confirmation comes before a registry ask")
    return problems


def test_the_messages_follow_appendix_a8(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    problems: list[str] = []
    for lead_id in LEAD_IDS:
        problems += message_problems(details[lead_id], histories[lead_id])
    assert problems == []
    requests = [d for detail in details.values() for d in detail.drafts if d.kind in REQUEST_KINDS]
    assert len(requests) == 9
    assert all(d.subject.startswith("Information needed for your quote: ") for d in requests)
    assert all(d.body.startswith(OPENING) for d in requests)
    # Lead 001 has no street address, so its subject names the lead id (A.8).
    assert requests[0].subject.endswith(LEAD_IDS[1])


def test_the_decline_notice_states_no_decline_reason(details: dict[str, LeadDetail]) -> None:
    # Section 10.2: no message contains a decline reason, pricing or internal notes.
    notice = details[LEAD_IDS[0]].drafts[0]
    assert notice.subject == f"Regarding your submission: {LEAD_IDS[0]}"
    for reason in ("pier", "foundation", "living", "occupan", "unoccupied", "fire", "rule"):
        assert reason not in notice.body.lower(), reason
    for pricing in ("$", "premium", "price"):
        assert pricing not in notice.body.lower(), pricing


def test_a_lookup_check_reports_a_wrong_source_and_a_wrong_status(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    # Lead 003's p_f is on its payload: a fetched copy and a lookup event are both reported.
    lead_id = LEAD_IDS[3]
    detail = details[lead_id].model_copy(deep=True)
    next(f for f in detail.facts if f.key == "p_f").source = "fetched"
    reported = lookup_problems(3, detail, histories[lead_id], PAYLOAD_PROVIDER_VALUES[3])
    assert any("p_f is not the submitted payload value" in p for p in reported)
    # Lead 000's kyc_score lookup is blocked: a found status is reported.
    lead_id = LEAD_IDS[0]
    history = histories[lead_id].model_copy(deep=True)
    call = next(
        e
        for e in history.events
        if e.type.value == "provider_called" and e.payload["key"] == "kyc_score"
    )
    call.payload = {**call.payload, "status": "found", "missing_inputs": []}
    reported = lookup_problems(0, details[lead_id], history, PAYLOAD_PROVIDER_VALUES[0])
    assert any("kyc_score lookup is not blocked" in p for p in reported)


def test_a_wrong_message_is_reported(
    details: dict[str, LeadDetail], histories: dict[str, LeadEvents]
) -> None:
    lead_id = LEAD_IDS[8]
    detail = details[lead_id].model_copy(deep=True)
    detail.drafts[0].subject = f"Information needed to quote {lead_id}"
    detail.drafts[0].body = detail.drafts[0].body.replace(OPENING, "Hello,")
    reported = message_problems(detail, histories[lead_id])
    assert any("subject" in p for p in reported)
    assert any("does not open" in p for p in reported)


def test_every_skill_is_passing_or_untested_with_a_threshold_of_1(client: TestClient) -> None:
    # Section 8: a failing deterministic skill stops its lead with a `data` blocker, and every
    # lead here has run to a rendered message. A.10: the pass threshold is 1.0.
    skills = TypeAdapter(list[SkillView]).validate_python(get_json(client, "/api/skills"))
    assert all(skill.status != "failing" for skill in skills)
    assert all(skill.threshold == 1.0 for skill in skills)
    by_name = {skill.name: skill for skill in skills}
    assert by_name["render_message"].status == "passing"
    assert by_name["read_reply"].status == "untested"


def test_the_age_counts_business_days_not_calendar_days() -> None:
    # Friday 17:00 to Monday 08:00 UTC spans a weekend: 7 hours on Friday and 8 on Monday.
    friday, monday = parse_time("2026-06-26T17:00:00Z"), parse_time("2026-06-29T08:00:00Z")
    assert business_days_between(friday, monday) == pytest.approx(15 / 24)
    assert (monday - friday).total_seconds() / 86400 == pytest.approx(2 + 15 / 24)
    assert business_days_between(parse_time("2026-06-29T05:00:00Z"), monday) == pytest.approx(
        3 / 24
    )


def set_clock_and_ages(
    directory: Path, sim_now: str, age: Callable[[datetime, datetime], float]
) -> None:
    """Move the run's clock and rewrite each queue row's age as `age` computes it."""
    edit_json(directory / "run.json", lambda run: run.update(sim_now=sim_now))

    def reage(rows: Any) -> None:
        for row in rows:
            history = json.loads(
                (directory / "events" / f"{row['lead_id']}.json").read_text("utf-8")
            )
            received = next(e for e in history["events"] if e["type"] == "lead_received")
            row["age_business_days"] = round(
                age(parse_time(received["payload"]["received_at"]), parse_time(sim_now)), 2
            )
            row["service_level_breached"] = row["age_business_days"] > SERVICE_LEVEL_DAYS

    edit_json(directory / "leads.json", reage)


def calendar_days_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86400


def age_problems(directory: Path) -> list[str]:
    return [p for p in all_problems(standin_client(directory)) if " age " in p]


def test_a_clock_across_a_weekend_ages_a_lead_in_business_days(tmp_path: Path) -> None:
    # The first pass ran on Monday 2026-06-29; a clock on Monday 2026-07-06 spans one weekend.
    sim_now = "2026-07-06T06:30:00Z"
    received = parse_time("2026-06-29T05:06:00Z")
    assert calendar_days_between(received, parse_time(sim_now)) - business_days_between(
        received, parse_time(sim_now)
    ) == pytest.approx(2.0)
    business = copy_fixtures(tmp_path / "business")
    set_clock_and_ages(business, sim_now, business_days_between)
    assert age_problems(business) == []
    calendar = copy_fixtures(tmp_path / "calendar")
    set_clock_and_ages(calendar, sim_now, calendar_days_between)
    assert len(age_problems(calendar)) == len(LEAD_IDS)
