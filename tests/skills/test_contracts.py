# ABOUTME: Tests the input and output models of the seven section 8 skills, the shared typed abstention, the A.9 reply models and the section 10.5 quote packet.
# ABOUTME: Skill names, abstention codes and the A.9 field lists are written out here; every model forbids unknown fields and round-trips through JSON.
from typing import Annotated, Any, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from uwh.rules.models import Ask
from uwh.runtime import event_types
from uwh.skills import contracts
from uwh.skills.contracts import (
    Abstention,
    AskField,
    BlockerRequest,
    BuildQuotePacketResult,
    Candidate,
    EvaluatePlaybookInput,
    LocatedCandidate,
    PlanAsksResult,
    QuotePacket,
    ReadReplyInput,
    ReadReplyResult,
    RenderMessageInput,
    RenderMessageResult,
    ReplyReading,
    ResolvedObservation,
    ResolveDataResult,
    TriageFieldsInput,
)

# The seven section 8 skills, written out. Each has `<CamelName>Input` and `<CamelName>Output` in
# `contracts`; the output is the named result or the typed abstention.
SKILL_NAMES = [
    "triage_fields",
    "resolve_data",
    "evaluate_playbook",
    "plan_asks",
    "render_message",
    "read_reply",
    "build_quote_packet",
]
RESULT_NAMES = {
    "triage_fields": "TriageFieldsResult",
    "resolve_data": "ResolveDataResult",
    "evaluate_playbook": "ActionPlan",
    "plan_asks": "PlanAsksResult",
    "render_message": "RenderMessageResult",
    "read_reply": "ReadReplyResult",
    "build_quote_packet": "BuildQuotePacketResult",
}


def skill_contract(skill: str) -> tuple[type[BaseModel], Any, type[BaseModel]]:
    """The input model, the output union and the result model of a skill, looked up in `contracts`."""
    camel = "".join(word.capitalize() for word in skill.split("_"))
    input_model = getattr(contracts, f"{camel}Input", None)
    output = getattr(contracts, f"{camel}Output", None)
    result_model = getattr(contracts, RESULT_NAMES[skill], None)
    assert isinstance(input_model, type) and issubclass(input_model, BaseModel), f"{camel}Input"
    assert output is not None, f"{camel}Output"
    assert isinstance(result_model, type) and issubclass(result_model, BaseModel), RESULT_NAMES[
        skill
    ]
    return input_model, output, result_model


ASK = {
    "ask_id": "pool_security",
    "kind": "follow_on_question",
    "fields": ["pool_security"],
    "reason": "conditional_unknown",
    "wording": "If there is a pool: is it fenced?",
}
FIELD_TRIAGE = {
    "value_status": "missing",
    "requirement": "required",
    "resolution": "ask",
    "depends_on": [],
}
FOUND = {
    "status": "found",
    "value": "4",
    "source": "fixture",
    "fetched_at": "2026-06-29T08:00:00+00:00",
    "is_stub": False,
}
CONFLICT = {
    "validator": "roof_before_build",
    "fields": ["roof_replacement_year", "year_built"],
    "values": {"roof_replacement_year": 1990, "year_built": 2001},
    "question": "Please confirm the year built and the year the roof was replaced.",
}
CANDIDATE = {
    "ask_id": "pool_security",
    "field": "pool_security",
    "value": "Fenced",
    "quote": "the pool is fenced",
}
LOCATED = {**CANDIDATE, "span_start": 4, "span_end": 22}
PACKET = {
    "coverages": [{"field": "coverage_a", "value": 500000}],
    "coverage_adjustments": [
        {
            "type": "coverage_adjustment",
            "rule": "RC-1",
            "field": "coverage_a",
            "proposed_value": 450000,
            "submitted_value": 500000,
        }
    ],
    "surcharges": [{"type": "surcharge", "rule": "PP-3", "percent": 15}],
    "requirements": [
        {
            "type": "requirement",
            "rule": "RF-2",
            "text": "Replace the roof",
            "deadline": "first_term",
        }
    ],
    "exclusions_and_endorsements": [
        {"type": "exclusion_or_endorsement", "rule": "PR-1", "text": "Exclude liability"}
    ],
    "advisories": [{"type": "advisory", "rule": "PR-2", "text": "Vinyl siding"}],
    "obligations": [
        {
            "type": "obligation",
            "rule": "TR-1",
            "text": "Return the trust questionnaire",
            "owner": "producer",
            "trigger": "post_bind",
        }
    ],
    "notes": [
        {"ref": "plumbing", "text": "Plumbing is not evaluated"},
        {"ref": "electrical", "text": "Electrical is not evaluated"},
    ],
}

