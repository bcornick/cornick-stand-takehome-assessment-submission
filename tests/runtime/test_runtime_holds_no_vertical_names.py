# ABOUTME: Tests that no file under src/uwh/runtime/ names an underwriting blocker kind, owner, item kind, status or message kind (section 7).
# ABOUTME: The names are written out here; a second vertical registers its own and the runtime does not change.
import re
from pathlib import Path

import pytest

RUNTIME = Path(__file__).resolve().parents[2] / "src" / "uwh" / "runtime"

UNDERWRITING_NAMES = (
    "underwriter",
    "producer",
    "data_team",
    "no_contact_route",
    "underwriter_review",
    "underwriter_question",
    "producer_reply",
    "received",
    "triaged",
    "in_progress",
    "quote_sent",
    "declined",
    "routine_request",
    "sensitive_request",
    "quote_packet",
    "decline_notice",
)


@pytest.mark.parametrize("path", sorted(RUNTIME.glob("*.py")), ids=lambda p: p.name)
def test_runtime_file_names_no_underwriting_name(path: Path) -> None:
    pattern = re.compile(r"\b(" + "|".join(UNDERWRITING_NAMES) + r")\b")
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert hits == []


def test_the_scan_finds_a_name_where_one_is_written() -> None:
    pattern = re.compile(r"\b(" + "|".join(UNDERWRITING_NAMES) + r")\b")
    assert pattern.search('owner = "producer"')
    assert not pattern.search("reply_received and lead_received")
