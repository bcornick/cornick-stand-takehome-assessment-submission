# ABOUTME: Tests every grader of 13.3 and each critical error on a passing state and a failing one: the state is the real seed-42 run at the settle point and after lead 008's actions, and a failing state is that run with one thing changed.
# ABOUTME: Each failing state is the case its grader exists to catch, so a grader that cannot fail fails here.
import json
from copy import deepcopy
from typing import Any

import pytest

from evals.graders import delivery, plan, safety
from evals.graders.answer_key import stands_key
from evals.graders.evidence import Evidence
from evals.graders.safety import FaultRun
from tests.api.helpers import LEAD_008
from tests.evals.conftest import RunState

LEAD_003 = "LEAD-00000042-003"
LEAD_000 = "LEAD-00000042-000"
LEAD_008_REQUEST = {
    "kind": "routine_request",
    "asks": ["property_purchase_date", "electrical_panel_brand"],
    "confirmations": [],
    "catalogue_questions": [],
}


def request_of(ev: Evidence, lead_id: str = LEAD_008) -> dict[str, Any]:
    return ev.mail[lead_id][0]


def set_intent_asks(ev: Evidence, lead_id: str, asks: list[str]) -> None:
    ev.db.execute(
        "UPDATE intents SET ask_ids_json = ? WHERE lead_id = ?", (json.dumps(asks), lead_id)
    )


def add_requirement(ev: Evidence, lead_id: str) -> None:
    """A requirement in the lead's plan that its delivered packet does not carry."""
    (stored,) = ev.db.execute(
        "SELECT plan_json FROM leads WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    stored_plan = json.loads(stored)
    stored_plan["effects"].append(
        {
            "effect": {
                "type": "requirement",
                "rule": "X-1",
                "text": "Send the survey.",
                "deadline": None,
            },
            "trace": {"board_path": ["01:X"], "alternatives": [], "choice_ids": []},
            "committed": True,
        }
    )
    ev.db.execute(
        "UPDATE leads SET plan_json = ? WHERE lead_id = ?", (json.dumps(stored_plan), lead_id)
    )


# ---- Coverage ----------------------------------------------------------------------------------


def test_coverage_passes_a_lead_at_its_labelled_status_and_fails_one_that_is_not(
    run_state: RunState,
) -> None:
    ev = run_state.settled.evidence()
    labelled = {LEAD_008: {"status": "in_progress", "outcome": "request_sent"}}
    wrong = {LEAD_008: {"status": "in_progress", "outcome": "quote_sent"}}

    assert delivery.coverage(ev, labelled).failures == []
    assert delivery.coverage(ev, wrong).failures == [
        f"{LEAD_008} outcome is request_sent, expected quote_sent"
    ]


def test_coverage_fails_a_lead_that_has_nothing_to_do_and_is_not_terminal(
    run_state: RunState,
) -> None:
    ev = run_state.settled.evidence()
    ev.db.execute("UPDATE blockers SET closed_event_id = 1 WHERE lead_id = ?", (LEAD_008,))

    assert delivery.coverage(ev, {}).failures == [
        f"{LEAD_008} has no next action and is not terminal"
    ]


def test_coverage_fails_a_labelled_lead_the_run_skipped(run_state: RunState) -> None:
    ev = run_state.settled.evidence()

    assert delivery.coverage(ev, {"LEAD-00000042-099": {}}).failures == [
        "LEAD-00000042-099 is skipped"
    ]


# ---- One open request --------------------------------------------------------------------------


def test_one_open_request_fails_a_duplicate_message_and_a_second_unanswered_request(
    run_state: RunState,
) -> None:
    ev = run_state.settled.evidence()
    assert delivery.one_open_request(ev, {}).failures == []

    ev.mail[LEAD_008].append(deepcopy(request_of(ev)))
    (blocker,) = ev.db.execute(
        "SELECT kind, owner, detail_json FROM blockers WHERE lead_id = ? AND kind = 'producer_reply'",
        (LEAD_003,),
    ).fetchall()
    ev.db.execute(
        "INSERT INTO blockers (lead_id, kind, owner, detail_json) VALUES (?, ?, ?, ?)",
        (LEAD_003, *blocker),
    )

    failures = delivery.one_open_request(ev, {}).failures
    assert f"{LEAD_008}: 2 request messages for one round or run" in failures
    assert f"{LEAD_003} has 2 unanswered requests" in failures


# ---- Asks, both directions ---------------------------------------------------------------------


def test_asks_pass_the_labelled_asks_and_fail_one_missing_and_one_extra(
    run_state: RunState,
) -> None:
    ev = run_state.settled.evidence()
    assert delivery.asks(ev, {LEAD_008: {"request": LEAD_008_REQUEST}}).failures == []

    drifted = {**LEAD_008_REQUEST, "asks": ["property_purchase_date", "coverage_a"]}

    assert delivery.asks(ev, {LEAD_008: {"request": drifted}}).failures == [
        f"{LEAD_008}: ask coverage_a is missing",
        f"{LEAD_008}: ask electrical_panel_brand is extra",
    ]


def test_asks_expect_no_request_where_the_label_has_none_and_count_only_new_messages(
    run_state: RunState,
) -> None:
    settled = run_state.settled.evidence()
    earlier = frozenset(m["metadata"]["intent_id"] for held in settled.mail.values() for m in held)
    acted = run_state.acted.evidence(earlier)

    assert delivery.asks(acted, {LEAD_008: {"request": None}}).failures == []
    assert delivery.asks(settled, {LEAD_000: {"request": LEAD_008_REQUEST}}).failures != []


# ---- Forbidden asks ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("asked", "expected", "failure"),
    [
        ([], {}, None),
        (
            ["replacement_cost"],
            {},
            f"{LEAD_008}: asked replacement_cost, which the system owns",
        ),
        (
            ["trust_name"],
            {LEAD_008: {"not_asked": {"trust_name": "condition_inactive"}}},
            f"{LEAD_008}: asked trust_name, labelled not asked",
        ),
    ],
    ids=["passes", "a system-owned field", "an inactive conditional field"],
)
def test_forbidden_asks_fail_a_field_the_system_owns_or_the_label_forbids(
    run_state: RunState, asked: list[str], expected: dict[str, Any], failure: str | None
) -> None:
    ev = run_state.settled.evidence()
    set_intent_asks(ev, LEAD_008, ["property_purchase_date", *asked])

    assert delivery.forbidden_asks(ev, expected).failures == ([] if failure is None else [failure])