# One valid input and one valid result per skill; the inputs carry values only.
INPUTS: dict[str, dict[str, Any]] = {
    "triage_fields": {
        "facts": {"pool_type": None, "year_built": 1990},
        "conflicting_fields": ["roof_replacement_year"],
        "unsupported_fields": ["kyc_score"],
        "blocked_lookups": {"protection_class": ["street_address", "zip"]},
    },
    "resolve_data": {
        "facts": {"year_built": None},
        "triage": {"year_built": FIELD_TRIAGE},
        "provider_results": {"protection_class": FOUND},
    },
    "evaluate_playbook": {
        "facts": {"foundation_type": "Piers"},
        "answered_choices": {"I13.fire_fail": "decline"},
        "suppressed_rules": ["PP-1"],
        "underwriter_decline": None,
    },
    "plan_asks": {
        "triage": {"year_built": FIELD_TRIAGE},
        "resolved": {
            "observations": [],
            "ask_fields": [
                {"field": "street_address", "reason": "blocked lookup: protection_class"}
            ],
            "catalogue_questions": ["kt_present_and_where"],
            "blockers": [],
        },
        "plan": {},
        "conflicts": [CONFLICT],
    },
    "render_message": {
        "kind": "request",
        "lead_label": "LEAD-00000042-001",
        "audience": "producer",
        "asks": [ASK],
    },
    "read_reply": {"body": "Yes, the pool is fenced.", "open_asks": [ASK]},
    "build_quote_packet": {
        "plan": {},
        "facts": {"coverage_a": 500000},
        "assumed": {"protection_class": "9"},
    },
}
RESULTS: dict[str, dict[str, Any]] = {
    "triage_fields": {"fields": {"year_built": FIELD_TRIAGE}},
    "resolve_data": {
        "observations": [
            {
                "key": "protection_class",
                "value": "9",
                "source": "assumed",
                "evidence": {"rule": "9.3"},
            },
        ],
        "ask_fields": [
            {"field": "zip", "reason": "the lookup of protection_class is blocked on it"}
        ],
        "catalogue_questions": [],
        "blockers": [
            {
                "kind": "data",
                "owner": "data_team",
                "detail": {"resume_trigger": "provider answers", "text": "kyc_score unavailable"},
            },
        ],
    },
    "evaluate_playbook": {"proposed_decline": False},
    "plan_asks": {"asks": [ASK], "message_class": "routine_request"},
    "render_message": {
        "subject": "Information needed for your quote: LEAD-00000042-001",
        "body": "Thank you for your submission.",
        "ask_ids": ["pool_security"],
    },
    "read_reply": {
        "classification": "answers_some",
        "candidates": [LOCATED],
        "dropped": [CANDIDATE],
    },
    "build_quote_packet": {
        "packet": PACKET,
        "internal": {"assumptions": {"protection_class": "9"}, "rule_traces": [], "approver": None},
    },
}


