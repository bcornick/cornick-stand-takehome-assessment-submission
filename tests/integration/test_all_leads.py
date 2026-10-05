# ABOUTME: Integration test of the ten seed-42 leads against Stand's running leadgen and mailbox containers: one run, then each lead's status, open blockers, the asks of its request and the messages in the producer's mailbox are compared with the first-pass row of the scenario table (5).
# ABOUTME: A start resets the mailbox, which the app container shares; the mailbox is read back through its own listing, as a producer's inbox.
import json
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

import httpx2
import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

REPLY_WAIT = ("producer_reply", None, None)
QUESTION = ("underwriter_question", None, None)
DECLINE_NOTICE_DRAFT = ("underwriter_review", "draft", None)


class FirstPass(NamedTuple):
    blockers: list[tuple[str, str | None, str | None]]  # kind, item kind, cause
    mail: dict[str, int]  # message kind -> how many are in the producer's mailbox
    asked: set[str]  # asks that must be in the request
    not_asked: set[str]  # asks that must not be


# The first-pass row of 5 for each lead.
FIRST_PASS = {
    # A proposed decline: the notice waits and nothing is asked.
    "000": FirstPass([DECLINE_NOTICE_DRAFT], {}, set(), set()),
    # No street address: a routine request that includes it.
    "001": FirstPass([REPLY_WAIT], {"routine_request": 1}, {"street_address"}, set()),
    # KYC 8 and 9: the requests for the missing fields; the liability exclusion is in the plan.
    "002": FirstPass([REPLY_WAIT], {"routine_request": 1}, {"coverage_a", "is_rental"}, set()),
    # The failed fire simulation is one card; the registry asks and the occupancy confirmation go out.
    "003": FirstPass(
        [QUESTION, REPLY_WAIT],
        {"routine_request": 1},
        {"roof_material", "months_unoccupied_in_primary_home"},
        {"willing_to_mitigate", "fire_dept_response_time", "alternative_water_source"},
    ),
    "004": FirstPass([REPLY_WAIT], {"routine_request": 1}, {"no_residents_in_primary_home"}, set()),
    # The missing pool fields and a confirmation; the diving-board answer on the lead is not asked again.
    "005": FirstPass(
        [REPLY_WAIT],
        {"routine_request": 1},
        {"pool_type", "pool_security", "no_residents_in_primary_home"},
        {"pool_has_diving_board_or_slide"},
    ),
    "006": FirstPass(
        [QUESTION, REPLY_WAIT],
        {"routine_request": 1},
        {"roof_material"},
        {"willing_to_mitigate", "pool_security", "pool_has_diving_board_or_slide"},
    ),
    "007": FirstPass([REPLY_WAIT], {"routine_request": 1}, {"zip", "has_animals"}, set()),
    "008": FirstPass(
        [REPLY_WAIT],
        {"routine_request": 1},
        {"property_purchase_date", "electrical_panel_brand"},
        set(),
    ),
    "009": FirstPass([REPLY_WAIT], {"routine_request": 1}, {"acreage"}, set()),
}


def test_a_run_leaves_every_lead_at_a_request_or_an_underwriter_wait(
    host_urls: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.load(
        {
            "UWH_DB": str(tmp_path / "app.db"),
            "RUN_MODE": "replay",
            "SEED": "42",
            "UWH_REGISTRY": str(ROOT / "docs" / "brief" / "field_registry.json"),
            "UWH_RECORDINGS": str(ROOT / "recordings"),
            "UWH_FIXTURE_REPLIES": str(ROOT / "fixtures" / "replies"),
            "LEADGEN_URL": host_urls["leadgen"],
            "MAILBOX_URL": host_urls["mailbox"],
        }
    )

    with TestClient(create_app(settings)) as app:
        assert app.post("/api/run/start?wait=true").status_code == 200

    db = open_store(settings.db_path)
    mismatches: list[str] = []
    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        mailbox = MailboxClient(http)
        for number, expected in FIRST_PASS.items():
            lead_id = f"LEAD-00000042-{number}"
            blockers = open_blockers(db, lead_id)
            sent = mailbox.list_for_lead(lead_id)
            requests = db.execute(
                "SELECT ask_ids_json FROM intents WHERE lead_id = ? AND kind LIKE '%_request'",
                (lead_id,),
            ).fetchall()
            asked = {ask for (ids,) in requests for ask in json.loads(ids)}
            found: dict[str, Any] = {
                "status": db.execute(
                    "SELECT status FROM leads WHERE lead_id = ?", (lead_id,)
                ).fetchone()[0],
                "blockers": sorted((b.kind, b.detail.item_kind, b.detail.cause) for b in blockers),
                "mail": dict(Counter(m["metadata"]["kind"] for m in sent)),
                "asked": expected.asked <= asked,
                "not_asked": not expected.not_asked & asked,
            }
            wanted: dict[str, Any] = {
                "status": "in_progress",
                "blockers": sorted(expected.blockers),
                "mail": expected.mail,
                "asked": True,
                "not_asked": True,
            }
            mismatches += [
                f"{lead_id} {name}: {found[name]!r}, expected {wanted[name]!r}"
                for name in wanted
                if found[name] != wanted[name]
            ]
    assert mismatches == []
