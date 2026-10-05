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
    BuildQuotePacketInput,
    BuildQuotePacketResult,
    Candidate,
    EvaluatePlaybookInput,
    LocatedCandidate,
    PlanAsksInput,
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
        "requests_sent": 0,
        "open_request": False,
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
        "outstanding_asks": [],
        "open_blocker_kinds": [],
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
    "plan_asks": {
        "asks": [ASK],
        "message_class": "routine_request",
        "round": 1,
        "request": "send",
    },
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
    for reason in ("timeout", "invalid_input", ""):  # A.10: two codes and nothing else
        with pytest.raises(ValidationError):
            Abstention.model_validate({"reason": reason, "message": "m"})


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


# No request to send: no class, no round. `asks` is the outstanding asks, empty only for "none".
NO_REQUEST = {"asks": [], "message_class": None, "round": None, "request": "none"}
HELD = {**NO_REQUEST, "asks": [ASK]}


def test_plan_asks_input_counts_the_requests_the_lead_has_had_and_whether_one_is_open() -> None:
    # 10.1 "one open request per lead" and 7.5 "rounds number requests only".
    assert {"requests_sent", "open_request"} <= set(PlanAsksInput.model_fields)
    parsed = PlanAsksInput.model_validate(
        {**INPUTS["plan_asks"], "requests_sent": 1, "open_request": True}
    )
    assert (parsed.requests_sent, parsed.open_request) == (1, True)
    for missing in ("requests_sent", "open_request"):
        without = {k: v for k, v in INPUTS["plan_asks"].items() if k != missing}
        with pytest.raises(ValidationError, match=missing):
            PlanAsksInput.model_validate(without)


def test_the_round_a_request_takes_is_set_exactly_when_there_is_a_request() -> None:
    # 7.5: the first request is round 1, so a request after one sent is round 2.
    second = PlanAsksResult.model_validate({**RESULTS["plan_asks"], "round": 2})
    assert (second.message_class, second.round) == ("routine_request", 2)
    with pytest.raises(ValidationError, match="round"):
        PlanAsksResult.model_validate({**RESULTS["plan_asks"], "round": None})
    with pytest.raises(ValidationError, match="round"):
        PlanAsksResult.model_validate({**NO_REQUEST, "round": 1})
    with pytest.raises(ValidationError, match="round"):
        PlanAsksResult.model_validate({**HELD, "request": "round_limit", "round": 3})


@pytest.mark.parametrize("request_value", ["request_open", "round_limit"])
def test_a_held_request_keeps_the_outstanding_asks(request_value: str) -> None:
    # 10.1 "One open request per lead. A second request is allowed only after a reply." and
    # "After two rounds the lead goes to the underwriter": the asks stay, nothing is sent.
    held = PlanAsksResult.model_validate({**HELD, "request": request_value})
    assert held.request == request_value
    assert [a.model_dump() for a in held.asks] == RESULTS["plan_asks"]["asks"]
    assert held.message_class is None and held.round is None


def test_nothing_left_to_ask_is_none_and_has_no_asks() -> None:
    nothing = PlanAsksResult.model_validate(NO_REQUEST)
    assert (nothing.request, nothing.asks) == ("none", [])


def test_a_request_is_sent_with_its_asks_class_and_round() -> None:
    sent = PlanAsksResult.model_validate(RESULTS["plan_asks"])
    assert (sent.request, sent.message_class, sent.round) == ("send", "routine_request", 1)
    assert sent.asks


