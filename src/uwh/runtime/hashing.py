# ABOUTME: SHA-256 over canonical JSON (A.4): the plan, payload and ruleset hashes, and the rule for naming the active ruleset directory.
# ABOUTME: Pure functions of values and paths; nothing here reads settings, the database or the environment.
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def _check_json(value: Any) -> None:
    """Raise TypeError for anything that is not a JSON value; the serializer never stringifies."""
    if value is None or isinstance(value, bool | int | float | str):
        return
    if isinstance(value, list | tuple):
        for item in value:
            _check_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be strings, got {type(key).__name__}")
            _check_json(item)
        return
    raise TypeError(f"{type(value).__name__} is not a JSON value")


def canonical_json(value: Any) -> bytes:
    """The canonical JSON text of `value` as UTF-8 bytes.

    Keys are sorted, there is no whitespace between tokens, and non-ASCII text is written as
    UTF-8, not as `\\u` escapes. A float is written as Python's shortest text that reads back
    equal, so `1` and `1.0` are different texts. NaN and the infinities raise ValueError.
    A set, a datetime, bytes or any other non-JSON value, and a non-string key, raise TypeError.
    A tuple is a list.
    """
    _check_json(value)
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_json(value: Any) -> str:
    """SHA-256 hex digest of the canonical JSON of `value`."""
    return sha256_hex(canonical_json(value))


def plan_hash(plan: Mapping[str, Any]) -> str:
    """The plan hash: the hash of the action plan as a JSON mapping."""
    return hash_json(dict(plan))


def payload_hash(recipient: str, subject: str, body: str) -> str:
    """The payload hash: the hash of `{recipient, subject, body}`."""
    return hash_json({"recipient": recipient, "subject": subject, "body": body})


def is_unhashed(path: Path) -> bool:
    """Compiled files (`__pycache__`, `*.pyc`), hidden files and directories (a path part
    starting with `.`) and editor leftovers (`*~`, `*.swp`) are never hashed, so a stray file
    on one machine cannot make a digest that a fresh clone cannot reproduce.
    """
    return (
        "__pycache__" in path.parts
        or path.suffix in (".pyc", ".swp")
        or path.name.endswith("~")
        or any(part.startswith(".") for part in path.parts)
    )


def file_entries(root: Path, files: Iterable[Path]) -> list[dict[str, str]]:
    """One `{path, sha256}` entry per file, `path` relative to `root` with `/` separators.

    Entries are in the order of that path as a whole string, so neither the operating system's
    separator nor its listing order changes the result. A rename changes an entry.
    """
    entries = [
        {"path": file.relative_to(root).as_posix(), "sha256": sha256_hex(file.read_bytes())}
        for file in files
    ]
    return sorted(entries, key=lambda entry: entry["path"])


def source_files(root: Path) -> list[Path]:
    """Every file under `root` except those `is_unhashed` names."""
    return [p for p in root.rglob("*") if p.is_file() and not is_unhashed(p.relative_to(root))]


def ruleset_hash(directory: Path) -> str:
    """The ruleset hash: every file under `directory`, by relative path and content, in path order."""
    if not directory.is_dir():
        raise FileNotFoundError(f"ruleset directory not found: {directory}")
    return hash_json(file_entries(directory, source_files(directory)))


_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def active_ruleset_dir(active: str | None, rulesets_root: Path, image_data: Path) -> Path:
    """The directory the setting `ruleset.active` names, or the image's rules data when it is unset.

    `active` is a ruleset hash (64 lowercase hex characters, A.4) and names
    `rulesets_root / active`. Any other value raises ValueError.
    """
    if active is None:
        return image_data
    if not _SHA256_HEX.fullmatch(active):
        raise ValueError(f"ruleset.active must be a ruleset hash, got {active!r}")
    return rulesets_root / active