def test_there_is_one_input_and_one_output_for_each_of_the_seven_skills() -> None:
    assert len(SKILL_NAMES) == 7
    assert list(INPUTS) == list(RESULTS) == list(RESULT_NAMES) == SKILL_NAMES
    for skill in SKILL_NAMES:
        input_model, output, result_model = skill_contract(skill)
        assert input_model is not result_model
        assert get_args(output)


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_an_input_validates_and_round_trips(skill: str) -> None:
    input_model = skill_contract(skill)[0]
    value = input_model.model_validate(INPUTS[skill])
    assert input_model.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_an_input_forbids_unknown_fields(skill: str) -> None:
    input_model = skill_contract(skill)[0]
    with pytest.raises(ValidationError):
        input_model.model_validate({**INPUTS[skill], "surprise": 1})


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_an_output_is_the_skills_result_or_the_typed_abstention(skill: str) -> None:
    _, output, result_model = skill_contract(skill)
    assert set(get_args(output)) == {result_model, Abstention}


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_an_output_picks_the_result_and_round_trips(skill: str) -> None:
    _, output, result_model = skill_contract(skill)
    adapter = TypeAdapter(output)
    value = adapter.validate_python(RESULTS[skill])
    assert type(value) is result_model
    assert adapter.validate_json(adapter.dump_json(value)) == value


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_an_output_picks_the_abstention(skill: str) -> None:
    adapter = TypeAdapter(skill_contract(skill)[1])
    value = adapter.validate_python(
        {"reason": "invalid_tool_input", "message": "The tool input failed validation twice."}
    )
    assert type(value) is Abstention


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_a_result_forbids_unknown_fields(skill: str) -> None:
    result_model = skill_contract(skill)[2]
    with pytest.raises(ValidationError):
        result_model.model_validate({**RESULTS[skill], "surprise": 1})


def test_the_abstention_holds_a_reason_code_and_a_plain_message() -> None:
    assert list(Abstention.model_fields) == ["reason", "message"]
    for reason in ("refusal", "invalid_tool_input"):  # A.10
        assert Abstention(reason=reason, message="m").reason == reason
    with pytest.raises(ValidationError):
        Abstention.model_validate({"reason": "refusal", "message": "m", "surprise": 1})


def test_inputs_carry_no_handles_or_clients() -> None:
    for input_model in (skill_contract(skill)[0] for skill in SKILL_NAMES):
        assert not {
            n
            for n in input_model.model_fields
            if n in {"db", "conn", "connection", "client", "store"}
        }


def test_the_evaluate_playbook_input_holds_usable_facts_answered_choices_and_suppressed_rules() -> (
    None
):
    assert list(EvaluatePlaybookInput.model_fields) == [
        "facts",
        "answered_choices",
        "suppressed_rules",
        "underwriter_decline",
    ]
    assert (
        EvaluatePlaybookInput.model_validate({**INPUTS["evaluate_playbook"]}).underwriter_decline
        is None
    )
    ruled = EvaluatePlaybookInput.model_validate(
        {**INPUTS["evaluate_playbook"], "underwriter_decline": "Reputational damage"}
    )
    assert ruled.underwriter_decline == "Reputational damage"


def test_the_triage_input_names_conflicting_and_unsupported_fields_and_blocked_lookups() -> None:
    assert list(TriageFieldsInput.model_fields) == [
        "facts",
        "conflicting_fields",
        "unsupported_fields",
        "blocked_lookups",
    ]
    # A blocked lookup names its missing inputs (9.4); a lookup not yet made is not in the mapping.
    triage = TriageFieldsInput.model_validate(INPUTS["triage_fields"])
    assert triage.blocked_lookups == {"protection_class": ["street_address", "zip"]}
    with pytest.raises(ValidationError):
        TriageFieldsInput.model_validate(
            {**INPUTS["triage_fields"], "blocked_lookups": ["protection_class"]}
        )


def test_render_message_kinds_are_the_three_a8_subjects() -> None:
    assert list(get_args(RenderMessageInput.model_fields["kind"].annotation)) == [
        "request",
        "quote_packet",
        "decline_notice",
    ]


