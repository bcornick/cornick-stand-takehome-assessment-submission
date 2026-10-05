# ABOUTME: The stand-in providers of 9.4: a lookup for each system-owned field, answered from the captured world fixture of the seed and checked first for the inputs it needs.
# ABOUTME: A lead the fixture has no entry for, or whose submitted fields differ from the captured ones, gets `unavailable`; no value is made up.
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from uwh.providers.models import ProviderResult

DATA_DIR = Path(__file__).parent / "data"

_ADDRESS = ["street_address", "city", "state", "zip"]
# Field -> (the facts the lookup needs, the real source it stands in for), from the table in 9.4.
_LOOKUPS: dict[str, tuple[list[str], str]] = {
    "broker_tier": ([], "Stand's distribution systems"),
    "has_primary_policy_with_stand": ([], "Stand's policy systems"),
    "replacement_cost": (_ADDRESS, "replacement cost estimator"),
    "protection_class": (_ADDRESS, "Verisk LOCATION PPC"),
    "kyc_score": (["first_name", "last_name", "insured_dob"], "identity and adverse-media screen"),
    "p_f": (_ADDRESS, "Stand's fire model"),
    "slope_angle_deg": (_ADDRESS, "Stand's geospatial data"),
    "min_distance_to_neighbor_ft": (_ADDRESS, "Stand's geospatial data"),
    "vegetation_clearance": (_ADDRESS, "Stand's geospatial data"),
    "road_access": (_ADDRESS, "Stand's geospatial data"),
}


class StandInProviders:
    def __init__(self, world: Mapping[str, Any]) -> None:
        self._leads: Mapping[str, Any] = world.get("leads", {})

    @classmethod
    def for_seed(cls, seed: int) -> "StandInProviders":
        """The providers of the seed's world fixture; with no fixture for the seed every lookup is `unavailable`."""
        path = DATA_DIR / f"world-{seed}.json"
        return cls(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})

    def lookup(
        self,
        field: str,
        lead_id: str,
        fingerprint: str,
        facts: Mapping[str, JsonValue],
        fetched_at: str,
    ) -> ProviderResult:
        """The result for `field`. The input check runs first, so `blocked` outranks `not_found`.
        `fingerprint` is the hash of the lead's submitted fields, which the entry must carry."""
        inputs, source = _LOOKUPS[field]
        missing = [name for name in inputs if name not in facts]
        entry = self._leads.get(lead_id)
        if missing:
            return ProviderResult(
                status="blocked",
                value=None,
                source=source,
                fetched_at=fetched_at,
                missing_inputs=missing,
            )
        if entry is None or entry["fingerprint"] != fingerprint:
            return ProviderResult(
                status="unavailable",
                value=None,
                source=source,
                fetched_at=fetched_at,
            )
        answer = entry["provider_values"][field]
        return ProviderResult(
            status=answer["status"],
            value=answer["value"],
            source=source,
            fetched_at=fetched_at,
        )
