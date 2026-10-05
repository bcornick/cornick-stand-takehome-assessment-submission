# ABOUTME: Tests that the plan hash and the payload hash an approval binds to change when their inputs change.
# ABOUTME: The key order of a mapping never changes a hash; the order of a list and the text moved between payload fields do.
import hashlib

from uwh.runtime.hashing import hash_json, payload_hash, plan_hash


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_a_mapping_hashes_the_same_in_any_key_order_and_a_list_does_not() -> None:
    assert hash_json({"a": 1, "b": [1, 2]}) == hash_json({"b": [1, 2], "a": 1})
    assert hash_json([1, 2]) != hash_json([2, 1])


def test_plan_hash_changes_with_the_plan() -> None:
    plan = {"asks": [{"id": "year_built"}], "effects": []}
    assert plan_hash(plan) == sha(b'{"asks":[{"id":"year_built"}],"effects":[]}')
    assert plan_hash(plan) != plan_hash({"asks": [], "effects": []})


def test_payload_hash_covers_recipient_subject_and_body() -> None:
    expected = sha(b'{"body":"b","recipient":"r","subject":"s"}')
    assert payload_hash("r", "s", "b") == expected
    assert payload_hash("r2", "s", "b") != expected
    assert payload_hash("r", "s2", "b") != expected
    assert payload_hash("r", "s", "b2") != expected
    assert payload_hash("r", "sb", "") != payload_hash("r", "s", "b")
