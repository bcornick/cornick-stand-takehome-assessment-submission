# ABOUTME: Tests canonical JSON per A.4 and the plan, payload and ruleset hashes over their A.4 inputs.
# ABOUTME: Expected bytes and digests are written out here with hashlib; a Hypothesis property checks that key order never changes a hash.
import datetime
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from uwh.runtime.hashing import (
    active_ruleset_dir,
    canonical_json,
    hash_json,
    payload_hash,
    plan_hash,
    ruleset_hash,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_canonical_json_sorts_keys_and_drops_whitespace() -> None:
    value = {"b": 1, "a": [1, 2, {"d": None, "c": True}]}
    assert canonical_json(value) == b'{"a":[1,2,{"c":true,"d":null}],"b":1}'


def test_canonical_json_writes_non_ascii_as_utf8() -> None:
    assert canonical_json({"k": "café ☃"}) == '{"k":"café ☃"}'.encode()


def test_canonical_json_escapes_what_json_requires() -> None:
    assert canonical_json('a\nb"c') == b'"a\\nb\\"c"'


def test_canonical_json_floats_use_the_shortest_round_trip_text() -> None:
    assert canonical_json([0.1, 1.5, 1e22]) == b"[0.1,1.5,1e+22]"
    # An integer and a float with the same value are different JSON text, so different hashes.
    assert canonical_json(1) == b"1"
    assert canonical_json(1.0) == b"1.0"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(bad: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": bad})


@pytest.mark.parametrize(
    "bad",
    [{1, 2}, datetime.datetime(2026, 6, 29), b"bytes", object(), {"x": {1, 2}}],
)
def test_canonical_json_rejects_values_that_are_not_json(bad: Any) -> None:
    with pytest.raises(TypeError):
        canonical_json(bad)


def test_canonical_json_rejects_non_string_keys() -> None:
    with pytest.raises(TypeError):
        canonical_json({1: "a"})
    with pytest.raises(TypeError):
        canonical_json({True: "a"})


def test_canonical_json_treats_a_tuple_as_a_list() -> None:
    assert canonical_json((1, 2)) == b"[1,2]"


def test_hash_json_is_sha256_of_canonical_json() -> None:
    value = {"b": "é", "a": 1}
    assert hash_json(value) == sha('{"a":1,"b":"é"}'.encode())


json_leaf = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
json_values = st.recursive(
    json_leaf,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=5), inner, max_size=4)
    ),
    max_leaves=12,
)


