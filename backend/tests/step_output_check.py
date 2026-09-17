"""Every completed step must expose its raw output.

The design pack is curated: it reads as a document and omits the steps
that do not belong in one. That made four agentic steps — 4, 9, 10 and
14 — invisible in the interface, which reads as though they did not run.

This check asserts the raw-output endpoint covers *every* step the run
completed, not just the ones the pack renders.
"""

import asyncio
import logging
import sys

import httpx

from server import app

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-24s %(message)s")
log = logging.getLogger("step-output")
log.setLevel(logging.INFO)

ANSWERS = {
    "OwnerConfirmationRequest": {"confirmed": True, "confirmed_by": "T"},
    "CoEReviewRequest": {"decision": "approve", "reviewed_by": "T"},
    "CriticalityConfirmationRequest": {"confirmed": True, "confirmed_by": "T"},
    "ArchitectReviewRequest": {"decision": "approve", "reviewed_by": "T"},
}

ENVELOPE_FIELDS = {
    "step",
    "tier",
    "performed_by",
    "artifacts_consulted",
    "gap_flags",
    "requires_input",
    "produced_at",
    "is_stub",
}

# The steps the curated design pack never renders. These are the reason
# this endpoint exists.
PREVIOUSLY_INVISIBLE = [4, 9, 10, 14]


async def main() -> int:
    failures: list[str] = []
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=180
    ) as client:
        payload = (await client.get("/api/samples/prior-auth")).json()
        summary = (await client.post("/api/submissions", json=payload)).json()
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

        completed = summary["steps_completed"]
        log.info("run %s completed %d steps", ref, len(completed))

        # -- every completed step must be retrievable ----------------------
        for step in completed:
            res = await client.get(f"/api/runs/{ref}/steps/{step}")
            if res.status_code != 200:
                failures.append(f"step {step}: HTTP {res.status_code}")
                continue

            body = res.json()
            envelope = body.get("envelope", {})
            payload_keys = set(body.get("payload", {}))

            missing = ENVELOPE_FIELDS - set(envelope)
            if missing:
                failures.append(f"step {step}: envelope missing {sorted(missing)}")

            leaked = payload_keys & ENVELOPE_FIELDS
            if leaked:
                failures.append(
                    f"step {step}: envelope fields leaked into payload {sorted(leaked)}"
                )

            if not payload_keys:
                failures.append(f"step {step}: payload is empty")

            marker = " [stub]" if envelope.get("is_stub") else ""
            log.info(
                "  step %-2d %-28s %d field(s)%s",
                step,
                envelope.get("performed_by", "?"),
                len(payload_keys),
                marker,
            )

        # -- the steps the design pack never showed ------------------------
        for step in PREVIOUSLY_INVISIBLE:
            if step not in completed:
                failures.append(f"step {step} did not run at all")
                continue
            res = await client.get(f"/api/runs/{ref}/steps/{step}")
            if res.status_code != 200 or not res.json().get("payload"):
                failures.append(
                    f"step {step} is still invisible — no output exposed"
                )

        # -- a step that did not run must 404, not return an empty shell ---
        res = await client.get(f"/api/runs/{ref}/steps/12")
        if res.status_code != 404:
            failures.append(
                f"deferred step 12 returned HTTP {res.status_code}, expected 404"
            )
        else:
            log.info("deferred step 12 correctly returns 404")

        res = await client.get("/api/runs/M42-INT-NOSUCH/steps/3")
        if res.status_code != 404:
            failures.append(
                f"unknown run returned HTTP {res.status_code}, expected 404"
            )

    if failures:
        log.error("")
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("")
    log.info("every completed step exposes its output")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