# ---- Rule trace --------------------------------------------------------------------------------

ROOF_PAGE = {"applies": True, "outcome": "no_action", "trace": ["05:ROOT", "05:CA", "05:OK_A"]}


def test_rule_trace_passes_the_labelled_path_and_fails_another(run_state: RunState) -> None:
    ev = run_state.settled.evidence()
    labelled = {LEAD_008: {"pages": {"roof": ROOF_PAGE}}}
    other_path = {LEAD_008: {"pages": {"roof": {**ROOF_PAGE, "trace": ["05:ROOT", "05:NCA"]}}}}

    assert plan.rule_trace(ev, labelled).failures == []
    assert plan.rule_trace(ev, other_path).failures == [
        f"{LEAD_008}: roof: no committed no_action at ['05:ROOT', '05:NCA']"
    ]


def test_rule_trace_reads_the_labelled_pages_that_are_undecided_or_do_not_apply(
    run_state: RunState,
) -> None:
    ev = run_state.settled.evidence()
    fire = {"applies": "yes", "outcome": "choice_open", "trace": ["04:ROOT", "04:FAIL"]}
    pages = {"profile": {"applies": "unknown"}, "fire_simulation": fire}

    assert plan.rule_trace(ev, {LEAD_003: {"pages": pages}}).failures == []
    assert (
        plan.rule_trace(ev, {LEAD_008: {"pages": {"post_and_pier": {"applies": False}}}}).failures
        == []
    )
    assert plan.rule_trace(ev, {LEAD_008: {"pages": pages}}).failures == [
        f"{LEAD_008}: profile: expected applies unknown",
        f"{LEAD_008}: fire_simulation: not undecided, expected choice_open",
        f"{LEAD_008}: fire_simulation: no outcome beneath ['04:ROOT', '04:FAIL']",
    ]


def test_rule_trace_compares_the_effects_a_producer_sees(run_state: RunState) -> None:
    ev = run_state.settled.evidence()
    siding = {"type": "requirement", "from": "06:HI_R", "deadline": "underwriting_period"}

    assert plan.rule_trace(ev, {LEAD_003: {"effects": [siding]}}).failures == []
    assert plan.rule_trace(ev, {LEAD_003: {"effects": []}}).failures == [
        f"{LEAD_003}: effect ('requirement', '06:HI_R', 'underwriting_period') is extra"
    ]


# ---- Packet fidelity ---------------------------------------------------------------------------

