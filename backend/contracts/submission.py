"""Submission contract — the Q0-Q30 intake form.

Source: `m42_use_cases_agent_requirements.docx` Appendix A, form
"Agentic AI Use Case Readiness".  This is the single validated record
persisted at step 2; every later step reads this, never the channel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Pathway(str, Enum):
    """Short form triages; comprehensive drives the business case."""

    QUICK = "quick"
    COMPREHENSIVE = "comprehensive"


class OrgUnit(str, Enum):
    """Q0 — routes the request."""

    ENGINEERING = "Engineering"
    OPERATIONAL = "Operational"
    CLINICAL = "Clinical"
    CONSULTANCY = "Consultancy"


class Channel(str, Enum):
    """Requirement 1 — text intake across these channels."""

    FORM = "form"
    TEAMS = "teams"
    COPILOT = "copilot"
    EMAIL = "email"
    BATCH = "batch"


class Relationship(str, Enum):
    """Q4."""

    PERFORMS = "I perform it myself"
    MANAGES = "I manage the team"
    CUSTOMER = "I am an internal customer"


class StepCount(str, Enum):
    """Q10."""

    S_1_5 = "1-5"
    S_6_15 = "6-15"
    S_16_30 = "16-30"
    S_OVER_30 = ">30"


class ConditionalLogic(str, Enum):
    """Q11."""

    NONE = "No"
    SIMPLE = "A few simple conditions"
    NESTED = "Many or nested rules"


class ChangeFrequency(str, Enum):
    """Q15."""

    RARELY = "Rarely"
    OCCASIONALLY = "Occasionally"
    FREQUENTLY = "Frequently"


class VolumePattern(str, Enum):
    """Q16."""

    CONSISTENT = "Consistent"
    PREDICTABLE_PEAKS = "Predictable peaks"
    HIGHLY_VARIABLE = "Highly variable"


class ErrorRate(str, Enum):
    """Q18 — drives the quality-saving calculation."""

    RARELY = "Rarely <1%"
    OCCASIONALLY = "Occasionally 1-5%"
    FREQUENTLY = "Frequently >5%"
    UNKNOWN = "Unknown"

    @property
    def midpoint(self) -> float | None:
        """Representative rate, or None when unknown.

        None is propagated, never defaulted — the no-fabrication rule.
        """
        return {
            ErrorRate.RARELY: 0.005,
            ErrorRate.OCCASIONALLY: 0.03,
            ErrorRate.FREQUENTLY: 0.07,
            ErrorRate.UNKNOWN: None,
        }[self]


class SignOffRequirement(str, Enum):
    """Q20."""

    MANDATORY_APPROVAL = "Mandatory human approval"
    AUDIT_TRAIL_ONLY = "Audit trail only"
    NONE = "No"


class FailureImpact(str, Enum):
    """Q22 — the dominant input to the step-7 criticality band and to the
    step-8 severe-harm rejection rule."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class DataReadiness(str, Enum):
    """Q24 — drives the Appendix B year-1 discount."""

    FULLY = "Yes fully"
    PARTIALLY = "Partially"
    NOT_READY = "No, work needed first"


class Urgency(str, Enum):
    """Q25."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class RoleBand(str, Enum):
    """Cost anchor bands from Appendix B."""

    DOCTOR = "doctor"
    NURSE = "nurse"
    ADMIN = "admin"


class EffortRow(BaseModel):
    """One row of the Q17 structured effort table.

    This table is what makes an initial business case possible without an
    architecture.  Missing values are left None so the calculator can mark
    the driver "requires input" rather than fabricating a number.
    """

    model_config = ConfigDict(extra="forbid")

    role: str
    role_band: RoleBand
    headcount: int = Field(ge=0)
    seniority: str = ""
    frequency_per_week: float = Field(ge=0)
    current_minutes: float | None = Field(default=None, ge=0)
    expected_minutes: float | None = Field(default=None, ge=0)


class Submission(BaseModel):
    """The validated, persisted intake record (steps 1-2).

    Field names carry their questionnaire number so provenance back to
    Appendix A stays explicit in every downstream artifact.
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: str
    tracking_reference: str
    pathway: Pathway = Pathway.COMPREHENSIVE
    channel: Channel = Channel.FORM
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Section 0 — Org
    q0_org_unit: OrgUnit

    # Section 1 — Submitter profile
    q1_full_name: str
    q2_department: str
    q3_job_title: str
    q4_relationship: Relationship

    # Section 2 — Background
    q5_task_description: str = Field(min_length=20)
    q6_categories: list[str] = Field(default_factory=list)
    q7_goals: list[str] = Field(default_factory=list)
    q8_biggest_value: str = ""
    q9_other_kpis: str = ""

    # Section 3 — Workflow structure & complexity
    q10_step_count: StepCount
    q11_conditional_logic: ConditionalLogic
    q12_systems: list[str] = Field(default_factory=list)
    q12b_write_back_targets: list[str] = Field(default_factory=list)
    q13_systems_purpose: str = ""
    q14_data_types: list[str] = Field(default_factory=list)
    q15_change_frequency: ChangeFrequency
    q16_volume_pattern: VolumePattern
    q16_annual_volume: int | None = Field(default=None, ge=0)
    q17_effort_table: list[EffortRow] = Field(default_factory=list)

    # Section 4 — Risk & compliance
    q18_error_rate: ErrorRate
    q19_sensitive_data: list[str] = Field(default_factory=list)
    q20_sign_off: SignOffRequirement
    q21_sign_off_detail: str = ""
    q22_failure_impact: FailureImpact

    # Section 5 — Readiness & dependencies
    q23_stakeholder_discussion: str = ""
    q24_data_readiness: DataReadiness

    # Section 6 — Solution & financial assessment
    q25_urgency: Urgency
    q26_investment_band: str = ""
    q27_budget_likelihood: str = ""
    q28_estimated_annual_benefit_aed: float | None = Field(default=None, ge=0)

    # Section 7 — Final notes
    q29_additional_context: str = ""
    # Q30 attachments are stored but NOT parsed in Phase 1 — the
    # requirements spec says "no document ingestion" while the form offers
    # upload. Open question #Q30 in the approach doc.
    q30_attachment_names: list[str] = Field(default_factory=list)

    @property
    def involves_sensitive_data(self) -> bool:
        return bool([s for s in self.q19_sensitive_data if s.lower() != "none"])
