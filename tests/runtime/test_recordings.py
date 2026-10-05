# ABOUTME: Tests that a model exchange is stored under its skill, prompt version and input hash, reads back by the same key, and that the input hash covers only what the model is shown.
# ABOUTME: Each test writes real files under a temporary directory; the committed file format (sorted keys, two-space indent, trailing LF) is asserted on the bytes.
import json
from pathlib import Path

import pytest

from uwh.runtime.hashing import sha256_hex
from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    input_hash,
    prompt_version,
    read_recording,
    write_recording,
)


def shown(body: str = "Yes, the roof is 2012.", asks: tuple[str, ...] = ("roof_year",)) -> dict:
    return {"reply_body": body, "open_asks": list(asks)}


def key_for(content: dict, skill: str = "read_reply", version: str = "a" * 64) -> RecordingKey:
    return RecordingKey(skill=skill, prompt_version=version, input_hash=input_hash(content))


def exchange_for(key: RecordingKey, content: dict, **changes) -> Exchange:
    fields = {
        "skill": key.skill,
        "prompt_version": key.prompt_version,
        "input_hash": key.input_hash,
        "input": content,
        "model_id": "deepseek-flash",
        "request_id": "req_1",
        "stop_reason": "tool_use",
        "tokens_in": 120,
        "tokens_out": 30,
        "tool_input": {"candidates": [{"field": "roof_year", "quote": "2012"}]},
    }
    return Exchange(**{**fields, **changes})


def test_exchange_reads_back_by_the_key_it_was_written_under(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    written = exchange_for(key, content)
    write_recording(tmp_path, key, written)
    assert read_recording(tmp_path, key) == written


def test_file_path_is_skill_prompt_version_input_hash(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    write_recording(tmp_path, key, exchange_for(key, content))
    assert (tmp_path / "read_reply" / ("a" * 64) / f"{key.input_hash}.json").is_file()


def test_absent_key_reads_as_none_and_a_different_key_does_not_hit(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    write_recording(tmp_path, key, exchange_for(key, content))
    assert read_recording(tmp_path, key_for(shown(body="No."))) is None
    assert read_recording(tmp_path, key_for(content, version="b" * 64)) is None
    assert read_recording(tmp_path, key_for(content, skill="chat")) is None
    assert read_recording(tmp_path / "elsewhere", key) is None


def test_file_is_sorted_two_space_indented_with_one_trailing_lf(tmp_path: Path) -> None:
    content = shown(body="Café 2012")
    key = key_for(content)
    write_recording(tmp_path, key, exchange_for(key, content))
    raw = (tmp_path / key.skill / key.prompt_version / f"{key.input_hash}.json").read_bytes()
    parsed = json.loads(raw)
    assert raw == (json.dumps(parsed, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    assert b"\r" not in raw
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n")
    assert "Café".encode() in raw


def test_refusal_exchange_without_tool_input_round_trips(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    refusal = exchange_for(key, content, stop_reason="refusal", tool_input=None)
    write_recording(tmp_path, key, refusal)
    assert read_recording(tmp_path, key) == refusal


def test_exchange_holds_no_credential_or_header_field() -> None:
    names = set(Exchange.__dataclass_fields__)
    assert names == {
        "skill",
        "prompt_version",
        "input_hash",
        "input",
        "model_id",
        "request_id",
        "stop_reason",
        "tokens_in",
        "tokens_out",
        "tool_input",
    }


def test_writing_under_a_key_the_exchange_does_not_carry_is_refused(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    other = key_for(shown(body="No."))
    with pytest.raises(ValueError, match="key"):
        write_recording(tmp_path, other, exchange_for(key, content))


@pytest.mark.parametrize("part", ["../x", "a/b", "", "a b", "."])
def test_key_parts_cannot_leave_the_directory(part: str) -> None:
    with pytest.raises(ValueError):
        RecordingKey(skill=part, prompt_version="a" * 64, input_hash="b" * 64)


def test_same_input_on_two_runs_with_different_ids_reads_one_recording(tmp_path: Path) -> None:
    # The skill builds `shown` from the reply body and the open asks only; run and intent ids
    # are in the skill's inputs but never in what the model is shown.
    run_one = {"run_id": "run-1", "intent_id": 11, **shown()}
    run_two = {"run_id": "run-2", "intent_id": 97, **shown()}
    first = shown_for(run_one)
    second = shown_for(run_two)
    assert input_hash(first) == input_hash(second)
    key = key_for(first)
    write_recording(tmp_path, key, exchange_for(key, first))
    assert read_recording(tmp_path, key_for(second)) is not None


def shown_for(skill_input: dict) -> dict:
    """What `read_reply` shows the model: the reply body and the open asks, nothing else."""
    return {"reply_body": skill_input["reply_body"], "open_asks": skill_input["open_asks"]}


def test_input_hash_changes_with_the_reply_body_or_the_ask_list() -> None:
    base = input_hash(shown())
    assert input_hash(shown(body="Yes, the roof is 2013.")) != base
    assert input_hash(shown(asks=("roof_year", "roof_material"))) != base
    assert input_hash(shown(asks=())) != base


def test_input_hash_is_independent_of_key_order() -> None:
    assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})


def test_prompt_version_is_the_hash_of_the_file_bytes(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_bytes(b"Read the reply.\n")
    version = prompt_version(prompt)
    assert version == sha256_hex(b"Read the reply.\n")
    prompt.write_bytes(b"Read the reply carefully.\n")
    assert prompt_version(prompt) != version