@pytest.mark.parametrize(
    "bad",
    [
        # none: asks is empty
        {**NO_REQUEST, "asks": [ASK]},
        # send: asks, class and round all set
        {**RESULTS["plan_asks"], "asks": []},
        {**RESULTS["plan_asks"], "message_class": None},
        {**RESULTS["plan_asks"], "round": None},
        # request_open and round_limit: asks stay, no class, no round
        {**NO_REQUEST, "request": "request_open"},
        {**NO_REQUEST, "request": "round_limit"},
        {**HELD, "request": "request_open", "message_class": "routine_request"},
        {**HELD, "request": "round_limit", "message_class": "routine_request"},
        {**HELD, "request": "request_open", "round": 1},
        # a class outside the two request classes, and a value outside the four
        {**RESULTS["plan_asks"], "message_class": "quote_packet"},
        {**RESULTS["plan_asks"], "request": "later"},
        # the removed flag is no field
        {**NO_REQUEST, "round_limit_reached": False},
    ],
)
def test_a_plan_asks_result_that_breaks_its_request_value_is_refused(
    bad: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PlanAsksResult.model_validate(bad)


def test_plan_asks_names_the_message_class_of_its_asks() -> None:
    assert list(PlanAsksResult.model_fields) == ["asks", "message_class", "round", "request"]
    classes = [
        arg
        for arg in get_args(PlanAsksResult.model_fields["message_class"].annotation)
        if arg is not type(None)
    ]
    assert [get_args(c) for c in classes] == [("routine_request", "sensitive_request")]
    assert get_args(PlanAsksResult.model_fields["request"].annotation) == (
        "send",
        "none",
        "request_open",
        "round_limit",
    )
    sensitive = PlanAsksResult.model_validate(
        {**RESULTS["plan_asks"], "message_class": "sensitive_request"}
    )
    assert sensitive.message_class == "sensitive_request"


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


def test_the_quote_packet_lines_carry_the_deadline_of_a_surcharge_or_an_adjustment() -> None:
    # 10.5: a surcharge or coverage adjustment that carries a deadline shows it on its line.
    packet = QuotePacket.model_validate(
        {
            **PACKET,
            "surcharges": [{**PACKET["surcharges"][0], "deadline": "duration_of_non_occupancy"}],
            "coverage_adjustments": [
                {**PACKET["coverage_adjustments"][0], "deadline": "within_30_days_of_bind"}
            ],
        }
    )
    assert packet.surcharges[0].deadline == "duration_of_non_occupancy"
    assert packet.coverage_adjustments[0].deadline == "within_30_days_of_bind"
    plain = QuotePacket.model_validate(PACKET)
    assert plain.surcharges[0].deadline is None and plain.coverage_adjustments[0].deadline is None
    with pytest.raises(ValidationError):
        QuotePacket.model_validate(
            {**PACKET, "surcharges": [{**PACKET["surcharges"][0], "deadline": "soon"}]}
        )


UNDECIDED_PLAN = {"undecided": [{"graph": "roof", "waits_on": ["roof_material"]}]}
OPEN_CHOICE_PLAN = {
    "open_choices": [
        {
            "choice_id": "I13.fire_fail",
            "options": ["decline", "legacy_underwriting"],
            "prompt": "p",
            "show": [],
        }
    ]
}
DECLINE_PLAN = {"proposed_decline": True, "underwriter_decline": "Reputational damage"}


def test_a_quote_packet_input_with_nothing_left_to_settle_is_accepted() -> None:
    packet_input = BuildQuotePacketInput.model_validate(INPUTS["build_quote_packet"])
    assert packet_input.outstanding_asks == [] and packet_input.open_blocker_kinds == []


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"plan": DECLINE_PLAN}, "proposed decline"),
        ({"plan": UNDECIDED_PLAN}, "undecided page"),
        ({"plan": OPEN_CHOICE_PLAN}, "open choice"),
        ({"open_blocker_kinds": ["producer_reply"]}, "open blocker.*producer_reply"),
        ({"open_blocker_kinds": ["waiting"]}, "open_blocker_kinds"),
        ({"outstanding_asks": [ASK]}, "outstanding ask.*pool_security"),
    ],
)
def test_the_quote_packet_skill_refuses_an_input_that_breaks_its_precondition(
    change: dict[str, Any], named: str
) -> None:
    # 9.6: the skill runs only when the plan holds no decline, no graph is undecided, no blocker
    # is open and no ask remains.
    with pytest.raises(ValidationError, match=named):
        BuildQuotePacketInput.model_validate({**INPUTS["build_quote_packet"], **change})


def test_the_quote_packet_precondition_names_every_broken_part() -> None:
    with pytest.raises(ValidationError) as error:
        BuildQuotePacketInput.model_validate(
            {
                **INPUTS["build_quote_packet"],
                "plan": {**UNDECIDED_PLAN, **OPEN_CHOICE_PLAN},
                "open_blocker_kinds": ["data"],
            }
        )
    message = str(error.value)
    assert "undecided page" in message and "open choice" in message and "open blocker" in message


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


def test_a_blocker_request_refuses_an_owner_outside_the_three() -> None:
    blocker = RESULTS["resolve_data"]["blockers"][0]
    assert BlockerRequest.model_validate({**blocker, "owner": "data_team"}).owner == "data_team"
    with pytest.raises(ValidationError, match="owner"):
        BlockerRequest.model_validate({**blocker, "owner": "made_up"})
    with pytest.raises(ValidationError, match="kind"):
        BlockerRequest.model_validate({**blocker, "kind": "made_up"})


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
