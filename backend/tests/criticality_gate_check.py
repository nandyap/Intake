"""Step 13 criticality gate — the class must be confirmed by a human.

Two things are asserted here, and the second is the one that matters.

1. The gate is presented, and confirming it sets ``architect_confirmed``.
2. Readiness rule R02 *fails closed* when it is not set.

Before the gate existed, R02 read ``not architect_confirmed and not
class_per_branch``. The agent stub always populates ``class_per_branch``,
so the second clause was always false and R02 could never fire — the rule
that exists to catch an unconfirmed criticality class was unable to catch
one. That is why this check asserts the failing case explicitly rather
than only walking the happy path.
"""

import asyncio
import logging
import sys

import httpx

from contracts.steps import (
    CriticalityBand,
    CriticalityConfirmation,
    OntologyDelta,
    OutcomeAssertions,
    QualityAttributes,
    WorkflowGraph,
)
from contracts.envelope import DeterminismTier
from deterministic import readiness
from server import app

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-28s %(message)s")
log = logging.getLogger("criticality-gate")
log.setLevel(logging.INFO)

ANSWERS = {
    "OwnerConfirmationRequest": {"confirmed": True, "confirmed_by": "T"},
    "CoEReviewRequest": {"decision": "approve", "reviewed_by": "T"},
    "ArchitectReviewRequest": {"decision": "approve", "reviewed_by": "T"},
}


def _confirmation(*, confirmed: bool) -> CriticalityConfirmation:
    """A criticality confirmation with a class proposed but not confirmed."""
    return CriticalityConfirmation(
        step=13,
        tier=DeterminismTier.D1,
        performed_by="Risk Officer",
        is_homogeneous=True,
        class_per_branch={"default": CriticalityBand.SIGNIFICANT},
        architect_confirmed=confirmed,
    )


def _r02(confirmed: bool) -> bool:
    """Run the readiness service and report whether R02 triggered."""
    verdict = readiness.evaluate(
        workflow=WorkflowGraph(
            step=11,
            tier=DeterminismTier.D1,
            performed_by="Process Analyst",
            nodes=[
                {
                    "node_id": "n1",
                    "activity_verb": "receive",
                    "performing_element": "intake service",
                }
            ],
        ),
        criticality=_confirmation(confirmed=confirmed),
        assertions=OutcomeAssertions(
            step=14, tier=DeterminismTier.D1, performed_by="Product Owner"
        ),
        quality=QualityAttributes(
            step=9, tier=DeterminismTier.D1, performed_by="Solution Architect"
        ),
        ontology=OntologyDelta(
            step=10, tier=DeterminismTier.D1, performed_by="Ontologist"
        ),
    )
    rule = next(r for r in verdict.rules_evaluated if r.rule_id == "R02")
    return rule.triggered


async def main() -> int:
    failures: list[str] = []

    # -- 1. R02 must fail closed on an unconfirmed class -------------------
    if not _r02(confirmed=False):
        failures.append(
            "R02 did not trigger for an unconfirmed criticality class — "
            "control rigour would be derived from an unreviewed judgement"
        )
    else:
        log.info("R02 triggers when architect_confirmed is False  (fail closed)")

    if _r02(confirmed=True):
        failures.append("R02 triggered even though the architect confirmed")
    else:
        log.info("R02 clear when architect_confirmed is True")

    # -- 2. The gate is presented and sets the flag ------------------------
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=180
    ) as client:
        payload = (await client.get("/api/samples/prior-auth")).json()
        summary = (await client.post("/api/submissions", json=payload)).json()
        ref = summary["tracking_reference"]

        seen: list[str] = []
        substituted = False

        while summary["awaiting_human"]:
            gate = summary["pending_gates"][0]
            seen.append(gate["gate_type"])

            if gate["gate_type"] == "CriticalityConfirmationRequest":
                proposed = gate["data"]["proposed_class"]
                log.info("criticality gate presented, proposed class %r", proposed)
                # Substitute a different class to prove the override path
                # reaches the pack rather than being silently dropped.
                answer = {
                    "confirmed": True,
                    "confirmed_class": "severe",
                    "confirmed_by": "Solution Architect",
                }
                substituted = proposed != "severe"
            else:
                answer = ANSWERS[gate["gate_type"]]

            summary = (
                await client.post(
                    f"/api/runs/{ref}/gates",
                    json={"request_id": gate["request_id"], "payload": answer},
                )
            ).json()

        pack = (await client.get(f"/api/runs/{ref}/pack")).json()

    if "CriticalityConfirmationRequest" not in seen:
        failures.append("the step 13 criticality gate was never presented")

    step13 = pack.get("outputs", {}).get("13") or {}
    if not step13.get("architect_confirmed"):
        failures.append("architect_confirmed is not set after confirmation")
    else:
        log.info("architect_confirmed set on step 13 output")

    chosen = (step13.get("class_per_branch") or {}).get("default")
    if substituted and chosen != "severe":
        failures.append(
            f"architect substituted 'severe' but the pack carries {chosen!r}"
        )
    else:
        log.info("confirmed class recorded in the pack: %r", chosen)

    verdict = pack.get("outputs", {}).get("15") or {}
    log.info("readiness outcome: %s", verdict.get("outcome"))
    log.info("gates seen: %s", ", ".join(seen))

    if failures:
        log.error("")
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("")
    log.info("criticality gate OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