def test_render_message_names_the_audience_of_the_wording() -> None:
    assert list(get_args(RenderMessageInput.model_fields["audience"].annotation)) == [
        "producer",
        "applicant",
    ]
    applicant = RenderMessageInput.model_validate(
        {**INPUTS["render_message"], "audience": "applicant"}
    )
    assert applicant.audience == "applicant"
    with pytest.raises(ValidationError):
        RenderMessageInput.model_validate({**INPUTS["render_message"], "audience": "underwriter"})
    without = {k: v for k, v in INPUTS["render_message"].items() if k != "audience"}
    with pytest.raises(ValidationError):
        RenderMessageInput.model_validate(without)


def test_plan_asks_names_the_message_class_of_its_asks() -> None:
    assert list(PlanAsksResult.model_fields) == ["asks", "message_class"]
    classes = [
        arg
        for arg in get_args(PlanAsksResult.model_fields["message_class"].annotation)
        if arg is not type(None)
    ]
    assert [get_args(c) for c in classes] == [("routine_request", "sensitive_request")]
    sensitive = PlanAsksResult.model_validate(
        {**RESULTS["plan_asks"], "message_class": "sensitive_request"}
    )
    assert sensitive.message_class == "sensitive_request"
    nothing = PlanAsksResult.model_validate({"asks": [], "message_class": None})
    assert nothing.message_class is None


def test_the_message_class_is_none_exactly_when_there_is_nothing_to_ask() -> None:
    with pytest.raises(ValidationError):
        PlanAsksResult.model_validate({"asks": [ASK], "message_class": None})
    with pytest.raises(ValidationError):
        PlanAsksResult.model_validate({"asks": [], "message_class": "routine_request"})
    with pytest.raises(ValidationError):
        PlanAsksResult.model_validate({"asks": [ASK], "message_class": "quote_packet"})


def test_a_rendered_message_has_no_recipient_field() -> None:
    assert list(RenderMessageResult.model_fields) == ["subject", "body", "ask_ids"]
    assert "recipient" not in RenderMessageInput.model_fields


# A.9, written out.
def test_candidate_has_the_a9_fields_and_no_offset() -> None:
    assert list(Candidate.model_fields) == ["ask_id", "field", "value", "quote"]
    assert "span_start" not in Candidate.model_fields
    assert "span_end" not in Candidate.model_fields


def test_a_candidate_quote_is_not_empty() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "quote": ""})


@pytest.mark.parametrize("value", ["Fenced", 3, 1.5, True])
def test_a_candidate_value_is_a_string_number_or_boolean_and_keeps_its_type(value: Any) -> None:
    assert type(Candidate.model_validate({**CANDIDATE, "value": value}).value) is type(value)


def test_a_candidate_value_is_not_a_list() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "value": ["Fenced"]})


def test_reply_reading_is_a_classification_and_candidates() -> None:
    assert list(ReplyReading.model_fields) == ["classification", "candidates"]
    assert list(get_args(ReplyReading.model_fields["classification"].annotation)) == [
        "answers_all",
        "answers_some",
        "declines_to_answer",
        "off_topic",
    ]
    reading = ReplyReading.model_validate(
        {"classification": "answers_all", "candidates": [CANDIDATE]}
    )
    assert reading.candidates[0].quote == "the pool is fenced"


def test_the_reply_reading_schema_holds_no_offsets() -> None:
    schema = str(ReplyReading.model_json_schema())
    assert "span_start" not in schema and "span_end" not in schema


def test_reply_reading_refuses_a_located_candidate() -> None:
    with pytest.raises(ValidationError):
        ReplyReading.model_validate({"classification": "answers_all", "candidates": [LOCATED]})


def test_a_located_candidate_is_a_candidate_with_offsets() -> None:
    assert issubclass(LocatedCandidate, Candidate)
    assert list(LocatedCandidate.model_fields) == [
        *Candidate.model_fields,
        "span_start",
        "span_end",
    ]
    located = LocatedCandidate.model_validate(LOCATED)
    assert located.span_start == 4 and located.span_end == 22


