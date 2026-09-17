"""Check that the run summary's step count advances between gates.

The run page header shows "N of 19 steps". If ``run.pack`` is only
refreshed when the workflow yields an output, that number would stay
stale while the run is paused at a gate — the UI would under-report
progress.

Run with:  python -m tests.progress_check
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
log = logging.getLogger("progress")
log.setLevel(logging.INFO)

ANSWERS = {
    "OwnerConfirmationRequest": {"confirmed": True, "confirmed_by": "T"},
    "CoEReviewRequest": {"decision": "approve", "reviewed_by": "T"},
    "CriticalityConfirmationRequest": {"confirmed": True, "confirmed_by": "T"},
    "ArchitectReviewRequest": {"decision": "approve", "reviewed_by": "T"},
}

# What the header should read when each gate is presented.
EXPECTED_AT_GATE = {
    1: 1,   # after step 3
    2: 6,   # after steps 4,5,6,7,8
    3: 10,  # after steps 9,10,11,13 — the criticality gate
    4: 19,  # after the full derivation
}


async def main() -> int:
    transport = httpx.ASGITransport(app=app)
    failures: list[str] = []

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=120
    ) as client:
        payload = (await client.get("/api/samples/prior-auth")).json()
        summary = (await client.post("/api/submissions", json=payload)).json()
        ref = summary["tracking_reference"]

        gate_no = 0
        while summary["awaiting_human"]:
            gate = summary["pending_gates"][0]
            gate_no += 1
            shown = len(summary["steps_completed"])
            expected = EXPECTED_AT_GATE.get(gate_no)

            log.info(
                "gate %d  %-28s header shows %2d steps%s",
                gate_no,
                gate["gate_type"],
                shown,
                f"  (expected {expected})" if expected else "",
            )
            if expected is not None and shown != expected:
                failures.append(
                    f"gate {gate_no} ({gate['gate_type']}): header showed "
                    f"{shown} steps, expected {expected}"
                )

            summary = (
                await client.post(
                    f"/api/runs/{ref}/gates",
                    json={
                        "request_id": gate["request_id"],
                        "payload": ANSWERS[gate["gate_type"]],
                    },
                )
            ).json()

        log.info("final    %-28s %2d steps", summary["status"], len(summary["steps_completed"]))

    if failures:
        log.error("")
        for f in failures:
            log.error("STALE: %s", f)
        log.error("")
        log.error("The run page under-reports progress while paused at a gate.")
        return 1

    log.info("progress reporting OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
