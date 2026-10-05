# ABOUTME: Tests that the event-type enum holds the 28 names of A.2 and that each type has a payload model named after it.
# ABOUTME: The names and each payload's field set are written out here; every payload forbids unknown fields and round-trips through JSON.
import pytest
from pydantic import BaseModel, ValidationError

from uwh.runtime import event_types
from uwh.runtime.event_types import PAYLOAD_MODELS, EventType

# A.2, in order.
A2_NAMES = [
    "run_started",
    "replay_miss",
    "draft_edited",
    "proposal_created",
    "lead_received",
    "fact_observed",
    "fact_selected",
    "conflict_opened",
    "conflict_closed",
    "triage_completed",
    "provider_called",
    "plan_built",
    "blocker_opened",
    "blocker_closed",
    "intent_created",
    "message_sent",
    "delivery_unknown",
    "reply_received",
    "reply_read",
    "approval_recorded",
    "ruling_recorded",
    "command_refused",
    "setting_changed",
    "class_demoted",
    "rule_change_applied",
    "skill_fallback_used",
    "model_called",
    "fault_injected",
]

# The fields each payload holds; the event row's own columns are not repeated here.
EXPECTED_FIELDS: dict[str, set[str]] = {
    "run_started": {"seed", "lead_count"},
    "replay_miss": {"skill", "prompt_version", "input_hash"},
    "draft_edited": {"intent_id", "subject", "body", "payload_hash", "reason"},
    "proposal_created": {"proposal_id", "kind", "diff_hash"},
    "lead_received": {"source", "received_at"},
    "fact_observed": {"observation_id", "key", "value", "source", "evidence", "status"},
    "fact_selected": {"key", "observation_id", "value", "source", "confirmed"},
    "conflict_opened": {"validator", "fields", "values", "question"},
    "conflict_closed": {"validator", "fields", "values", "observation_id"},
    "triage_completed": {"fields"},
    "provider_called": {
        "key",
        "status",
        "value",
        "source",
        "fetched_at",
        "is_stub",
        "missing_inputs",
    },
    "plan_built": {"plan", "plan_hash"},
    "blocker_opened": {"blocker_id", "kind", "owner", "detail"},
    "blocker_closed": {"blocker_id", "kind"},
    "intent_created": {
        "intent_id",
        "round",
        "kind",
        "recipient",
        "subject",
        "body",
        "ask_ids",
        "payload_hash",
    },
    "message_sent": {"intent_id", "mailbox_id"},
    "delivery_unknown": {"intent_id"},
    "reply_received": {"intent_id", "body", "body_hash"},
    "reply_read": {"classification", "candidates", "dropped"},
    "approval_recorded": {
        "item_id",
        "item_kind",
        "intent_id",
        "lead_revision",
        "plan_hash",
        "ruleset_hash",
        "recipient",
        "payload_hash",
        "decision",
        "reason",
    },
    "ruling_recorded": {"choice_id", "option", "reason", "plan_hash", "suppressed_rule_ids"},
    "command_refused": {"command_type", "reason"},
    "setting_changed": {"key", "value"},
    "class_demoted": {"command_class", "reason"},
    "rule_change_applied": {"proposal_id", "diff_hash", "new_ruleset_hash"},
    "skill_fallback_used": {"skill", "status", "fallback"},
    "model_called": {
        "skill",
        "prompt_version",
        "input_hash",
        "tokens_in",
        "tokens_out",
        "stop_reason",
    },
    "fault_injected": {"fault"},
}

H = "a" * 64

