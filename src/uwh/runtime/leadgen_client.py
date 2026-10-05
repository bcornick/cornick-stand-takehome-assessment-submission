# ABOUTME: Synchronous client for Stand's leadgen service: queue, list, fetch and health.
# ABOUTME: It returns parsed JSON and raises on any non-success response.
from typing import Any

import httpx2


class LeadgenClient:
    def __init__(self, http: httpx2.Client) -> None:
        self._http = http

    def post_queue(self, seed: int, count: int = 10) -> dict[str, Any]:
        """Replace the stored queue with `count` leads generated from `seed`."""
        response = self._http.post("/queue", params={"seed": seed, "count": count})
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def list_leads(self) -> list[dict[str, Any]]:
        response = self._http.get("/leads")
        response.raise_for_status()
        result: list[dict[str, Any]] = response.json()
        return result

    def get_lead(self, lead_id: str) -> dict[str, Any]:
        response = self._http.get(f"/leads/{lead_id}")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def healthz(self) -> dict[str, Any]:
        response = self._http.get("/healthz")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
