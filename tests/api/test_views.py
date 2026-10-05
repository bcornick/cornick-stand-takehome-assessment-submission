# ABOUTME: Tests of the route shapes: the section 11 queue columns, the lead detail, the items view, the A.11 commands and the vertical's vocabularies.
# ABOUTME: The architecture's lists are written out here and compared with the models and with the app's OpenAPI document.
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from uwh.api import views
from uwh.api.app import create_app
from uwh.runtime.event_types import PAYLOAD_MODELS, EventType
from uwh.settings import Settings
from uwh.skills import vertical

LEAD = "LEAD-00000042-003"


def document() -> dict[str, Any]:
    return create_app(Settings.load({"UWH_DB": "unused.db"})).openapi()


def schema(name: str) -> dict[str, Any]:
    return document()["components"]["schemas"][name]  # type: ignore[no-any-return]


def deref(doc: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        target: Any = doc
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return target  # type: ignore[no-any-return]
    return node


def all_schemas(node: Any) -> Any:
    """Every dict in the document, to walk property names."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from all_schemas(value)
    elif isinstance(node, list):
        for value in node:
            yield from all_schemas(value)


# ---- the queue (section 11) ------------------------------------------------------------------

# "One row per lead: status chip, primary next action, who it waits on, age against a
# two-business-day service level, effective date, ask count", plus the ordering group.
QUEUE_COLUMNS = {
    "lead_id",
    "status",
    "primary_next_action",
    "waits_on",
    "age_business_days",
    "service_level_breached",
    "effective_date",
    "ask_count",
    "group",
}
QUEUE_GROUPS = ["blocked_on_underwriter", "waiting_on_data_or_producer", "finished"]


def queue_row(**changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "lead_id": LEAD,
        "status": "in_progress",
        "primary_next_action": "underwriter_question",
        "waits_on": "underwriter",
        "age_business_days": 0.5,
        "service_level_breached": False,
        "effective_date": "2026-07-15",
        "ask_count": 3,
        "group": "blocked_on_underwriter",
    }
    return row | changes


def test_queue_row_carries_every_section_11_column() -> None:
    assert set(views.QueueRow.model_fields) == QUEUE_COLUMNS
    assert set(schema("QueueRow")["properties"]) == QUEUE_COLUMNS


def test_queue_row_of_a_finished_lead_has_no_next_action_and_no_owner() -> None:
    row = views.QueueRow.model_validate(
        queue_row(
            status="declined",
            primary_next_action=None,
            waits_on=None,
            group="finished",
            effective_date=None,
        )
    )
    assert row.primary_next_action is None


@pytest.mark.parametrize(
    "bad",
    [
        {"status": "closed"},
        {"primary_next_action": "email_the_agent"},
        {"waits_on": "applicant"},
        {"group": "urgent"},
        {"confidence": 0.9},
    ],
)
def test_queue_row_refuses_values_outside_the_vocabularies(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        views.QueueRow.model_validate(queue_row(**bad))


def test_queue_groups_are_the_section_11_order() -> None:
    assert schema("QueueRow")["properties"]["group"]["enum"] == QUEUE_GROUPS


# ---- the run (A.5, section 11) ---------------------------------------------------------------

RUN_FIELDS = {"run_id", "mode", "seed", "sim_now", "first_pass_complete", "summary"}
SUMMARY_COUNTS = {
    "quotes_sent",
    "follow_ups_sent",
    "declines_approved",
    "waiting_on_underwriter",
    "waiting_on_data",
    "delivery_unknown",
}


def test_run_view_carries_a5_fields_and_section_11_counts() -> None:
    assert set(views.RunView.model_fields) == RUN_FIELDS
    assert set(views.RunSummary.model_fields) == SUMMARY_COUNTS


# ---- the lead detail (A.5, A.11, section 11) --------------------------------------------------

LEAD_DETAIL_FIELDS = {
    "lead_id",
    "mode",
    "status",
    "revision",
    "facts",
    "plan",
    "plan_hash",
    "playbook",
    "notes",
    "blockers",
    "drafts",
    "open_choices",
    "next_action",
    "links",
}
FACT_FIELDS = {
    "key",
    "value",
    "source",
    "status",
    "confirmed",
    "evidence",
    "observation_id",
    "is_stub",
}
BLOCKER_FIELDS = {
    "item_id",
    "kind",
    "item_kind",
    "owner",
    "detail",
    "observation",
    "review_cause",
    "held_draft_payload_hash",
}
DRAFT_FIELDS = {
    "intent_id",
    "payload_hash",
    "kind",
    "recipient",
    "subject",
    "body",
    "state",
    "round",
}
OPEN_CHOICE_FIELDS = {"choice_id", "options", "prompt", "show", "shown_values"}
PLAYBOOK_FIELDS = {
    "graph",
    "applies",
    "result",
    "waits_on",
    "effects",
    "declines_on_every_branch",
    "exception",
}


def fact(**changes: Any) -> dict[str, Any]:
    return {
        "key": "roof_year",
        "value": 1998,
        "source": "reply",
        "status": "pending_review",
        "confirmed": False,
        "evidence": {"quote": "built in 1998"},
        "observation_id": 4,
        "is_stub": False,
    } | changes


def blocker(**changes: Any) -> dict[str, Any]:
    """A review raised by a late reply; `review_cause` follows `detail.cause` unless given."""
    detail = {
        "item_kind": "review",
        "cause": "late_reply",
        "cause_persists": False,
        "resume_trigger": "underwriter approves",
        "text": "A reply arrived after the round closed.",
    }
    base: dict[str, Any] = {
        "item_id": 7,
        "kind": "underwriter_review",
        "item_kind": "review",
        "owner": "underwriter",
        "observation": None,
        "held_draft_payload_hash": None,
    }
    detail_changes = changes.pop("detail", {})
    merged_detail = detail | detail_changes
    view = base | changes | {"detail": merged_detail}
    if "review_cause" not in view:
        view["review_cause"] = merged_detail["cause"] if view["item_kind"] == "review" else None
    return view


def draft(**changes: Any) -> dict[str, Any]:
    return {
        "intent_id": "intent-1",
        "payload_hash": "ab" * 32,
        "kind": "routine_request",
        "recipient": "agent@example.test",
        "subject": "Information needed",
        "body": "Please send the roof year.",
        "state": "draft",
        "round": 1,
    } | changes


def choice(**changes: Any) -> dict[str, Any]:
    return {
        "choice_id": "I12.mitigation",
        "options": ["accept_mitigation", "decline"],
        "prompt": "Does the mitigation plan hold?",
        "show": ["p_f", "siding_material"],
        "shown_values": {"p_f": 0.79, "siding_material": "wood shake"},
    } | changes


def test_lead_detail_carries_the_a5_and_section_11_parts() -> None:
    assert set(views.LeadDetail.model_fields) == LEAD_DETAIL_FIELDS
    assert set(views.FactView.model_fields) == FACT_FIELDS
    assert set(views.BlockerView.model_fields) == BLOCKER_FIELDS
    assert set(views.DraftView.model_fields) == DRAFT_FIELDS
    assert set(views.OpenChoiceView.model_fields) == OPEN_CHOICE_FIELDS
    assert set(views.PlaybookPage.model_fields) == PLAYBOOK_FIELDS


def test_lead_detail_reuses_the_rules_and_runtime_models() -> None:
    from uwh.rules.models import ActionPlan, OpenChoice, PlannedEffect, RuleTrace
    from uwh.runtime.event_types import BlockerDetail

    assert views.LeadDetail.model_fields["plan"].annotation == ActionPlan | None
    assert views.BlockerView.model_fields["detail"].annotation is BlockerDetail
    assert issubclass(views.OpenChoiceView, OpenChoice)
    assert views.PlaybookPage.model_fields["effects"].annotation == list[PlannedEffect]
    assert views.PlaybookPage.model_fields["declines_on_every_branch"].annotation == (
        RuleTrace | None
    )


def test_p_f_is_validated_like_any_other_fact_and_is_not_a_confidence() -> None:
    p_f = fact(
        key="p_f",
        value=0.79,
        source="fetched",
        status="accepted",
        evidence={"provider": "fire_simulation"},
    )
    view = views.FactView.model_validate(p_f)
    assert (view.key, view.value) == ("p_f", 0.79)
    other = views.FactView.model_validate(fact(key="year_built", value=1950))
    assert set(view.model_dump()) == set(other.model_dump())
    # The no-confidence walk of the schema flags a property by its name; a fact's `p_f` key is a value.
    assert [n for n in views.FactView.model_fields if "confidence" in n.lower()] == []
    with pytest.raises(ValidationError):
        views.FactView.model_validate(p_f | {"confidence": 0.79})


def test_a_fact_carries_its_observation_id_and_whether_its_value_is_a_stub() -> None:
    stub = views.FactView.model_validate(
        fact(source="fetched", status="accepted", is_stub=True, observation_id=9)
    )
    assert (stub.observation_id, stub.is_stub) == (9, True)
    for missing in ("observation_id", "is_stub"):
        with pytest.raises(ValidationError, match=missing):
            views.FactView.model_validate({k: v for k, v in fact().items() if k != missing})


def test_a_blocker_carries_item_id_kind_item_kind_and_its_cause() -> None:
    view = views.BlockerView.model_validate(blocker())
    assert (view.item_id, view.kind, view.item_kind) == (7, "underwriter_review", "review")
    assert view.detail.cause == "late_reply"
    assert view.detail.cause_persists is False
    assert view.review_cause == "late_reply"


def test_a_review_whose_cause_persists_differs_from_one_an_event_raised() -> None:
    event = views.ReviewItem.model_validate(review_item("review_raised_by_event"))
    persists = views.ReviewItem.model_validate(review_item("review_cause_persists"))
    assert (event.review_cause, event.detail.cause_persists) == ("late_reply", False)
    assert (persists.review_cause, persists.detail.cause_persists) == ("round_limit", True)
    assert (event.item, persists.item) == ("review_raised_by_event", "review_cause_persists")
    # The flag follows the registered cause, not the item row alone.
    with pytest.raises(ValidationError, match="cause_persists"):
        views.ReviewItem.model_validate(
            review_item(
                "review_cause_persists", detail=blocker(detail={"cause": "round_limit"})["detail"]
            )
        )
    with pytest.raises(ValidationError, match="cause_persists"):
        views.ReviewItem.model_validate(
            review_item(
                "review_raised_by_event",
                detail=blocker(detail={"cause": "late_reply", "cause_persists": True})["detail"],
            )
        )


def test_a_draft_review_names_its_draft() -> None:
    view = views.BlockerView.model_validate(
        blocker(item_kind="draft", detail={"item_kind": "draft", "intent_id": "intent-1"})
    )
    assert view.detail.intent_id == "intent-1"
    with pytest.raises(ValidationError, match="intent_id"):
        views.BlockerView.model_validate(
            blocker(item_kind="draft", detail={"item_kind": "draft", "intent_id": None})
        )


@pytest.mark.parametrize(
    "bad",
    [
        # item kind and detail disagree
        blocker(item_kind="draft", detail={"item_kind": "review"}),
        # a review raised by an event has its cause
        blocker(detail={"cause": None}, review_cause=None),
        # the cause is one of the registered review causes
        blocker(detail={"cause": "a late reply"}),
        # the cause's flag is the registered one
        blocker(detail={"cause": "late_reply", "cause_persists": True}),
        blocker(detail={"cause": "round_limit", "cause_persists": False}),
        # the review cause field is the detail's cause
        blocker(review_cause="round_limit"),
        blocker(review_cause=None),
        # only a review has a review cause
        blocker(
            kind="delivery_unknown",
            item_kind="delivery_unknown",
            detail={"item_kind": "delivery_unknown", "cause": None},
            review_cause="late_reply",
        ),
        # only a review can hold a persistent cause
        blocker(
            item_kind="observation",
            detail={
                "item_kind": "observation",
                "cause": None,
                "cause_persists": True,
                "observation_id": 4,
            },
            observation=fact(),
        ),
        # delivery_unknown is its own blocker kind
        blocker(
            kind="underwriter_review",
            item_kind="delivery_unknown",
            detail={"item_kind": "delivery_unknown"},
        ),
        # a question card is not an approvals item
        blocker(kind="underwriter_question"),
        # an unknown blocker kind
        blocker(kind="waiting"),
    ],
)
def test_blocker_refuses_an_inconsistent_kind_and_item_kind(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        views.BlockerView.model_validate(bad)


def test_a_delivery_unknown_blocker_is_its_own_kind_and_item_kind() -> None:
    view = views.BlockerView.model_validate(
        blocker(
            kind="delivery_unknown",
            item_kind="delivery_unknown",
            detail={"item_kind": "delivery_unknown", "cause": None, "intent_id": "intent-1"},
        )
    )
    assert view.kind == "delivery_unknown"


def observation_blocker(**changes: Any) -> dict[str, Any]:
    detail = {"item_kind": "observation", "cause": None, "observation_id": 4}
    return blocker(item_kind="observation", observation=fact(), detail=detail) | changes


def test_a_pending_observation_blocker_carries_the_value_to_approve() -> None:
    view = views.BlockerView.model_validate(observation_blocker())
    assert view.observation is not None
    assert (view.observation.key, view.observation.value) == ("roof_year", 1998)
    assert view.observation.observation_id == view.detail.observation_id == 4
    assert view.review_cause is None


@pytest.mark.parametrize(
    "bad",
    [
        # an observation item shows its observation
        observation_blocker(observation=None),
        # the observation is pending review
        observation_blocker(observation=fact(status="accepted")),
        observation_blocker(observation=fact(status="rejected")),
        # it is the observation the detail names
        observation_blocker(observation=fact(observation_id=5)),
        observation_blocker(detail={"item_kind": "observation", "observation_id": None}),
        # no other item carries an observation
        blocker(observation=fact()),
    ],
)
def test_an_observation_blocker_refuses_a_missing_or_mismatched_observation(
    bad: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        views.BlockerView.model_validate(bad)


def held_blocker(cause: str, **changes: Any) -> dict[str, Any]:
    return (
        blocker(
            detail={"cause": cause, "intent_id": "intent-1"},
            held_draft_payload_hash="ab" * 32,
        )
        | changes
    )


@pytest.mark.parametrize("cause", ["draft_held_by_stop", "draft_held_class_off"])
def test_a_held_draft_review_names_its_draft_and_the_hash_an_approve_carries(cause: str) -> None:
    view = views.BlockerView.model_validate(held_blocker(cause))
    assert (view.detail.intent_id, view.held_draft_payload_hash) == ("intent-1", "ab" * 32)
    for bad in (
        held_blocker(cause, held_draft_payload_hash=None),
        held_blocker(cause, detail={"cause": cause, "intent_id": None}),
    ):
        with pytest.raises(ValidationError):
            views.BlockerView.model_validate(bad)


def test_only_a_held_draft_review_carries_a_held_draft_hash() -> None:
    with pytest.raises(ValidationError, match="held_draft_payload_hash"):
        views.BlockerView.model_validate(blocker(held_draft_payload_hash="ab" * 32))


def test_review_cause_is_an_enum_of_the_registered_causes_in_the_schema() -> None:
    node = schema("BlockerView")["properties"]["review_cause"]
    enum = [m["enum"] for m in node["anyOf"] if "enum" in m]
    assert enum == [[name for name, _ in vertical.REVIEW_CAUSES]]


@pytest.mark.parametrize(("cause", "persists"), vertical.REVIEW_CAUSES)
def test_every_registered_review_cause_validates_with_its_flag_only(
    cause: str, persists: bool
) -> None:
    held = cause.startswith("draft_held")
    extra: dict[str, Any] = (
        {"held_draft_payload_hash": "ab" * 32, "detail": {"intent_id": "intent-1"}} if held else {}
    )

    def view(flag: bool) -> dict[str, Any]:
        detail = {"cause": cause, "cause_persists": flag} | extra.get("detail", {})
        return blocker(detail=detail) | {k: v for k, v in extra.items() if k != "detail"}

    assert views.BlockerView.model_validate(view(persists)).review_cause == cause
    with pytest.raises(ValidationError, match="cause_persists"):
        views.BlockerView.model_validate(view(not persists))


def test_a_draft_carries_intent_id_and_payload_hash() -> None:
    view = views.DraftView.model_validate(draft())
    assert (view.intent_id, view.payload_hash) == ("intent-1", "ab" * 32)
    with pytest.raises(ValidationError):
        views.DraftView.model_validate(draft(kind="newsletter"))
    with pytest.raises(ValidationError):
        views.DraftView.model_validate(draft(state="queued"))


def test_an_open_choice_carries_its_choice_id_option_ids_and_shown_values() -> None:
    view = views.OpenChoiceView.model_validate(choice())
    assert view.choice_id == "I12.mitigation"
    assert view.options == ["accept_mitigation", "decline"]
    assert view.shown_values["p_f"] == 0.79


PLANNED_NO_ACTION = {
    "effect": {"type": "no_action", "rule": "R-01-1"},
    "trace": {"board_path": ["01:START", "01:OK"]},
    "committed": True,
}
PLANNED_REQUIREMENT = {
    "effect": {"type": "requirement", "rule": "R-01-2", "text": "Provide the roof report."},
    "trace": {"board_path": ["01:START", "01:ROOF"]},
    "committed": True,
}
PLANNED_DECLINE = {
    "effect": {"type": "decline", "rule": "R-07-1"},
    "trace": {"board_path": ["07:LIVING", "07:D1"]},
    "committed": True,
}
DECLINE_ON_EVERY_BRANCH = {
    "board_path": [],
    "alternatives": [
        {
            "assumed": [{"field": "p_f", "when": {"gt": 0.5}}],
            "board_path": ["04:START", "04:D1"],
            "rule": "R-04-1",
        }
    ],
}


def page(**changes: Any) -> dict[str, Any]:
    return {
        "graph": "pools",
        "applies": "yes",
        "result": "decided",
        "waits_on": [],
        "effects": [],
        "declines_on_every_branch": None,
        "exception": False,
    } | changes


def test_a_playbook_result_is_a_node_result_or_not_evaluated() -> None:
    # Section 9.6's three node results, then the page that was not evaluated.
    node = schema("PlaybookPage")["properties"]["result"]
    assert [m["enum"] for m in node["anyOf"] if "enum" in m] == [
        ["decided", "undecided", "declines_on_every_branch", "not_evaluated"]
    ]
    assert schema("PlaybookPage")["properties"]["applies"]["enum"] == ["yes", "no", "unknown"]


@pytest.mark.parametrize(
    ("changes", "exception"),
    [
        # a page that does not apply is not an exception and has no result
        ({"applies": "no", "result": None}, False),
        # a decided page whose effects are all no_action is not an exception
        ({}, False),
        ({"effects": [PLANNED_NO_ACTION]}, False),
        # any other effect is
        ({"effects": [PLANNED_NO_ACTION, PLANNED_REQUIREMENT]}, True),
        ({"effects": [PLANNED_DECLINE]}, True),
        # an undecided page is, whether the controlling fact is unknown or the page applies
        ({"applies": "unknown", "result": "undecided", "waits_on": ["pool_type"]}, True),
        ({"result": "undecided", "waits_on": ["I12.mitigation"]}, True),
        # a decline on every branch is
        (
            {
                "result": "declines_on_every_branch",
                "declines_on_every_branch": DECLINE_ON_EVERY_BRANCH,
            },
            True,
        ),
        # a page that applies and was not evaluated is
        ({"result": "not_evaluated"}, True),
    ],
)
def test_a_playbook_page_flags_an_exception_exactly_by_the_section_11_rule(
    changes: dict[str, Any], exception: bool
) -> None:
    parsed = views.PlaybookPage.model_validate(page(exception=exception, **changes))
    assert parsed.exception is exception
    with pytest.raises(ValidationError, match="exception"):
        views.PlaybookPage.model_validate(page(exception=not exception, **changes))


@pytest.mark.parametrize(
    ("bad", "match"),
    [
        ({"applies": "no", "result": "decided"}, "applies"),
        ({"applies": "no", "result": None, "effects": [PLANNED_NO_ACTION]}, "applies"),
        ({"applies": "unknown", "result": "decided"}, "applies"),
        ({"applies": "unknown", "result": None}, "applies"),
        # an unknown page is undecided and contributes nothing (9.6): no effect, no decline
        (
            {
                "applies": "unknown",
                "result": "undecided",
                "waits_on": ["pool_type"],
                "effects": [PLANNED_REQUIREMENT],
                "exception": True,
            },
            "applies",
        ),
        (
            {
                "applies": "unknown",
                "result": "undecided",
                "waits_on": ["pool_type"],
                "declines_on_every_branch": DECLINE_ON_EVERY_BRANCH,
                "exception": True,
            },
            "declines_on_every_branch",
        ),
        (
            {
                "applies": "unknown",
                "result": "declines_on_every_branch",
                "declines_on_every_branch": DECLINE_ON_EVERY_BRANCH,
                "exception": True,
            },
            "applies",
        ),
        ({"applies": "yes", "result": None}, "result"),
        ({"applies": "maybe"}, "applies"),
        ({"result": "pending"}, "result"),
        ({"waits_on": ["pool_type"]}, "waits_on"),
        ({"result": "undecided", "waits_on": [], "exception": True}, "waits_on"),
        ({"declines_on_every_branch": DECLINE_ON_EVERY_BRANCH}, "declines_on_every_branch"),
        (
            {
                "result": "declines_on_every_branch",
                "declines_on_every_branch": None,
                "exception": True,
            },
            "declines_on_every_branch",
        ),
        ({"trace": {"board_path": ["a"]}}, "trace"),
        ({"page": "pools"}, "page"),
    ],
)
def test_a_playbook_page_refuses_a_result_that_does_not_follow_whether_it_applies(
    bad: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        views.PlaybookPage.model_validate(page(**bad))


def test_a_lead_detail_validates_with_a_plan_and_a_trace() -> None:
    plan = {
        "effects": [
            {
                "effect": {"type": "decline", "rule": "R-07-1"},
                "trace": {"board_path": ["07:LIVING", "07:D1"]},
                "committed": True,
            }
        ],
        "proposed_decline": True,
        "open_choices": [{"choice_id": "c", "options": ["a"], "prompt": "p", "show": []}],
    }
    detail = views.LeadDetail.model_validate(
        {
            "lead_id": LEAD,
            "mode": "replay",
            "status": "in_progress",
            "revision": 2,
            "facts": [],
            "plan": plan,
            "plan_hash": "cd" * 32,
            "playbook": [
                page(graph="post_and_pier", effects=[PLANNED_DECLINE], exception=True),
                page(
                    graph="roof",
                    applies="unknown",
                    result="undecided",
                    waits_on=["roof_year"],
                    exception=True,
                ),
            ],
            "notes": [{"kind": "not_evaluated", "ref": "I09", "text": "Not evaluated."}],
            "blockers": [blocker()],
            "drafts": [draft()],
            "open_choices": [choice()],
            "next_action": "Decide the open choice.",
            "links": [{"kind": "map", "label": "Property", "url": "https://maps.example/x"}],
        }
    )
    assert detail.lead_id == LEAD
    assert detail.plan is not None and detail.plan.proposed_decline


# ---- the items view (section 11, A.11) --------------------------------------------------------

# The A.11 item table, row by row.
A11_ITEMS = [
    "draft_request",
    "draft_quote_packet",
    "draft_decline_notice",
    "pending_observation",
    "delivery_unknown",
    "no_contact_route",
    "review_raised_by_event",
    "review_cause_persists",
]


def review_item(item: str, **changes: Any) -> dict[str, Any]:
    drafts = ("draft_request", "draft_quote_packet", "draft_decline_notice")
    base = blocker(
        item_kind="draft",
        detail={"item_kind": "draft", "intent_id": "intent-1", "cause": None},
    )
    kinds = {
        "draft_request": "routine_request",
        "draft_quote_packet": "quote_packet",
        "draft_decline_notice": "decline_notice",
    }
    extra: dict[str, Any] = {"draft": draft(kind=kinds.get(item, "routine_request"))}
    if item in ("pending_observation",):
        base = observation_blocker()
        extra = {}
    elif item == "delivery_unknown":
        base = blocker(
            kind="delivery_unknown",
            item_kind="delivery_unknown",
            detail={"item_kind": "delivery_unknown", "intent_id": "intent-1", "cause": None},
        )
        extra = {}
    elif item == "no_contact_route":
        base = blocker(
            item_kind="no_contact_route", detail={"item_kind": "no_contact_route", "cause": None}
        )
        extra = {}
    elif item == "review_raised_by_event":
        extra = {}
        base = blocker()
    elif item == "review_cause_persists":
        extra = {}
        base = blocker(detail={"cause": "round_limit", "cause_persists": True})
    assert (item in drafts) == ("draft" in extra)
    return {"type": "review", "lead_id": LEAD, "item": item, "draft": None} | base | extra | changes


def held_review(**changes: Any) -> dict[str, Any]:
    return (
        {"type": "review", "lead_id": LEAD, "item": "review_raised_by_event", "draft": draft()}
        | held_blocker("draft_held_by_stop")
        | changes
    )


def question_item(**changes: Any) -> dict[str, Any]:
    base = blocker(
        kind="underwriter_question",
        item_kind=None,
        owner="underwriter",
        detail={"item_kind": None, "cause": None, "choice_ids": ["I12.mitigation"]},
    )
    return {"type": "question", "lead_id": LEAD, "choices": [choice()]} | base | changes


def test_a_review_item_is_one_of_the_a11_items_with_both_review_rows() -> None:
    assert schema("ReviewItem")["properties"]["item"]["enum"] == A11_ITEMS


@pytest.mark.parametrize("item", A11_ITEMS)
def test_every_a11_item_is_a_valid_review_item(item: str) -> None:
    parsed = views.ReviewItem.model_validate(review_item(item))
    assert parsed.item == item
    assert parsed.lead_id == LEAD


def test_a_draft_item_carries_the_payload_hash_an_approve_must_echo() -> None:
    parsed = views.ReviewItem.model_validate(review_item("draft_request"))
    assert parsed.draft is not None
    assert parsed.draft.payload_hash == "ab" * 32
    without_draft = review_item("draft_request")
    del without_draft["draft"]
    with pytest.raises(ValidationError, match="draft"):
        views.ReviewItem.model_validate(without_draft)


@pytest.mark.parametrize(
    "bad",
    [
        # the draft shown is not the draft the blocker reviews
        review_item("draft_request", draft=draft(intent_id="intent-2")),
        # a pending observation shows the pending observation
        review_item("pending_observation", observation=None),
        # a review whose cause persists says so in its detail
        review_item("review_cause_persists", detail=blocker()["detail"]),
        # a review raised by an event does not
        review_item(
            "review_raised_by_event", detail=blocker(detail={"cause_persists": True})["detail"]
        ),
        # a draft row holds a draft of its own message kind
        review_item("draft_request", draft=draft(kind="quote_packet")),
        review_item("draft_request", draft=draft(kind="decline_notice")),
        review_item("draft_quote_packet", draft=draft(kind="routine_request")),
        review_item("draft_quote_packet", draft=draft(kind="decline_notice")),
        review_item("draft_decline_notice", draft=draft(kind="sensitive_request")),
        review_item("draft_decline_notice", draft=draft(kind="quote_packet")),
        # a held draft's review that carries its draft carries the one the blocker holds
        held_review(draft=draft(payload_hash="cd" * 32)),
        held_review(draft=draft(intent_id="intent-2")),
        # an item whose approvals kind is wrong for its row
        review_item("no_contact_route", item_kind="review"),
        # no notify item exists
        review_item("review_raised_by_event") | {"item": "notify"},
    ],
)
def test_review_item_refuses_a_row_its_blocker_does_not_fit(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        views.ReviewItem.model_validate(bad)


@pytest.mark.parametrize("kind", ["routine_request", "sensitive_request"])
def test_a_request_draft_row_holds_either_request_kind(kind: str) -> None:
    parsed = views.ReviewItem.model_validate(review_item("draft_request", draft=draft(kind=kind)))
    assert parsed.draft is not None and parsed.draft.kind == kind


def test_a_held_draft_review_carries_its_draft_and_the_hash_an_approve_echoes() -> None:
    parsed = views.ReviewItem.model_validate(held_review())
    assert parsed.draft is not None
    assert parsed.draft.payload_hash == parsed.held_draft_payload_hash
    assert views.ReviewItem.model_validate(held_review(draft=None)).draft is None


def test_a_question_item_carries_the_leads_open_choices_as_one_card() -> None:
    parsed = views.QuestionItem.model_validate(
        question_item(
            choices=[choice(), choice(choice_id="I06.occupancy")],
            detail=question_item()["detail"] | {"choice_ids": ["I12.mitigation", "I06.occupancy"]},
        )
    )
    assert [c.choice_id for c in parsed.choices] == ["I12.mitigation", "I06.occupancy"]
    with pytest.raises(ValidationError, match="choice"):
        views.QuestionItem.model_validate(question_item(choices=[]))


def test_the_items_view_holds_review_and_question_items_only() -> None:
    adapter = TypeAdapter(list[views.Item])
    parsed = adapter.validate_python(
        [review_item("draft_request"), review_item("delivery_unknown"), question_item()]
    )
    assert [p.type for p in parsed] == ["review", "review", "question"]
    with pytest.raises(ValidationError):
        adapter.validate_python([{"type": "notify", "lead_id": LEAD}])
    mapping = document()["paths"]["/api/items"]["get"]["responses"]["200"]["content"]
    items = deref(document(), mapping["application/json"]["schema"]["items"])
    assert set(items["discriminator"]["mapping"]) == {"review", "question"}


# ---- commands (A.11) --------------------------------------------------------------------------

# A.11's table: type -> payload fields, written out.
A11_PAYLOADS = {
    "approve": {"item_id", "artifact_hash", "reason"},
    "reject": {"item_id", "reason"},
    "edit_draft": {"intent_id", "subject", "body", "reason"},
    "record_ruling": {"lead_id", "choice_id", "option", "reason"},
    "resolve_fact": {"lead_id", "key", "value", "reason"},
    "decline_lead": {"lead_id", "reason"},
    "deliver_reply": {"lead_id", "intent_id", "body"},
    "change_setting": {"key", "value"},
    "emergency_stop": {"engaged"},
    "start_run": {"seed"},
    "propose_rule_change": {"row_id", "param", "value", "reason"},
    "apply_rule_change": {"proposal_id", "diff_hash"},
    "propose_command": {"type", "payload", "rationale"},
}
# Every A.11 payload field is required except approve's artifact_hash.
A11_OPTIONAL = {("approve", "artifact_hash")}


def command_variants() -> dict[str, dict[str, Any]]:
    """The command types the HTTP request schema accepts -> their payload schema."""
    doc = document()
    body = doc["paths"]["/api/commands"]["post"]["requestBody"]["content"]["application/json"]
    union = deref(doc, body["schema"])
    out = {}
    for command_type, ref in union["discriminator"]["mapping"].items():
        variant = deref(doc, {"$ref": ref})
        out[command_type] = deref(doc, variant["properties"]["payload"])
    return out


def test_the_command_schema_has_one_payload_model_per_a11_row_with_a11_fields() -> None:
    variants = command_variants()
    assert set(variants) == set(A11_PAYLOADS)
    for command_type, payload in variants.items():
        assert set(payload["properties"]) == A11_PAYLOADS[command_type], command_type
        optional = {f for (t, f) in A11_OPTIONAL if t == command_type}
        required = A11_PAYLOADS[command_type] - optional
        assert set(payload["required"]) == required, command_type
        assert payload["additionalProperties"] is False


def test_the_http_command_schema_omits_the_workflow_only_classes() -> None:
    workflow_only = {c.name for c in vertical.COMMAND_CLASSES if c.actors == ("workflow",)}
    assert workflow_only == {
        "fetch_data",
        "send_routine_request",
        "send_sensitive_request",
        "send_quote_packet",
        "send_decline_notice",
    }
    accepted = set(command_variants())
    assert not accepted & workflow_only
    assert accepted == {c.name for c in vertical.COMMAND_CLASSES} - workflow_only


def test_a_proposed_command_names_one_of_the_other_twelve_http_types() -> None:
    proposed = command_variants()["propose_command"]["properties"]["type"]
    workflow_only = {c.name for c in vertical.COMMAND_CLASSES if c.actors == ("workflow",)}
    assert not set(proposed["enum"]) & workflow_only
    assert "propose_command" not in proposed["enum"]
    assert set(proposed["enum"]) == set(A11_PAYLOADS) - {"propose_command"}
    assert len(proposed["enum"]) == 12


def test_a_proposed_command_payload_is_a_union_of_the_twelve_payload_models() -> None:
    doc = document()
    inner = command_variants()["propose_command"]["properties"]["payload"]
    refs = {m["$ref"].rsplit("/", 1)[1] for m in inner["anyOf"]}
    assert refs == {
        "ApprovePayload",
        "RejectPayload",
        "EditDraftPayload",
        "RecordRulingPayload",
        "ResolveFactPayload",
        "DeclineLeadPayload",
        "ReplyRequest",
        "ChangeSettingPayload",
        "EmergencyStopPayload",
        "StartRunPayload",
        "ProposeRuleChangePayload",
        "ApplyRuleChangePayload",
    }
    assert refs <= set(doc["components"]["schemas"])


command = TypeAdapter(views.Command)


def test_approve_carries_the_artifact_hash_it_echoes() -> None:
    parsed = command.validate_python(
        {"type": "approve", "payload": {"item_id": 7, "artifact_hash": "ab" * 32, "reason": ""}}
    )
    assert parsed.payload.artifact_hash == "ab" * 32  # type: ignore[union-attr]
    omitted = command.validate_python({"type": "approve", "payload": {"item_id": 7, "reason": ""}})
    assert omitted.payload.artifact_hash is None  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "reject", "payload": {"item_id": 7, "reason": ""}},
        {"type": "reject", "payload": {"item_id": 7}},
        {
            "type": "record_ruling",
            "payload": {"lead_id": LEAD, "choice_id": "c", "option": "a", "reason": ""},
        },
        {"type": "decline_lead", "payload": {"lead_id": LEAD, "reason": ""}},
        {"type": "fetch_data", "payload": {}},
        {"type": "send_routine_request", "payload": {}},
        {"type": "approve", "payload": {"item_id": 7, "reason": "", "confidence": 0.9}},
        {
            "type": "deliver_reply",
            "payload": {"lead_id": LEAD, "intent_id": "i", "body": "x" * 8001},
        },
        {"type": "emergency_stop", "payload": {"engaged": "maybe"}},
    ],
)
def test_a_malformed_command_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        command.validate_python(bad)


def proposal(command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "propose_command",
        "payload": {"type": command_type, "payload": payload, "rationale": "the roof is slate"},
    }


RESOLVE_FACT = {"lead_id": LEAD, "key": "roof_type", "value": "slate", "reason": "per the reply"}


def test_a_proposed_command_holds_a_valid_inner_command() -> None:
    parsed = command.validate_python(proposal("resolve_fact", RESOLVE_FACT))
    inner = parsed.payload
    assert isinstance(inner, views.ProposeCommandPayload)
    assert inner.type == "resolve_fact"
    assert isinstance(inner.payload, views.ResolveFactPayload)
    assert inner.payload.value == "slate"
    assert inner.rationale == "the roof is slate"


def test_a_proposed_command_is_checked_by_its_type_not_by_the_shape_alone() -> None:
    # {item_id, reason} fits approve and reject; the type picks reject, whose reason is required.
    rejected = {"item_id": 7, "reason": "wrong recipient"}
    parsed = command.validate_python(proposal("reject", rejected))
    assert isinstance(parsed.payload.payload, views.RejectPayload)  # type: ignore[union-attr]
    approved = command.validate_python(proposal("approve", rejected))
    assert isinstance(approved.payload.payload, views.ApprovePayload)  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        command.validate_python(proposal("reject", {"item_id": 7, "reason": ""}))


def test_a_proposed_command_built_from_models_cannot_pair_a_type_with_another_payload() -> None:
    with pytest.raises(ValidationError, match="reject"):
        views.ProposeCommandPayload(
            type="reject",
            payload=views.ApprovePayload(item_id=7, reason="x"),
            rationale="r",
        )


def test_a_proposed_command_survives_a_json_round_trip() -> None:
    parsed = command.validate_python(proposal("resolve_fact", RESOLVE_FACT))
    again = command.validate_json(command.dump_json(parsed))
    assert again == parsed


@pytest.mark.parametrize(
    "bad",
    [
        # a proposal does not nest a proposal
        proposal("propose_command", proposal("resolve_fact", RESOLVE_FACT)["payload"]),
        # the inner payload must be valid for the inner type
        proposal("approve", {"nonsense": True}),
        proposal("resolve_fact", {"lead_id": LEAD}),
        proposal("approve", RESOLVE_FACT),
        # a workflow-only class is not a command over HTTP, so it is not proposed either
        proposal("fetch_data", {}),
        proposal("send_quote_packet", {}),
        # an unknown inner type
        proposal("notify", {}),
    ],
)
def test_a_proposed_command_that_is_not_one_of_the_other_twelve_is_refused(
    bad: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        command.validate_python(bad)


def test_the_command_response_is_accepted_event_id_and_reason() -> None:
    assert set(views.CommandResponse.model_fields) == {"accepted", "event_id", "reason"}
    refused = views.CommandResponse(accepted=False, event_id=None, reason="the stop is engaged")
    assert refused.reason == "the stop is engaged"


def test_a_reply_request_and_a_deliver_reply_payload_are_one_model() -> None:
    assert set(views.ReplyRequest.model_fields) == {"lead_id", "intent_id", "body"}
    assert views.DeliverReplyPayload is views.ReplyRequest


def test_a_reply_response_carries_lead_id_and_the_command_outcome() -> None:
    assert set(views.ReplyResponse.model_fields) == {"lead_id", "accepted", "event_id", "reason"}
    assert set(views.FixtureRepliesResponse.model_fields) == {"replies"}


# ---- read views, events, chat ------------------------------------------------------------------


def test_settings_view_marks_locked_classes_and_names_the_active_ruleset() -> None:
    assert set(views.SettingsView.model_fields) == {"autonomy", "emergency_stop", "ruleset_active"}
    assert set(views.AutonomySetting.model_fields) == {
        "command_class",
        "level",
        "default_level",
        "locked",
    }


def test_skill_view_carries_status_last_result_threshold_and_fallback() -> None:
    assert set(views.SkillView.model_fields) == {
        "name",
        "status",
        "last_result",
        "threshold",
        "fallback",
        "rules_changed_since_eval",
    }
    assert set(views.SkillResult.model_fields) == {"cases_passed", "cases_total", "passed"}
    assert schema("SkillView")["properties"]["status"]["enum"] == [
        "untested",
        "passing",
        "failing",
        "unavailable",
    ]


def test_proposal_view_follows_the_a1_proposals_columns() -> None:
    assert set(views.ProposalView.model_fields) == {
        "proposal_id",
        "kind",
        "payload",
        "diff_hash",
        "state",
        "actor",
        "event_id",
    }


def test_chat_answers_cite_event_ids_and_a_directive_becomes_a_proposal() -> None:
    assert set(views.ChatRequest.model_fields) == {"message"}
    assert set(views.ChatResponse.model_fields) == {"answer", "cited_event_ids", "proposals"}


def event_row(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": 12,
        "run_id": "run-1",
        "mode": "replay",
        "lead_id": LEAD,
        "type": event_type,
        "payload": payload,
        "actor": "workflow",
        "ruleset_hash": "ef" * 32,
        "prompt_versions": None,
        "model_id": None,
        "request_id": None,
        "real_ts": "2026-10-05T10:00:00+00:00",
        "sim_ts": "2026-06-29T08:05:00+00:00",
    }


def test_events_view_rows_are_the_a1_events_columns() -> None:
    assert set(views.EventRow.model_fields) == {
        "id",
        "run_id",
        "mode",
        "lead_id",
        "type",
        "payload",
        "actor",
        "ruleset_hash",
        "prompt_versions",
        "model_id",
        "request_id",
        "real_ts",
        "sim_ts",
    }
    assert set(views.LeadEvents.model_fields) == {"lead_id", "events"}
    assert schema("EventType")["enum"] == [t.value for t in EventType]


def test_an_event_payload_must_follow_the_model_of_its_type() -> None:
    row = views.EventRow.model_validate(
        event_row("message_sent", {"intent_id": "i", "mailbox_id": 3})
    )
    assert row.payload == {"intent_id": "i", "mailbox_id": 3}
    with pytest.raises(ValidationError, match="message_sent"):
        views.EventRow.model_validate(event_row("message_sent", {"intent_id": "i"}))
    with pytest.raises(ValidationError):
        views.EventRow.model_validate(event_row("notify", {}))
    assert set(PAYLOAD_MODELS) == set(EventType)


# ---- vocabularies and confidence ----------------------------------------------------------------


AUTONOMY_CLASSES = [
    "fetch_data",
    "send_routine_request",
    "send_sensitive_request",
    "send_quote_packet",
    "send_decline_notice",
    "deliver_reply",
    "propose_command",
]


def autonomy_setting(**changes: Any) -> dict[str, Any]:
    return {
        "command_class": "send_quote_packet",
        "level": "review",
        "default_level": "review",
        "locked": True,
    } | changes


def test_autonomy_applies_only_to_the_classes_of_the_7_4_table_with_a_default_level() -> None:
    assert [c.name for c in vertical.COMMAND_CLASSES if c.default_level is not None] == (
        AUTONOMY_CLASSES
    )
    assert schema("AutonomySetting")["properties"]["command_class"]["enum"] == AUTONOMY_CLASSES
    for name in AUTONOMY_CLASSES:
        views.AutonomySetting.model_validate(autonomy_setting(command_class=name))
    for human_only in ("approve", "emergency_stop", "start_run", "change_setting"):
        with pytest.raises(ValidationError, match="command_class"):
            views.AutonomySetting.model_validate(autonomy_setting(command_class=human_only))


def test_an_actor_is_one_of_the_five_of_7_4() -> None:
    actors = ["workflow", "underwriter", "assistant", "mcp_client", "inbound"]
    assert schema("EventRow")["properties"]["actor"]["enum"] == actors
    assert schema("ProposalView")["properties"]["actor"]["enum"] == actors
    row = event_row("message_sent", {"intent_id": "i", "mailbox_id": 3})
    for actor in actors:
        assert views.EventRow.model_validate(row | {"actor": actor}).actor == actor
    with pytest.raises(ValidationError, match="actor"):
        views.EventRow.model_validate(row | {"actor": "robot"})
    proposal_row = {
        "proposal_id": 1,
        "kind": "command",
        "payload": {},
        "diff_hash": None,
        "state": "open",
        "actor": "assistant",
        "event_id": 5,
    }
    assert views.ProposalView.model_validate(proposal_row).actor == "assistant"
    with pytest.raises(ValidationError, match="actor"):
        views.ProposalView.model_validate(proposal_row | {"actor": "robot"})


def test_vocabulary_enums_in_the_schema_equal_the_verticals() -> None:
    assert schema("QueueRow")["properties"]["status"]["enum"] == list(vertical.STATUSES)
    assert schema("LeadDetail")["properties"]["status"]["enum"] == list(vertical.STATUSES)
    assert schema("BlockerView")["properties"]["kind"]["enum"] == list(
        vertical.BLOCKER_KINDS_BY_PRIORITY
    )
    assert schema("DraftView")["properties"]["kind"]["enum"] == list(vertical.MESSAGE_KINDS)
    assert schema("AutonomySetting")["properties"]["level"]["enum"] == list(
        vertical.AUTONOMY_LEVELS
    )
    assert schema("RunView")["properties"]["mode"]["enum"] == ["live", "replay", "record"]


def test_a_value_outside_a_vocabulary_is_refused() -> None:
    with pytest.raises(ValidationError, match="in_review"):
        views.DraftView.model_validate(draft(state="draft", kind="in_review"))


def test_no_schema_property_is_named_confidence_or_carries_one() -> None:
    names = []
    for node in all_schemas(document()):
        names += [name for name in node.get("properties", {})]
    assert names, "the walk found no properties"
    assert [n for n in names if "confidence" in n.lower()] == []


# The runtime's payloads hold these as plain strings; the API shows the registered names as an
# enum and refuses any other.
@pytest.mark.parametrize(
    ("model", "data", "field", "registered"),
    [
        (views.FactView, fact(), "source", vertical.OBSERVATION_SOURCES),
        (views.BlockerView, blocker(), "owner", vertical.BLOCKER_OWNERS),
        (views.BlockerView, blocker(), "item_kind", vertical.ITEM_KINDS),
    ],
)
def test_the_api_shows_the_registered_names_and_refuses_others(
    model: Any, data: dict[str, Any], field: str, registered: tuple[str, ...]
) -> None:
    node = schema(model.__name__)["properties"][field]
    enum = node["enum"] if "enum" in node else node["anyOf"][0]["enum"]
    assert enum == list(registered)
    with pytest.raises(ValidationError, match="is not one of"):
        model.model_validate({**data, field: "made_up"})
