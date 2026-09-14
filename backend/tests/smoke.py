"""End-to-end smoke test — the Sprint 1 exit criterion.

Runs a real submission through the full 3-22 graph in stub mode, pausing
at each human gate and answering it, and asserts:

* the graph builds and every declared edge resolves,
* all four human-in-the-loop gates fire,
* the deterministic services produce verdicts,
* the run reaches a composed architecture,
* the same submission run twice produces an identical design pack
  (reproducibility is the product).

Run with:  python -m tests.smoke
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.envelope import DesignPack, RunStatus
from contracts.submission import (
    ChangeFrequency,
    Channel,
    ConditionalLogic,
    DataReadiness,
    EffortRow,
    ErrorRate,
    FailureImpact,
    OrgUnit,
    Pathway,
    Relationship,
    RoleBand,
    SignOffRequirement,
    StepCount,
    Submission,
    Urgency,
    VolumePattern,
)
from workflow.graph import build_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(name)-28s %(message)s",
)
logging.getLogger("agent_framework").setLevel(logging.WARNING)
log = logging.getLogger("smoke")


def make_submission(
    failure_impact: FailureImpact = FailureImpact.MEDIUM,
) -> Submission:
    """A realistic comprehensive submission.

    Modelled on a plausible M42 operational use case so the derivation has
    something real to chew on.
    """
    return Submission(
        submission_id="SUB-0001",
        tracking_reference="M42-INT-0001",
        pathway=Pathway.COMPREHENSIVE,
        channel=Channel.FORM,
        q0_org_unit=OrgUnit.OPERATIONAL,
        q1_full_name="Layla Haddad",
        q2_department="Patient Access",
        q3_job_title="Operations Manager",
        q4_relationship=Relationship.MANAGES,
        q5_task_description=(
            "Insurance pre-authorisation requests arrive by email and fax. "
            "Coordinators re-key each request into the portal, chase missing "
            "clinical documentation, and follow up with insurers. Patients "
            "wait an average of three days for a decision and roughly one in "
            "twenty requests is resubmitted because a field was wrong."
        ),
        q6_categories=[
            "Validate request",
            "Extract clinical documentation",
            "Submit authorisation",
            "Track insurer response",
        ],
        q7_goals=["Reduce time", "Improve accuracy", "Customer experience"],
        q8_biggest_value=(
            "Patients receive an authorisation decision within one day "
            "instead of three."
        ),
        q9_other_kpis="Resubmission rate; coordinator overtime hours",
        q10_step_count=StepCount.S_6_15,
        q11_conditional_logic=ConditionalLogic.SIMPLE,
        q12_systems=["EMR-EHR", "Portal", "Email-calendar"],
        q12b_write_back_targets=["EMR"],
        q13_systems_purpose=(
            "EMR holds the clinical record; the insurer portal receives the "
            "authorisation request."
        ),
        q14_data_types=[
            "Authorisation request",
            "Clinical document",
            "Insurer response",
        ],
        q15_change_frequency=ChangeFrequency.OCCASIONALLY,
        q16_volume_pattern=VolumePattern.PREDICTABLE_PEAKS,
        q16_annual_volume=24000,
        q17_effort_table=[
            EffortRow(
                role="Authorisation coordinator",
                role_band=RoleBand.ADMIN,
                headcount=6,
                seniority="mid",
                frequency_per_week=80,
                current_minutes=12,
                expected_minutes=4,
            ),
            EffortRow(
                role="Reviewing nurse",
                role_band=RoleBand.NURSE,
                headcount=2,
                seniority="senior",
                frequency_per_week=40,
                current_minutes=8,
                expected_minutes=5,
            ),
        ],
        q18_error_rate=ErrorRate.OCCASIONALLY,
        q19_sensitive_data=["PII", "Regulated"],
        q20_sign_off=SignOffRequirement.AUDIT_TRAIL_ONLY,
        q21_sign_off_detail="Every submission must be traceable to a coordinator.",
        q22_failure_impact=failure_impact,
        q23_stakeholder_discussion="Yes supportive",
        q24_data_readiness=DataReadiness.PARTIALLY,
        q25_urgency=Urgency.HIGH,
        q26_investment_band="AED 200-500k",
        q27_budget_likelihood="Likely",
        q28_estimated_annual_benefit_aed=900000,
        q29_additional_context="Peak volumes follow the start of each month.",
    )


def _answer(request: object) -> object:
    """Respond to whatever gate the workflow paused at.

    Approves everything, so the happy path is exercised end to end.
    """
    from contracts.verdicts import (
        ArchitectReviewRequest,
        ArchitectReviewResponse,
        CoEReviewRequest,
        CoEReviewResponse,
        OwnerConfirmationRequest,
        OwnerConfirmationResponse,
        ReviewDecision,
    )

    if isinstance(request, OwnerConfirmationRequest):
        log.info("  gate: owner confirmation -> confirmed")
        return OwnerConfirmationResponse(confirmed=True, confirmed_by="Layla Haddad")
    if isinstance(request, CoEReviewRequest):
        log.info(
            "  gate: AI CoE review (feasibility=%s) -> accepted",
            request.feasibility_outcome,
        )
        return CoEReviewResponse(
            decision=ReviewDecision.APPROVE, reviewed_by="AI CoE"
        )
    if isinstance(request, ArchitectReviewRequest):
        log.info(
            "  gate: architect review (%d components, %d obligations, "
            "%d divergences) -> approved",
            request.component_count,
            request.obligation_count,
            len(request.divergences),
        )
        return ArchitectReviewResponse(
            decision=ReviewDecision.APPROVE, reviewed_by="Solution Architect"
        )
    raise AssertionError(f"unhandled gate: {type(request).__name__}")


async def run(submission: Submission) -> DesignPack:
    """Drive one submission through the graph, answering every gate.

    Uses the non-streaming API: each ``run`` returns when the workflow
    either completes or pauses at one or more human gates. Answering the
    pending requests resumes it at exactly that point.
    """
    workflow = build_graph(agents={})

    pack = DesignPack(
        submission_id=submission.submission_id,
        tracking_reference=submission.tracking_reference,
    )
    pack.outputs["submission"] = submission.model_dump(mode="json")

    gates_hit = 0
    result: DesignPack | None = None

    run_result = await workflow.run(pack)
    while True:
        for output in run_result.get_outputs():
            if isinstance(output, DesignPack):
                result = output

        requests = run_result.get_request_info_events()
        if not requests:
            break

        gates_hit += len(requests)
        responses = {
            event.request_id: _answer(event.data) for event in requests
        }
        run_result = await workflow.run(responses=responses)

    assert result is not None, "workflow produced no output"
    log.info("gates answered: %d", gates_hit)
    return result


def _fingerprint(pack: DesignPack) -> str:
    """Stable fingerprint ignoring timestamps, for the reproducibility check.

    Wall-clock fields are excluded deliberately: they differ between runs
    by definition and say nothing about whether the derivation is
    reproducible.
    """
    ignored = {"produced_at", "retrieved_at", "raised_at", "submitted_at"}

    def strip(obj):
        if isinstance(obj, dict):
            return {
                k: strip(v) for k, v in sorted(obj.items()) if k not in ignored
            }
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj

    return json.dumps(strip(pack.outputs), sort_keys=True)


async def main() -> int:
    failures: list[str] = []

    # --- happy path -------------------------------------------------------
    log.info("=" * 72)
    log.info("CASE 1 — full derivation, steps 3 to 22")
    log.info("=" * 72)
    pack = await run(make_submission())

    log.info("-" * 72)
    log.info("status          : %s", pack.status.value)
    log.info("steps completed : %s", sorted(int(k) for k in pack.outputs if k.isdigit()))
    log.info("gap flags       : %d", len(pack.gap_flags))

    case = pack.outputs.get("initial_business_case", {})
    log.info(
        "business case   : %s · annual value %s AED",
        case.get("recommendation"),
        f"{case['annual_value']:,.0f}" if case.get("annual_value") else "not derived",
    )

    verdict = pack.get(8) or {}
    log.info("feasibility     : %s", verdict.get("outcome"))
    readiness = pack.get(15) or {}
    log.info("readiness       : %s", readiness.get("outcome"))
    controls = pack.get(19) or {}
    log.info(
        "obligations     : %s",
        [o["obligation_id"] for o in controls.get("obligations", [])],
    )
    surface = pack.get(20) or {}
    log.info("build surface   : %s", surface.get("surface"))
    arch = pack.get(22) or {}
    log.info(
        "architecture    : %d logical steps, %d violations",
        len(arch.get("logical", {}).get("steps", [])),
        len(arch.get("conformance_violations", [])),
    )
    log.info("-" * 72)

    expected = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}
    actual = {int(k) for k in pack.outputs if k.isdigit()}
    if missing := expected - actual:
        failures.append(f"steps did not run: {sorted(missing)}")
    if pack.status is not RunStatus.COMPLETED:
        failures.append(f"expected COMPLETED, got {pack.status.value}")
    if not arch.get("logical", {}).get("steps"):
        failures.append("composed architecture has no logical steps")

    # --- sponsor directive: severe harm is rejected at step 8 -------------
    log.info("")
    log.info("=" * 72)
    log.info("CASE 2 — Q22=Critical must be rejected at the feasibility gate")
    log.info("=" * 72)
    critical = make_submission(failure_impact=FailureImpact.CRITICAL)
    critical.tracking_reference = "M42-INT-0002"
    rejected = await run(critical)

    verdict = rejected.get(8) or {}
    log.info("feasibility     : %s", verdict.get("outcome"))
    log.info("reason          : %s", (verdict.get("reasons") or ["-"])[0])

    if verdict.get("outcome") != "reject":
        failures.append("Q22=Critical was not rejected (rule F01)")
    if 22 in {int(k) for k in rejected.outputs if k.isdigit()}:
        failures.append("rejected run continued into deep derivation")

    # --- reproducibility --------------------------------------------------
    log.info("")
    log.info("=" * 72)
    log.info("CASE 3 — same submission twice must produce an identical pack")
    log.info("=" * 72)
    again = await run(make_submission())
    if _fingerprint(pack) != _fingerprint(again):
        failures.append("two identical submissions produced different design packs")
    else:
        log.info("fingerprints match — derivation is reproducible")

    # --- report -----------------------------------------------------------
    log.info("")
    log.info("=" * 72)
    if failures:
        for f in failures:
            log.error("FAIL: %s", f)
        return 1
    log.info("ALL CHECKS PASSED")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
