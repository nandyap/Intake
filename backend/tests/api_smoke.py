"""API smoke test — exercises the HTTP surface end to end.

Uses httpx's in-process ASGI transport on the caller's own event loop.
(Starlette's ``TestClient`` runs the app in a worker thread with its own
loop, which deadlocks against the workflow's async execution.)

Run with:  python -m tests.api_smoke
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from server import app
from tests.smoke import make_submission

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("api-smoke")
log.setLevel(logging.INFO)


GATE_ANSWERS = {
    "OwnerConfirmationRequest": {
        "confirmed": True,
        "confirmed_by": "Layla Haddad",
    },
    "CoEReviewRequest": {"decision": "approve", "reviewed_by": "AI CoE"},
    "ArchitectReviewRequest": {
        "decision": "approve",
        "reviewed_by": "Solution Architect",
    },
}


async def main() -> int:
    failures: list[str] = []
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=120
    ) as client:
        health = (await client.get("/api/health")).json()
        log.info(
            "health: mode=%s fail_closed=%s", health["mode"], health["fail_closed"]
        )

        artifacts = (await client.get("/api/artifacts")).json()
        log.info(
            "artifacts: %d total, %d seeds",
            artifacts["total"],
            artifacts["seed_count"],
        )

        payload = make_submission().model_dump(mode="json")
        payload.pop("submission_id")
        payload.pop("tracking_reference")

        response = await client.post("/api/submissions", json=payload)
        if response.status_code != 200:
            log.error(
                "submission rejected %s: %s",
                response.status_code,
                response.text[:400],
            )
            return 1

        summary = response.json()
        ref = summary["tracking_reference"]
        log.info("tracking reference: %s", ref)

        gates = 0
        while summary["awaiting_human"]:
            gate = summary["pending_gates"][0]
            answer = GATE_ANSWERS.get(gate["gate_type"])
            if answer is None:
                failures.append(f"no answer for gate {gate['gate_type']}")
                break
            log.info("gate %d: %s -> answering", gates + 1, gate["gate_type"])
            gates += 1
            summary = (
                await client.post(
                    f"/api/runs/{ref}/gates",
                    json={"request_id": gate["request_id"], "payload": answer},
                )
            ).json()

        log.info("status: %s", summary["status"])
        log.info("steps completed: %s", summary["steps_completed"])
        log.info(
            "recommendation: %s (annual value %s AED)",
            summary["recommendation"],
            f"{summary['annual_value']:,.0f}" if summary["annual_value"] else "n/a",
        )

        timeline = (await client.get(f"/api/runs/{ref}/timeline")).json()
        seeds = sorted(
            {
                a["id"]
                for s in timeline["steps"]
                for a in s["artifacts"]
                if a["is_seed"]
            }
        )
        log.info("timeline steps: %d", len(timeline["steps"]))
        log.info("seed artifacts relied on: %s", seeds)
        log.info("gap flags: %d", len(timeline["gap_flags"]))

        pack = (await client.get(f"/api/runs/{ref}/pack")).json()

    if not pack.get("outputs", {}).get("22"):
        failures.append("design pack has no composed architecture")
    if summary["status"] != "completed":
        failures.append(f"expected completed, got {summary['status']}")
    if gates != 4:
        failures.append(f"expected 4 human gates, saw {gates}")

    if failures:
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("API SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
