"""Initial business case — Appendix B, S and C buckets only.

This answers the sponsor's stage 2: "The analysis reports the immediate
marginal value."  It runs *before* any architecture exists, which is
precisely why it is restricted to the survey-direct (S) and calculated (C)
buckets.

Build cost is architecture-derived (bucket A), so ROI and payback are
structurally impossible here and are returned as ``None`` — never
estimated.  That is the no-fabrication rule, enforced by construction
rather than by discipline.

All arithmetic is deterministic Python.  No model is involved.
"""

from __future__ import annotations

import logging

from contracts.business_case import (
    BusinessCaseLine,
    CostAnchors,
    InitialBusinessCase,
    ProvenanceBucket,
    Recommendation,
    RolePosition,
)
from contracts.envelope import DeterminismTier, RequiresInput
from contracts.submission import DataReadiness, OrgUnit, Submission
from knowledge.retrieval import get_store

logger = logging.getLogger(__name__)

STEP = 8  # runs alongside the feasibility gate, before the CoE review
ARTIFACT_ID = "cost-anchors"
WEEKS_PER_YEAR = 52
MINUTES_PER_HOUR = 60


def _load_anchors() -> tuple[CostAnchors, float, object]:
    """Resolve the cost anchor sheet. Fail-closed by design."""
    artifact = get_store().resolve(ARTIFACT_ID)
    content = artifact.content
    rates = content["fully_loaded_hourly_rate"]
    errors = content["cost_per_error"]

    anchors = CostAnchors(
        version=f"{content['artifact_id']}@{content['version']}",
        currency=content.get("currency", "AED"),
        hourly_rate_doctor=float(rates["doctor"]),
        hourly_rate_nurse=float(rates["nurse"]),
        hourly_rate_admin=float(rates["admin"]),
        cost_per_error_clinical=float(errors["clinical"]),
        cost_per_error_operational=float(errors["operational"]),
        annual_run_cost_ratio=float(content["annual_run_cost_ratio"]),
        not_digital_discount=float(content["not_digital_discount"]),
    )
    reduction_pct = float(content["default_error_reduction_pct"]["value"])
    return anchors, reduction_pct, artifact.ref


def _positions(
    submission: Submission, anchors: CostAnchors
) -> tuple[list[RolePosition], float | None, bool]:
    """Compute per-role annual effort, cost and saving from the Q17 table.

    Returns the positions, the total annual operational saving (None when
    nothing could be computed) and whether any row was incomplete.
    """
    positions: list[RolePosition] = []
    total_saving = 0.0
    any_computed = False
    any_missing = False

    for row in submission.q17_effort_table:
        rate = anchors.hourly_rate(row.role_band.value)
        missing: list[str] = []
        if row.current_minutes is None:
            missing.append("current_minutes")
        if row.expected_minutes is None:
            missing.append("expected_minutes")

        position = RolePosition(
            role=row.role,
            role_band=row.role_band.value,
            headcount=row.headcount,
            requires_input=bool(missing),
            missing_fields=missing,
        )

        if row.current_minutes is not None:
            # annual_hours = headcount * freq/wk * current_min * 52 / 60
            position.annual_hours = (
                row.headcount
                * row.frequency_per_week
                * row.current_minutes
                * WEEKS_PER_YEAR
                / MINUTES_PER_HOUR
            )
            position.annual_cost = position.annual_hours * rate

        if row.current_minutes is not None and row.expected_minutes is not None:
            saved_minutes = max(row.current_minutes - row.expected_minutes, 0.0)
            saved_hours = (
                row.headcount
                * row.frequency_per_week
                * saved_minutes
                * WEEKS_PER_YEAR
                / MINUTES_PER_HOUR
            )
            position.annual_saving = saved_hours * rate
            total_saving += position.annual_saving
            any_computed = True

        any_missing = any_missing or bool(missing)
        positions.append(position)

    return positions, (total_saving if any_computed else None), any_missing


def _quality_saving(
    submission: Submission, anchors: CostAnchors, reduction_pct: float
) -> tuple[float | None, str]:
    """Annual quality saving, or None with a reason when inputs are absent."""
    rate = submission.q18_error_rate.midpoint
    if rate is None:
        return None, "Q18 error rate is Unknown — error volume cannot be derived."
    if submission.q16_annual_volume is None:
        return None, "Annual process volume was not provided (Q16)."

    cost_per_error = (
        anchors.cost_per_error_clinical
        if submission.q0_org_unit is OrgUnit.CLINICAL
        else anchors.cost_per_error_operational
    )
    errors_today = submission.q16_annual_volume * rate
    return errors_today * reduction_pct * cost_per_error, ""


