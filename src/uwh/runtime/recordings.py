# ABOUTME: Stores one model exchange per file, keyed by skill, prompt version and input hash (7.7), and reads it back by the same key.
# ABOUTME: Files are sorted-key JSON with a two-space indent and one trailing LF so committed recordings diff cleanly; nothing here reads settings or process state.
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uwh.runtime.hashing import hash_json, sha256_hex

_PATH_PART = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class RecordingKey:
    """What one recording answers: the skill, the SHA-256 of its `prompt.md` and the input hash."""

    skill: str
    prompt_version: str
    input_hash: str

    def __post_init__(self) -> None:
        for name in ("skill", "prompt_version", "input_hash"):
            if not _PATH_PART.fullmatch(getattr(self, name)):
                raise ValueError(f"recording key {name} must be letters, digits, _ or -")


@dataclass(frozen=True)
class Exchange:
    """One model exchange: what was shown, and what is needed to rebuild the skill's output and its `model_called` event.

    `tool_input` is the forced tool call's input as the model returned it, or None when the
    model returned no tool call (a refusal).
    """

    skill: str
    prompt_version: str
    input_hash: str
    input: dict[str, Any]
    model_id: str
    request_id: str
    stop_reason: str
    tokens_in: int
    tokens_out: int
    tool_input: dict[str, Any] | None


def input_hash(shown: Mapping[str, Any]) -> str:
    """The input hash: the hash of exactly the content the model is shown.

    The caller builds `shown` from that content alone (for `read_reply`, the reply body and
    the open asks), so run ids and intent ids never reach it.
    """
    return hash_json(dict(shown))


def prompt_version(prompt_file: Path) -> str:
    """The prompt version: the SHA-256 of the file's bytes (8)."""
    return sha256_hex(prompt_file.read_bytes())


def _path(directory: Path, key: RecordingKey) -> Path:
    return directory / key.skill / key.prompt_version / f"{key.input_hash}.json"


def write_recording(directory: Path, key: RecordingKey, exchange: Exchange) -> None:
    """Write `exchange` under `key`, replacing any recording already there."""
    if (exchange.skill, exchange.prompt_version, exchange.input_hash) != (
        key.skill,
        key.prompt_version,
        key.input_hash,
    ):
        raise ValueError("the exchange does not carry the key it is written under")
    path = _path(directory, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(exchange), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def read_recording(directory: Path, key: RecordingKey) -> Exchange | None:
    """The exchange recorded under `key`, or None when there is none."""
    path = _path(directory, key)
    if not path.is_file():
        return None
    return Exchange(**json.loads(path.read_bytes()))