def test_the_candidate_contracts_are_the_runtime_classes() -> None:
    assert Candidate is event_types.Candidate
    assert LocatedCandidate is event_types.LocatedCandidate
    assert contracts.ReplyClassification is event_types.ReplyClassification


def test_a_candidate_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "surprise": 1})


def test_the_read_reply_result_is_the_classification_with_located_candidates_and_the_dropped() -> (
    None
):
    assert list(ReadReplyResult.model_fields) == ["classification", "candidates", "dropped"]
    with pytest.raises(ValidationError):  # a candidate without offsets is not a located candidate
        ReadReplyResult.model_validate({**RESULTS["read_reply"], "candidates": [CANDIDATE]})


# Section 10.5.
def test_the_quote_packet_holds_the_section_10_5_parts() -> None:
    assert list(QuotePacket.model_fields) == [
        "coverages",
        "coverage_adjustments",
        "surcharges",
        "requirements",
        "exclusions_and_endorsements",
        "advisories",
        "obligations",
        "notes",
    ]


def test_the_quote_packet_shows_an_adjustment_beside_the_submitted_value() -> None:
    packet = QuotePacket.model_validate(PACKET)
    assert packet.coverages[0].value == 500000
    adjustment = packet.coverage_adjustments[0]
    assert (adjustment.submitted_value, adjustment.proposed_value) == (500000, 450000)


def test_the_quote_packet_puts_each_surcharge_on_its_own_line_with_its_rule() -> None:
    packet = QuotePacket.model_validate(
        {
            **PACKET,
            "surcharges": [
                PACKET["surcharges"][0],
                {"type": "surcharge", "rule": "PP-4", "percent": 25},
            ],
        }
    )
    assert [(s.percent, s.rule) for s in packet.surcharges] == [(15, "PP-3"), (25, "PP-4")]


def test_the_quote_packet_requirements_carry_deadlines() -> None:
    assert QuotePacket.model_validate(PACKET).requirements[0].deadline == "first_term"


def test_the_quote_packet_carries_the_obligations_and_the_not_evaluated_notes() -> None:
    packet = QuotePacket.model_validate(PACKET)
    assert [(o.rule, o.owner, o.trigger) for o in packet.obligations] == [
        ("TR-1", "producer", "post_bind")
    ]
    assert [n.ref for n in packet.notes] == ["plumbing", "electrical"]
    with pytest.raises(ValidationError):  # an obligation is not an advisory
        QuotePacket.model_validate({**PACKET, "obligations": PACKET["advisories"]})


PRICE_WORDS = ("price", "premium", "cost", "amount", "total", "fee", "rate")


def field_names(model: type[BaseModel]) -> set[str]:
    """Every field name of `model` and of each model reached through lists, `X | None`, unions and annotations."""

    def models_in(annotation: Any) -> list[type[BaseModel]]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        return [m for arg in get_args(annotation) for m in models_in(arg)]

    found = set(model.model_fields)
    for info in model.model_fields.values():
        for nested in models_in(info.annotation):
            found |= field_names(nested)
    return found


def test_no_field_of_the_packet_is_a_price_or_premium() -> None:
    packet_names = field_names(QuotePacket)
    assert {"percent", "text", "rule", "owner", "trigger"} <= packet_names
    assert not {n for n in packet_names if any(w in n for w in PRICE_WORDS)}


def test_the_price_check_reaches_models_nested_under_lists_options_and_unions() -> None:
    class Inner(BaseModel):
        monthly_premium: int

    class Deep(BaseModel):
        service_fee: int

    class Holder(BaseModel):
        lines: list[Inner] | None
        other: Annotated[Deep | int, "x"]

    assert {"monthly_premium", "service_fee"} <= field_names(Holder)


