"""Verify the example submissions load, validate and behave as documented.

Runs each one through the graph and asserts it reaches the outcome its
description promises. If a sample stops matching its label, the demo is
lying — so this is a test, not a script.

Run with:  python -m tests.samples_check
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import samples
from contracts.submission import Submission
from tests.smoke import run as run_graph

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("samples")
log.setLevel(logging.INFO)


# What each sample must demonstrate, as (feasibility outcome, recommendation).
EXPECTED = {
    "prior-auth": ("proceed", "proceed_with_conditions"),
    "medication": ("reject", None),
    "onboarding": ("proceed", "defer"),
}


async def main() -> int:
    failures: list[str] = []

    for entry in samples.list_samples():
        sample_id = entry["id"]
        payload = samples.get_sample(sample_id)
        assert payload is not None

        payload["submission_id"] = f"CHECK-{sample_id}"
        payload["tracking_reference"] = f"CHECK-{sample_id}"

        try:
            submission = Submission.model_validate(payload)
        except Exception as exc:
            failures.append(f"{sample_id}: does not validate — {exc}")
            continue

        pack = await run_graph(submission)
        verdict = (pack.get(8) or {}).get("outcome")
        case = pack.outputs.get("initial_business_case", {})
        recommendation = case.get("recommendation")

        log.info(
            "%-12s %-34s feasibility=%-9s recommendation=%s",
            sample_id,
            entry["label"],
            verdict,
            recommendation or "-",
        )

        want_verdict, want_recommendation = EXPECTED[sample_id]
        if verdict != want_verdict:
            failures.append(
                f"{sample_id}: expected feasibility '{want_verdict}', got '{verdict}'"
            )
        if want_recommendation and recommendation != want_recommendation:
            failures.append(
                f"{sample_id}: expected recommendation "
                f"'{want_recommendation}', got '{recommendation}'"
            )

    if failures:
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("SAMPLES OK — every example behaves as its description claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