def reorder_keys(value: Any, rng: random.Random) -> Any:
    if isinstance(value, dict):
        items = [(k, reorder_keys(v, rng)) for k, v in value.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(value, list):
        return [reorder_keys(v, rng) for v in value]
    return value


@settings(max_examples=100, deadline=None)
@given(value=json_values, seed=st.integers())
def test_hash_of_a_mapping_does_not_depend_on_key_order(value: Any, seed: int) -> None:
    shuffled = reorder_keys(value, random.Random(seed))
    assert canonical_json(shuffled) == canonical_json(value)
    assert hash_json(shuffled) == hash_json(value)
    # The canonical text parses back to the same value.
    assert json.loads(canonical_json(value)) == value


def test_hash_json_depends_on_list_order() -> None:
    assert hash_json([1, 2]) != hash_json([2, 1])


def test_plan_hash_is_the_hash_of_the_plan() -> None:
    plan = {"asks": [{"id": "year_built"}], "effects": []}
    assert plan_hash(plan) == sha(b'{"asks":[{"id":"year_built"}],"effects":[]}')
    assert plan_hash(plan) != plan_hash({"asks": [], "effects": []})


def test_payload_hash_covers_recipient_subject_and_body() -> None:
    expected = sha(b'{"body":"b","recipient":"r","subject":"s"}')
    assert payload_hash("r", "s", "b") == expected
    assert payload_hash("r2", "s", "b") != expected
    assert payload_hash("r", "s2", "b") != expected
    assert payload_hash("r", "s", "b2") != expected
    # Moving text between fields changes the hash.
    assert payload_hash("r", "sb", "") != payload_hash("r", "s", "b")


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def test_ruleset_hash_covers_relative_path_and_content_in_path_order(tmp_path: Path) -> None:
    write(tmp_path, {"a/z.yaml": "one", "a.b": "two", "graphs/g.yaml": "three"})
    # Path order is the order of the whole posix path: "a.b" sorts before "a/z.yaml".
    expected = hash_json(
        [
            {"path": "a.b", "sha256": sha(b"two")},
            {"path": "a/z.yaml", "sha256": sha(b"one")},
            {"path": "graphs/g.yaml", "sha256": sha(b"three")},
        ]
    )
    assert ruleset_hash(tmp_path) == expected


def test_ruleset_hash_does_not_depend_on_creation_order(tmp_path: Path) -> None:
    files = {"b.yaml": "1", "a.yaml": "2", "d/c.yaml": "3"}
    write(tmp_path / "one", files)
    write(tmp_path / "two", dict(reversed(files.items())))
    assert ruleset_hash(tmp_path / "one") == ruleset_hash(tmp_path / "two")


def test_ruleset_hash_changes_with_content_rename_and_added_file(tmp_path: Path) -> None:
    write(tmp_path / "base", {"a.yaml": "1", "d/b.yaml": "2"})
    base = ruleset_hash(tmp_path / "base")

    write(tmp_path / "content", {"a.yaml": "1", "d/b.yaml": "3"})
    write(tmp_path / "renamed", {"a.yaml": "1", "d/c.yaml": "2"})
    write(tmp_path / "moved", {"a.yaml": "1", "b.yaml": "2"})
    write(tmp_path / "added", {"a.yaml": "1", "d/b.yaml": "2", "e.yaml": ""})
    others = {ruleset_hash(tmp_path / n) for n in ("content", "renamed", "moved", "added")}
    assert base not in others
    assert len(others) == 4


def test_ruleset_hash_ignores_compiled_files(tmp_path: Path) -> None:
    write(tmp_path / "a", {"x.yaml": "1"})
    write(tmp_path / "b", {"x.yaml": "1", "__pycache__/m.cpython-312.pyc": "z", "m.pyc": "z"})
    assert ruleset_hash(tmp_path / "a") == ruleset_hash(tmp_path / "b")


@pytest.mark.parametrize(
    "stray",
    [".DS_Store", "d/.DS_Store", ".hidden/x.yaml", "d/.cache/y.yaml", "a.yaml~", "d/b.yaml.swp"],
)
def test_ruleset_hash_ignores_hidden_files_and_editor_leftovers(tmp_path: Path, stray: str) -> None:
    write(tmp_path / "a", {"a.yaml": "1", "d/b.yaml": "2"})
    write(tmp_path / "b", {"a.yaml": "1", "d/b.yaml": "2", stray: "junk"})
    assert ruleset_hash(tmp_path / "a") == ruleset_hash(tmp_path / "b")


def test_ruleset_hash_of_a_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ruleset_hash(tmp_path / "absent")


def test_active_ruleset_dir_is_the_named_directory_or_the_image_data(tmp_path: Path) -> None:
    rulesets = tmp_path / "volume" / "rulesets"
    image_data = tmp_path / "app" / "src" / "uwh" / "rules" / "data"
    assert active_ruleset_dir(None, rulesets, image_data) == image_data
    name = "0123456789abcdef" * 4
    assert active_ruleset_dir(name, rulesets, image_data) == rulesets / name


@pytest.mark.parametrize(
    "bad",
    ["", "..", "a/b", "a\\b", "../x", "abc123", "A" * 64, "a" * 63, "a" * 65, "g" * 64],
)
def test_active_ruleset_dir_rejects_a_value_that_is_not_a_sha256_hex_hash(
    tmp_path: Path, bad: str
) -> None:
    with pytest.raises(ValueError):
        active_ruleset_dir(bad, tmp_path / "r", tmp_path / "d")
