# ABOUTME: Tests that a model exchange is stored under its skill, prompt version and input hash, reads back by the same key only, and that the input hash follows the content and not the key order.
# ABOUTME: Each test writes real files under a temporary directory.
from pathlib import Path

from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    input_hash,
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


def test_an_exchange_reads_back_by_the_key_it_was_written_under_and_no_other_key_hits(
    tmp_path: Path,
) -> None:
    content = shown()
    key = key_for(content)
    written = exchange_for(key, content)
    write_recording(tmp_path, key, written)

    assert read_recording(tmp_path, key) == written
    assert read_recording(tmp_path, key_for(shown(body="No."))) is None
    assert read_recording(tmp_path, key_for(content, version="b" * 64)) is None
    assert read_recording(tmp_path, key_for(content, skill="chat")) is None


def test_a_refusal_exchange_without_tool_input_round_trips(tmp_path: Path) -> None:
    content = shown()
    key = key_for(content)
    refusal = exchange_for(key, content, stop_reason="refusal", tool_input=None)
    write_recording(tmp_path, key, refusal)
    assert read_recording(tmp_path, key) == refusal


def test_the_input_hash_follows_the_content_and_not_the_key_order() -> None:
    base = input_hash(shown())
    assert input_hash(shown(body="Yes, the roof is 2013.")) != base
    assert input_hash(shown(asks=("roof_year", "roof_material"))) != base
    assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})