def test_the_resolve_data_result_gives_the_reason_for_each_ask() -> None:
    result = ResolveDataResult.model_validate(RESULTS["resolve_data"])
    assert result.ask_fields == [
        AskField(field="zip", reason="the lookup of protection_class is blocked on it")
    ]
    with pytest.raises(ValidationError):
        ResolveDataResult.model_validate({**RESULTS["resolve_data"], "ask_fields": ["zip"]})
    with pytest.raises(ValidationError):
        AskField.model_validate({"field": "zip"})


@pytest.mark.parametrize("source", ["derived", "fetched", "assumed"])
def test_a_resolved_observation_is_derived_fetched_or_assumed(source: str) -> None:
    observation = {**RESULTS["resolve_data"]["observations"][0], "source": source}
    assert ResolvedObservation.model_validate(observation).source == source


@pytest.mark.parametrize("source", ["submitted", "reply", "underwriter"])
def test_a_resolved_observation_is_never_submitted_or_stated(source: str) -> None:
    observation = {**RESULTS["resolve_data"]["observations"][0], "source": source}
    with pytest.raises(ValidationError):
        ResolvedObservation.model_validate(observation)


def test_a_blocker_request_carries_the_runtimes_blocker_detail() -> None:
    assert BlockerRequest.model_fields["detail"].annotation is event_types.BlockerDetail
    request = BlockerRequest.model_validate(RESULTS["resolve_data"]["blockers"][0])
    assert request.detail.resume_trigger == "provider answers"
    with pytest.raises(ValidationError):
        BlockerRequest.model_validate(
            {"kind": "data", "owner": "data_team", "detail": {"field": "kyc_score"}}
        )


# A.9 and A.1: `ask_id` is a registry field name, a bare catalogue id or a validator id; `fields`
# holds fact keys, which for a catalogue question is the id prefixed `q:`.
ASK_CONVENTION_SAMPLES = [
    ("field_request", "year_built", ["year_built"]),
    ("catalogue_question", "kt_extent", ["q:kt_extent"]),
    ("confirmation", "roof_before_build", ["roof_replacement_year", "year_built"]),
]


@pytest.mark.parametrize(("kind", "ask_id", "fields"), ASK_CONVENTION_SAMPLES)
def test_an_ask_id_is_a_field_catalogue_or_validator_id_and_fields_are_fact_keys(
    kind: str, ask_id: str, fields: list[str]
) -> None:
    ask = Ask.model_validate(
        {"ask_id": ask_id, "kind": kind, "fields": fields, "reason": "r", "wording": "w"}
    )
    assert ":" not in ask.ask_id
    if kind == "catalogue_question":
        assert ask.fields == [f"q:{ask.ask_id}"]
    elif kind == "field_request":
        assert ask.fields == [ask.ask_id]
    else:
        assert len(ask.fields) == 2 and ask.ask_id not in ask.fields


def test_the_internal_copy_lists_assumptions_the_rule_trace_and_the_approver() -> None:
    internal = BuildQuotePacketResult.model_validate(RESULTS["build_quote_packet"]).internal
    assert list(type(internal).model_fields) == ["assumptions", "rule_traces", "approver"]
    assert internal.assumptions == {"protection_class": "9"}
    assert internal.approver is None


def test_no_contract_model_carries_a_confidence() -> None:
    for cls in contract_classes():
        assert not {n for n in cls.model_fields if "confidence" in n}, cls


def contract_classes() -> list[type[BaseModel]]:
    return [
        c
        for c in vars(contracts).values()
        if isinstance(c, type) and issubclass(c, BaseModel) and c.__module__ == contracts.__name__
    ]


def test_every_asks_model_is_the_rules_ask() -> None:
    assert PlanAsksResult.model_fields["asks"].annotation == list[Ask]
    assert ReadReplyInput.model_fields["open_asks"].annotation == list[Ask]


def test_every_contract_model_forbids_unknown_fields() -> None:
    assert contract_classes()
    for cls in contract_classes():
        assert cls.model_config.get("extra") == "forbid", cls