# One valid payload per type, with values that make a lossy round trip visible.
SAMPLES: dict[str, dict[str, object]] = {
    "run_started": {"seed": 42, "lead_count": 10},
    "replay_miss": {"skill": "read_reply", "prompt_version": H, "input_hash": H},
    "draft_edited": {
        "intent_id": "i1",
        "subject": "Re: café",
        "body": "Line one\nLine two",
        "payload_hash": H,
        "reason": "tone",
    },
    "proposal_created": {"proposal_id": 3, "kind": "rule_change", "diff_hash": H},
    "lead_received": {"source": "broker_email", "received_at": "2026-06-29T08:00:00+00:00"},
    "fact_observed": {
        "observation_id": 7,
        "key": "p_f",
        "value": 0.5,
        "source": "fetched",
        "evidence": {"provider": "fire model", "spans": [1, 2]},
        "status": "accepted",
    },
    "fact_selected": {
        "key": "year_built",
        "observation_id": 8,
        "value": 1950,
        "source": "reply",
        "confirmed": True,
    },
    "conflict_opened": {
        "validator": "roof_before_build",
        "fields": ["roof_replacement_year", "year_built"],
        "values": {"roof_replacement_year": 1990, "year_built": 2000},
        "question": "Can you confirm the roof year?",
    },
    "conflict_closed": {
        "validator": "roof_before_build",
        "fields": ["roof_replacement_year", "year_built"],
        "values": {"roof_replacement_year": 1990, "year_built": 2000},
        "observation_id": 9,
    },
    "triage_completed": {"fields": {"year_built": {"value_status": "present", "depends_on": []}}},
    "provider_called": {
        "key": "protection_class",
        "status": "blocked",
        "value": None,
        "source": "stand-in",
        "fetched_at": "2026-06-29T08:01:00+00:00",
        "is_stub": True,
        "missing_inputs": ["zip"],
    },
    "plan_built": {"plan": {"asks": [], "effects": [{"kind": "no_action"}]}, "plan_hash": H},
    "blocker_opened": {
        "blocker_id": 1,
        "kind": "data",
        "owner": "data_team",
        "detail": {"reason": "lookup down"},
    },
    "blocker_closed": {"blocker_id": 1, "kind": "data"},
    "intent_created": {
        "intent_id": "i1",
        "round": 1,
        "kind": "routine_request",
        "recipient": "a@example.com",
        "subject": "s",
        "body": "b",
        "ask_ids": ["year_built", "q:contact_email"],
        "payload_hash": H,
    },
    "message_sent": {"intent_id": "i1", "mailbox_id": 12},
    "delivery_unknown": {"intent_id": "i1"},
    "reply_received": {"intent_id": "i1", "body": "It is 1950.", "body_hash": H},
    "reply_read": {
        "classification": "answers_some",
        "candidates": [
            {
                "ask_id": "year_built",
                "field": "year_built",
                "value": 1950,
                "quote": "1950",
                "span_start": 6,
                "span_end": 10,
            }
        ],
        "dropped": [
            {"ask_id": "pool_type", "field": "pool_type", "value": "Inground", "quote": "pool"}
        ],
    },
    "approval_recorded": {
        "item_id": 4,
        "item_kind": "draft",
        "intent_id": "i1",
        "lead_revision": 2,
        "plan_hash": H,
        "ruleset_hash": H,
        "recipient": "a@example.com",
        "payload_hash": H,
        "decision": "approved",
        "reason": "ok",
    },
    "ruling_recorded": {
        "choice_id": "I07.two_months",
        "option": "under_60_days",
        "reason": "r",
        "plan_hash": H,
        "suppressed_rule_ids": [],
    },
    "command_refused": {"command_type": "approve", "reason": "stale hash"},
    "setting_changed": {"key": "autonomy.fetch_data", "value": "review"},
    "class_demoted": {"command_class": "send_routine_request", "reason": "duplicate"},
    "rule_change_applied": {"proposal_id": 3, "diff_hash": H, "new_ruleset_hash": H},
    "skill_fallback_used": {"skill": "read_reply", "status": "failing", "fallback": "unread"},
    "model_called": {
        "skill": "read_reply",
        "prompt_version": H,
        "input_hash": H,
        "tokens_in": 100,
        "tokens_out": 20,
        "stop_reason": "tool_use",
    },
    "fault_injected": {"fault": "provider_unavailable"},
}

ROW_COLUMNS = {
    "run_id",
    "mode",
    "lead_id",
    "type",
    "actor",
    "prompt_versions_json",
    "model_id",
    "request_id",
    "real_ts",
    "sim_ts",
}


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def test_event_type_enum_equals_the_28_names_of_a2() -> None:
    assert len(A2_NAMES) == 28
    assert [t.value for t in EventType] == A2_NAMES
    assert {t.name for t in EventType} == set(A2_NAMES)


def test_each_type_has_a_payload_model_named_after_it() -> None:
    assert set(PAYLOAD_MODELS) == set(EventType)
    for name in A2_NAMES:
        model = PAYLOAD_MODELS[EventType(name)]
        assert model.__name__ == pascal(name)
        assert getattr(event_types, pascal(name)) is model
        assert issubclass(model, BaseModel)


def test_the_test_tables_cover_every_type() -> None:
    assert set(EXPECTED_FIELDS) == set(A2_NAMES)
    assert set(SAMPLES) == set(A2_NAMES)


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_fields(name: str) -> None:
    fields = set(PAYLOAD_MODELS[EventType(name)].model_fields)
    assert fields == EXPECTED_FIELDS[name]
    assert "confidence" not in fields
    assert not fields & ROW_COLUMNS


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_forbids_unknown_fields(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    with pytest.raises(ValidationError):
        model.model_validate({**SAMPLES[name], "surprise": 1})


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_requires_every_field(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    for field in SAMPLES[name]:
        partial = {k: v for k, v in SAMPLES[name].items() if k != field}
        with pytest.raises(ValidationError):
            model.model_validate(partial)


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_round_trips_through_json(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    payload = model.model_validate(SAMPLES[name])
    assert model.model_validate_json(payload.model_dump_json()) == payload


def test_round_trip_keeps_value_types() -> None:
    model = PAYLOAD_MODELS[EventType.fact_selected]
    for value in (True, 1, 1.0, "1", None, ["a"], {"k": 1.5}):
        payload = model.model_validate({**SAMPLES["fact_selected"], "value": value})
        back = model.model_validate_json(payload.model_dump_json())
        assert back == payload
        assert type(back.value) is type(value)  # type: ignore[attr-defined]


def test_reply_read_candidates_carry_the_a9_fields() -> None:
    model = PAYLOAD_MODELS[EventType.reply_read]
    located = model.model_fields["candidates"].annotation
    dropped = model.model_fields["dropped"].annotation
    assert located is not None and dropped is not None
    assert set(located.__args__[0].model_fields) == {  # type: ignore[attr-defined]
        "ask_id",
        "field",
        "value",
        "quote",
        "span_start",
        "span_end",
    }
    assert set(dropped.__args__[0].model_fields) == {  # type: ignore[attr-defined]
        "ask_id",
        "field",
        "value",
        "quote",
    }


def test_provider_status_and_observation_values_are_closed_sets() -> None:
    provider = PAYLOAD_MODELS[EventType.provider_called]
    with pytest.raises(ValidationError):
        provider.model_validate({**SAMPLES["provider_called"], "status": "maybe"})
    observed = PAYLOAD_MODELS[EventType.fact_observed]
    with pytest.raises(ValidationError):
        observed.model_validate({**SAMPLES["fact_observed"], "source": "guess"})
    with pytest.raises(ValidationError):
        observed.model_validate({**SAMPLES["fact_observed"], "status": "maybe"})