def build(submission: Submission) -> InitialBusinessCase:
    """Produce the initial (pre-architecture) business case."""
    anchors, reduction_pct, artifact_ref = _load_anchors()

    positions, operational_saving, positions_incomplete = _positions(
        submission, anchors
    )
    quality_saving, quality_reason = _quality_saving(
        submission, anchors, reduction_pct
    )

    lines: list[BusinessCaseLine] = []
    requires_input: list[RequiresInput] = []
    gate_conditions: list[str] = []

    # -- operational saving (C) -------------------------------------------
    discount_applied = submission.q24_data_readiness is not DataReadiness.FULLY
    adjusted_operational = operational_saving
    if operational_saving is not None and discount_applied:
        # Appendix B: 70% discount applied when data is not fully digital.
        adjusted_operational = operational_saving * anchors.not_digital_discount
        gate_conditions.append(
            f"Year-1 operational saving discounted to "
            f"{anchors.not_digital_discount:.0%} because data is not fully "
            f"digital (Q24 = {submission.q24_data_readiness.value})."
        )

    lines.append(
        BusinessCaseLine(
            label="Annual operational saving",
            value=adjusted_operational,
            unit=anchors.currency,
            bucket=ProvenanceBucket.CALCULATED,
            formula="sum(headcount x freq/wk x (current_min - expected_min)) x 52 / 60 x hourly_rate",
            source=f"Q17 effort table; anchors {anchors.version}",
            requires_input=operational_saving is None,
        )
    )
    if operational_saving is None:
        requires_input.append(
            RequiresInput(
                field_name="q17_effort_table",
                reason="No effort row carried both current and expected minutes.",
                gate_condition="Complete the Q17 effort table before the business case can quantify time saving.",
            )
        )
    elif positions_incomplete:
        gate_conditions.append(
            "Some Q17 effort rows were incomplete; the operational saving "
            "covers only the rows that carried both current and expected minutes."
        )

    # -- quality saving (C) ------------------------------------------------
    lines.append(
        BusinessCaseLine(
            label="Annual quality saving",
            value=quality_saving,
            unit=anchors.currency,
            bucket=ProvenanceBucket.CALCULATED,
            formula="annual_volume x error_rate x reduction_pct x cost_per_error",
            source=f"Q16, Q18, Q0; anchors {anchors.version}",
            requires_input=quality_saving is None,
        )
    )
    if quality_saving is None:
        requires_input.append(
            RequiresInput(
                field_name="q18_error_rate",
                reason=quality_reason,
                gate_condition="Provide the annual process volume and a known error rate to quantify quality saving.",
            )
        )

    # -- submitter's own estimate (S) --------------------------------------
    lines.append(
        BusinessCaseLine(
            label="Submitter-estimated annual benefit",
            value=submission.q28_estimated_annual_benefit_aed,
            unit=anchors.currency,
            bucket=ProvenanceBucket.SURVEY_DIRECT,
            source="Q28",
            requires_input=submission.q28_estimated_annual_benefit_aed is None,
        )
    )

    # -- build cost is bucket A — structurally absent at this stage --------
    lines.append(
        BusinessCaseLine(
            label="Build cost",
            value=None,
            unit=anchors.currency,
            bucket=ProvenanceBucket.ARCHITECTURE_DERIVED,
            source="Requires steps 20-22 (component selection and composition)",
            requires_input=True,
        )
    )
    gate_conditions.append(
        "Build cost, ROI and payback are architecture-derived and are not "
        "produced at the analysis stage. They follow the full business case."
    )

    computed = [v for v in (adjusted_operational, quality_saving) if v is not None]
    annual_value = sum(computed) if computed else None

    # -- recommendation ----------------------------------------------------
    # v2.5: a case carrying placeholders can recommend
    # proceed-with-conditions, never proceed.
    if annual_value is None:
        recommendation = Recommendation.DEFER
        narrative = (
            "No quantified benefit could be derived from the submission. "
            "The case cannot be assessed on value until the effort table or "
            "the error-rate inputs are completed."
        )
    elif requires_input or gate_conditions:
        recommendation = Recommendation.PROCEED_WITH_CONDITIONS
        narrative = (
            f"Quantified annual value of {annual_value:,.0f} {anchors.currency} "
            f"from {len(computed)} of 2 benefit drivers. Conditions remain "
            f"outstanding, so this is proceed-with-conditions."
        )
    else:
        recommendation = Recommendation.PROCEED
        narrative = (
            f"Quantified annual value of {annual_value:,.0f} {anchors.currency} "
            "with no outstanding input conditions."
        )

    logger.info(
        "Initial business case for %s: %s (annual value=%s)",
        submission.tracking_reference,
        recommendation.value,
        annual_value,
    )

    return InitialBusinessCase(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Business case service (initial, S+C)",
        artifacts_consulted=[artifact_ref],
        requires_input=requires_input,
        anchors_version=anchors.version,
        currency=anchors.currency,
        positions=positions,
        lines=lines,
        annual_operational_saving=adjusted_operational,
        annual_quality_saving=quality_saving,
        annual_value=annual_value,
        roi_multiple=None,
        payback_months=None,
        recommendation=recommendation,
        gate_conditions=gate_conditions,
        narrative=narrative,
    )
