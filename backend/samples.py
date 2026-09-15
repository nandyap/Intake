"""Example submissions for demonstrations and local testing.

Three cases chosen to show different paths through the derivation:

* ``prior-auth``      proceeds cleanly and reaches a composed architecture
* ``medication``      rejected at the feasibility gate on the severe-harm rule
* ``onboarding``      proceeds but with incomplete effort data, so the
                      business case can only recommend proceed-with-conditions

Loaded by ``GET /api/samples`` and offered in the submit form.
"""

from __future__ import annotations

from typing import Any

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


def _prior_auth() -> Submission:
    """Insurance pre-authorisation. The happy path."""
    return Submission(
        submission_id="SAMPLE-001",
        tracking_reference="SAMPLE-001",
        pathway=Pathway.COMPREHENSIVE,
        channel=Channel.FORM,
        q0_org_unit=OrgUnit.OPERATIONAL,
        q1_full_name="Layla Haddad",
        q2_department="Patient Access",
        q3_job_title="Operations Manager",
        q4_relationship=Relationship.MANAGES,
        q5_task_description=(
            "Insurance pre-authorisation requests arrive by email and fax. "
            "Coordinators re-key each request into the insurer portal, chase "
            "missing clinical documentation, and follow up on responses. "
            "Patients wait an average of three days for a decision and roughly "
            "one in twenty requests is resubmitted because a field was wrong. "
            "The limiting factor is coordinator capacity at month-start peaks."
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
            "The EMR holds the clinical record; the insurer portal receives "
            "the authorisation request."
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
        q22_failure_impact=FailureImpact.MEDIUM,
        q23_stakeholder_discussion="Yes supportive",
        q24_data_readiness=DataReadiness.PARTIALLY,
        q25_urgency=Urgency.HIGH,
        q26_investment_band="AED 200-500k",
        q27_budget_likelihood="Likely",
        q28_estimated_annual_benefit_aed=900000,
        q29_additional_context="Peak volumes follow the start of each month.",
    )


def _medication() -> Submission:
    """Medication dosing. Rejected at step 8 on the severe-harm rule."""
    return Submission(
        submission_id="SAMPLE-002",
        tracking_reference="SAMPLE-002",
        pathway=Pathway.COMPREHENSIVE,
        channel=Channel.FORM,
        q0_org_unit=OrgUnit.CLINICAL,
        q1_full_name="Dr Omar Farouk",
        q2_department="Inpatient Pharmacy",
        q3_job_title="Lead Clinical Pharmacist",
        q4_relationship=Relationship.PERFORMS,
        q5_task_description=(
            "Pharmacists calculate weight-based dosing for paediatric "
            "inpatients and adjust for renal function. Each calculation is "
            "checked by a second pharmacist. The double-check consumes senior "
            "pharmacist time and delays first administration."
        ),
        q6_categories=["Clinical approval review", "Data entry"],
        q7_goals=["Reduce time", "Improve accuracy"],
        q8_biggest_value="First dose administered sooner after prescribing.",
        q9_other_kpis="Time to first administration",
        q10_step_count=StepCount.S_1_5,
        q11_conditional_logic=ConditionalLogic.NESTED,
        q12_systems=["EMR-EHR"],
        q12b_write_back_targets=["EMR"],
        q13_systems_purpose="The EMR holds weight, renal function and the order.",
        q14_data_types=["Structured", "Personal data"],
        q15_change_frequency=ChangeFrequency.RARELY,
        q16_volume_pattern=VolumePattern.CONSISTENT,
        q16_annual_volume=18000,
        q17_effort_table=[
            EffortRow(
                role="Clinical pharmacist",
                role_band=RoleBand.DOCTOR,
                headcount=4,
                seniority="senior",
                frequency_per_week=60,
                current_minutes=9,
                expected_minutes=3,
            ),
        ],
        q18_error_rate=ErrorRate.RARELY,
        q19_sensitive_data=["PII", "Regulated"],
        q20_sign_off=SignOffRequirement.MANDATORY_APPROVAL,
        q21_sign_off_detail="Second-pharmacist verification is mandatory.",
        # The decisive field: an error here causes severe or permanent harm.
        q22_failure_impact=FailureImpact.CRITICAL,
        q23_stakeholder_discussion="Yes supportive",
        q24_data_readiness=DataReadiness.FULLY,
        q25_urgency=Urgency.CRITICAL,
        q26_investment_band="AED 200-500k",
        q27_budget_likelihood="Very likely",
        q28_estimated_annual_benefit_aed=1200000,
        q29_additional_context=(
            "Clinically valuable, but an incorrect paediatric dose can cause "
            "irreversible harm."
        ),
    )


def _onboarding() -> Submission:
    """Supplier onboarding. Proceeds, but with incomplete effort data."""
    return Submission(
        submission_id="SAMPLE-003",
        tracking_reference="SAMPLE-003",
        pathway=Pathway.COMPREHENSIVE,
        channel=Channel.FORM,
        q0_org_unit=OrgUnit.OPERATIONAL,
        q1_full_name="Priya Raghavan",
        q2_department="Procurement",
        q3_job_title="Supplier Onboarding Lead",
        q4_relationship=Relationship.MANAGES,
        q5_task_description=(
            "New suppliers submit registration packs as PDFs and spreadsheets. "
            "Analysts check completeness, verify trade licences against the "
            "registry, and create the vendor record in the ERP. Packs are "
            "returned two or three times before they are complete."
        ),
        q6_categories=["Document processing", "Data entry", "Comms"],
        q7_goals=["Reduce time", "Reduce cost", "Compliance"],
        q8_biggest_value="Suppliers are onboarded in days rather than weeks.",
        q9_other_kpis="Rework loops per supplier",
        q10_step_count=StepCount.S_16_30,
        q11_conditional_logic=ConditionalLogic.NESTED,
        q12_systems=["ERP", "PDF-DMS", "Email-calendar", "External site"],
        q12b_write_back_targets=["ERP"],
        q13_systems_purpose="The ERP holds the vendor master record.",
        q14_data_types=["Documents", "Structured", "Financial"],
        q15_change_frequency=ChangeFrequency.FREQUENTLY,
        q16_volume_pattern=VolumePattern.HIGHLY_VARIABLE,
        # No annual volume, and the expected time is unknown — so the
        # business case reports "requires input" rather than estimating.
        q16_annual_volume=None,
        q17_effort_table=[
            EffortRow(
                role="Procurement analyst",
                role_band=RoleBand.ADMIN,
                headcount=3,
                seniority="mid",
                frequency_per_week=25,
                current_minutes=45,
                expected_minutes=None,
            ),
        ],
        q18_error_rate=ErrorRate.UNKNOWN,
        q19_sensitive_data=["Financial", "Confidential internal"],
        q20_sign_off=SignOffRequirement.MANDATORY_APPROVAL,
        q21_sign_off_detail="Finance approves every new vendor record.",
        q22_failure_impact=FailureImpact.MEDIUM,
        q23_stakeholder_discussion="Yes neutral",
        q24_data_readiness=DataReadiness.NOT_READY,
        q25_urgency=Urgency.MEDIUM,
        q26_investment_band="AED 50-200k",
        q27_budget_likelihood="Unlikely",
        q28_estimated_annual_benefit_aed=None,
        q29_additional_context="Volumes have not been measured.",
    )


SAMPLES: dict[str, dict[str, Any]] = {
    "prior-auth": {
        "label": "Insurance pre-authorisation",
        "expect": "Proceeds to a composed architecture",
        "why": (
            "A well-formed submission with complete effort data. Runs the full "
            "19 steps and produces a quantified business case."
        ),
        "submission": _prior_auth(),
    },
    "medication": {
        "label": "Paediatric medication dosing",
        "expect": "Rejected at the feasibility gate",
        "why": (
            "Failure impact is Critical. Rule F01 rejects on error tolerance "
            "even though an agent could technically perform the task — a "
            "sponsor directive, not a seed rule."
        ),
        "submission": _medication(),
    },
    "onboarding": {
        "label": "Supplier onboarding",
        "expect": "Proceeds with conditions",
        "why": (
            "Effort and volume data are incomplete, so the business case "
            "reports 'requires input' rather than estimating. Shows the "
            "no-fabrication rule."
        ),
        "submission": _onboarding(),
    },
}


def list_samples() -> list[dict[str, Any]]:
    """Summaries for the picker, without the full payloads."""
    return [
        {
            "id": key,
            "label": value["label"],
            "expect": value["expect"],
            "why": value["why"],
        }
        for key, value in SAMPLES.items()
    ]


def get_sample(sample_id: str) -> dict[str, Any] | None:
    """Full submission payload, ready to post."""
    entry = SAMPLES.get(sample_id)
    if entry is None:
        return None
    payload = entry["submission"].model_dump(mode="json")
    # The server issues these; a sample must not pin them.
    payload.pop("submission_id", None)
    payload.pop("tracking_reference", None)
    payload.pop("submitted_at", None)
    return payload