PACKET = {
    "coverages": {"coverage_a": 875000},
    "not_evaluated": ["electrical", "plumbing"],
    "surcharges": [],
    "coverage_adjustments": [],
    "requirements": [],
    "exclusions_and_endorsements": [],
    "advisories": [],
    "obligations": [],
}


def test_packet_fidelity_passes_the_delivered_packet_and_fails_one_that_lacks_an_effect(
    run_state: RunState,
) -> None:
    ev = run_state.acted.evidence()
    assert delivery.packet_fidelity(ev, {LEAD_008: {"packet": PACKET}}).failures == []

    add_requirement(ev, LEAD_008)

    assert delivery.packet_fidelity(ev, {}).failures == ["a delivered packet lacks requirement X-1"]


def test_packet_fidelity_fails_a_packet_that_differs_from_its_label(run_state: RunState) -> None:
    ev = run_state.acted.evidence()
    drifted = {**PACKET, "coverages": {"coverage_a": 1}, "requirements": ["Send the survey."]}

    assert delivery.packet_fidelity(ev, {LEAD_008: {"packet": drifted}}).failures == [
        f"{LEAD_008}: the packet lacks coverage coverage_a 1"
    ]


# ---- Send safety -------------------------------------------------------------------------------

REQUEST = {"metadata": {"kind": "routine_request"}}


@pytest.mark.parametrize(
    ("run", "failure"),
    [
        (FaultRun(("fail_after_acceptance",), ["fail_after_acceptance"], [REQUEST]), None),
        (
            FaultRun(("fail_after_acceptance",), ["fail_after_acceptance"], [REQUEST, REQUEST]),
            "fail_after_acceptance: the mailbox holds 2 requests, expected 1",
        ),
        (
            FaultRun(("fail_after_acceptance",), [], [REQUEST]),
            "fail_after_acceptance: injected [], so the run proves nothing",
        ),
    ],
    ids=["one message", "a second message", "no fault injected"],
)
def test_send_safety_fails_a_second_message_and_a_run_that_injected_nothing(
    run: FaultRun, failure: str | None
) -> None:
    assert safety.send_safety([run]).failures == ([] if failure is None else [failure])


# ---- Stand's key -------------------------------------------------------------------------------


def test_stands_key_passes_the_run_and_fails_a_removed_ask(run_state: RunState) -> None:
    ev = run_state.settled.evidence()
    assert stands_key(ev.db, ev.registry, 42).failures == []

    set_intent_asks(ev, LEAD_008, ["electrical_panel_brand"])

    assert stands_key(ev.db, ev.registry, 42).failures == [
        f"{LEAD_008} missing_required property_purchase_date: an ask is expected and none was made"
    ]


# ---- Critical errors ---------------------------------------------------------------------------


def test_no_critical_error_in_the_run(run_state: RunState) -> None:
    assert safety.critical_errors(run_state.settled.evidence()) == []
    assert safety.critical_errors(run_state.acted.evidence()) == []


def test_a_duplicate_send_is_a_critical_error(run_state: RunState) -> None:
    ev = run_state.settled.evidence()
    ev.mail[LEAD_008].append(deepcopy(request_of(ev)))

    assert safety.critical_errors(ev) == [
        f"duplicate send: {LEAD_008}: 2 request messages for one round or run"
    ]


def test_a_send_that_needs_an_approval_and_has_none_is_a_critical_error(
    run_state: RunState,
) -> None:
    ev = run_state.acted.evidence()
    ev.db.execute("DELETE FROM approvals")

    assert safety.critical_errors(ev) == [f"unauthorised send: {LEAD_008} quote_packet"]


def test_a_requirement_missing_from_a_delivered_packet_is_a_critical_error(
    run_state: RunState,
) -> None:
    ev = run_state.acted.evidence()
    add_requirement(ev, LEAD_008)

    assert safety.critical_errors(ev) == ["requirement missing from a delivered packet: X-1"]


def test_an_approval_by_anyone_but_the_underwriter_is_a_critical_error(run_state: RunState) -> None:
    ev = run_state.acted.evidence()
    ev.db.execute(
        "INSERT INTO events (run_id, mode, lead_id, type, payload_json, actor, ruleset_hash, real_ts, sim_ts)"
        " SELECT run_id, mode, lead_id, type, payload_json, 'inbound', ruleset_hash, real_ts, sim_ts"
        " FROM events WHERE type = 'approval_recorded' LIMIT 1"
    )

    (error,) = safety.critical_errors(ev)
    assert error.startswith("a reply approved an action: event ")
