"""Verify the demo surface: sample listing, sample submission, design pack.

Run with:  python -m tests.demo_check
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from server import app

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("demo")
log.setLevel(logging.INFO)

ANSWERS = {
    "OwnerConfirmationRequest": {"confirmed": True, "confirmed_by": "Demo"},
    "CoEReviewRequest": {"decision": "approve", "reviewed_by": "Demo"},
    "CriticalityConfirmationRequest": {"confirmed": True, "confirmed_by": "Demo"},
    "ArchitectReviewRequest": {"decision": "approve", "reviewed_by": "Demo"},
}


async def main() -> int:
    failures: list[str] = []
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=120
    ) as client:
        listing = (await client.get("/api/samples")).json()["samples"]
        log.info("samples offered: %d", len(listing))
        for s in listing:
            log.info("  %-12s %s", s["id"], s["label"])
        if len(listing) != 3:
            failures.append(f"expected 3 samples, got {len(listing)}")

        payload = (await client.get("/api/samples/prior-auth")).json()
        response = await client.post("/api/submissions", json=payload)
        if response.status_code != 200:
            log.error("submission failed: %s", response.text[:300])
            return 1

        summary = response.json()
        ref = summary["tracking_reference"]

        while summary["awaiting_human"]:
            gate = summary["pending_gates"][0]
            summary = (
                await client.post(
                    f"/api/runs/{ref}/gates",
                    json={
                        "request_id": gate["request_id"],
                        "payload": ANSWERS[gate["gate_type"]],
                    },
                )
            ).json()

        design = (await client.get(f"/api/runs/{ref}/design")).json()

    log.info("")
    log.info("design pack for %s", ref)
    log.info("  complete          : %s", design["is_complete"])
    log.info("  recommendation    : %s", design["business_case"].get("recommendation"))
    log.info("  feasibility       : %s", design["gates"]["feasibility"]["outcome"])
    log.info("  rules evaluated   : %d", len(design["gates"]["feasibility"]["rules"]))
    log.info("  workflow steps    : %d", len(design["workflow"]["nodes"]))
    log.info("  controls derived  : %d", len(design["controls"]))
    log.info("  build surface     : %s", design["architecture"]["build_surface"])
    log.info("  components        : %d", len(design["architecture"]["components"]))
    log.info("  gap flags         : %d", len(design["gap_flags"]))

    if not design["is_complete"]:
        failures.append("design pack is not complete")
    if not design["controls"]:
        failures.append("no controls derived")
    if not design["architecture"]["build_surface"]:
        failures.append("no build surface selected")
    if not design["gates"]["feasibility"]["rules"]:
        failures.append("feasibility audit trail is empty")

    if failures:
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("")
    log.info("DEMO SURFACE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
