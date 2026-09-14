"""Verdict contracts — the deterministic gates.

Steps 8, 15, 18, 19 and 22 are D0: their outputs are produced by code
reading governed artifacts, never by a model.  The final scope document
carries no detailed record for any of them, so the rules encoded here are
derived from two defensible sources and are marked as such:

* A sponsor directive — the severe/permanent-harm rejection.
* The Q0-Q30 form's own risk signals (Q18, Q19, Q20, Q22).

Every rule carries a ``rule_id`` so the confirmation workshop can accept,
amend or replace each one individually.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from contracts.envelope import StepOutput


class RuleProvenance(str, Enum):
    """Where a rule came from. SEED rules must be confirmed with M42."""

    SPONSOR_DIRECTIVE = "sponsor_directive"
    REQUIREMENTS_V25 = "requirements_v2.5"
    SEED = "seed"


class RuleOutcome(BaseModel):
    """One rule's contribution to a verdict — the audit trail."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str
    provenance: RuleProvenance
    triggered: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Step 8 — Feasibility verdict (D0)
# ---------------------------------------------------------------------------

class FeasibilityOutcome(str, Enum):
    PROCEED = "proceed"
    REJECT = "reject"
    RETURN_AS_INTEGRATION = "return_as_integration"


class FeasibilityVerdict(StepOutput):
    """Placed after the cheap derivations (3-7) and before the expensive
    ones. Its inputs are derived, not estimated, so the verdict is
    deterministic.
    """

    outcome: FeasibilityOutcome
    reasons: list[str] = Field(default_factory=list)
    rules_evaluated: list[RuleOutcome] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 15 — Readiness verdict (D0)
# ---------------------------------------------------------------------------

class ReadinessOutcome(str, Enum):
    PASS = "pass"
    CONDITIONAL = "conditional"
    FAIL = "fail"


class ReadinessVerdict(StepOutput):
    outcome: ReadinessOutcome
    conditions: list[str] = Field(default_factory=list)
    rules_evaluated: list[RuleOutcome] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 18 — Derive exposure and influence (D0)
# ---------------------------------------------------------------------------

class ExposureClass(str, Enum):
    """How much the step is reachable by, or acts on, the outside world."""

    CONTAINED = "contained"
    INTERNAL = "internal"
    EXTERNAL = "external"


class InfluenceClass(str, Enum):
    """How much the step's output determines a consequential outcome."""

    ADVISORY = "advisory"
    CONTRIBUTORY = "contributory"
    DETERMINATIVE = "determinative"


class StepRiskClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    exposure: ExposureClass
    influence: InfluenceClass
    derived_from: list[str] = Field(default_factory=list)


class RiskDerivation(StepOutput):
    """Derived from the facet vectors of step 17 — never assigned directly.

    The asymmetry that drives the whole control surface: this solution can
    do little harm itself, but it determines what a system built next
    quarter will be required to do.
    """

    classes: list[StepRiskClass] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 19 — Evaluate obligations (D0)
# ---------------------------------------------------------------------------

class Obligation(BaseModel):
    """A CAFE control requirement (G-series).

    Count discrepancy: the final scope says G01-G26, Hamza's email says
    G01-G14. The seed obligation set uses the G01-G14 numbering and flags
    anything above G14 as unconfirmed.
    """

    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    title: str
    applies_to_nodes: list[str] = Field(default_factory=list)
    trigger: str = ""
    failure_mode: str = ""


class ControlRequirementSet(StepOutput):
    obligations: list[Obligation] = Field(default_factory=list)
    rules_evaluated: list[RuleOutcome] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 22 — Compose architecture (D0)
# ---------------------------------------------------------------------------

class ComposedArchitecture(StepOutput):
    """Conceptual, logical and physical views.

    ``solution_json`` is the CAFE interlock contract (framework 9.3). Once
    the CAFE packet arrives, the drawio-cafe generator becomes the
    conformance gate here: it renders this and refuses on any violation.
    """

    conceptual: dict = Field(default_factory=dict)
    logical: dict = Field(default_factory=dict)
    physical: dict = Field(default_factory=dict)
    solution_json: dict = Field(default_factory=dict)
    conformance_validated: bool = False
    conformance_violations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Human decision points
# ---------------------------------------------------------------------------

class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    RETURN_FOR_INFO = "return_for_info"
    RE_PROMPT = "re_prompt"


class OwnerConfirmationRequest(BaseModel):
    """Sponsor stage 1: the business owner confirms the objective and its
    value before any expensive derivation runs.
    """

    model_config = ConfigDict(extra="forbid")

    tracking_reference: str
    problem_statement: str
    accountable_owner: str
    expected_change: str
    stated_objective: str
    estimated_annual_benefit_aed: float | None = None
    prompt: str = "Confirm the objective and the value of achieving it."


class OwnerConfirmationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool
    corrections: str = ""
    confirmed_by: str = ""


class CoEReviewRequest(BaseModel):
    """Sponsor stage 2: the analysis report goes to the AI CoE via Teams and
    email to accept, reject, or send back for further information.
    """

    model_config = ConfigDict(extra="forbid")

    tracking_reference: str
    feasibility_outcome: FeasibilityOutcome
    criticality_band: str
    reuse_recommendation: str
    initial_business_case: dict = Field(default_factory=dict)
    unresolved_inputs: list[str] = Field(default_factory=list)
    prompt: str = "Accept, reject, or return for further information."


class CoEReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    notes: str = ""
    reviewed_by: str = ""
    information_requested: list[str] = Field(default_factory=list)


class ArchitectReviewRequest(BaseModel):
    """Sponsor stage 3: an architect approves, rejects or re-prompts.

    ``divergences`` drives the second gate — any divergence between the
    proposal and the original request goes back to the business owner.
    """

    model_config = ConfigDict(extra="forbid")

    tracking_reference: str
    build_surface: str
    component_count: int
    obligation_count: int
    conformance_validated: bool
    conformance_violations: list[str] = Field(default_factory=list)
    divergences: list[str] = Field(default_factory=list)
    prompt: str = "Approve the design, reject it, or re-prompt the derivation."


class ArchitectReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    notes: str = ""
    reviewed_by: str = ""
    re_prompt_guidance: str = ""
