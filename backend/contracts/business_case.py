"""Business case contract — Appendix B.

Every field comes from exactly one of four provenance buckets.  The split
is what makes the two business cases separable:

* **Initial** (analysis stage) = S + C only.  Computable from the Q0-Q30
  answers and the named cost anchors, with NO architecture. This is in
  Phase 1.
* **Full** (funding stage) = adds A (needs steps 20-22) and M (finance,
  compliance, delegation-of-authority). This is NOT in Phase 1.

Cost figures use named anchors, not live Finance pulls, so estimates stay
consistent and comparable across submissions.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from contracts.envelope import StepOutput


class ProvenanceBucket(str, Enum):
    """Appendix B — the four buckets."""

    SURVEY_DIRECT = "S"       # verbatim from a Q0-Q30 answer
    ARCHITECTURE_DERIVED = "A"  # read from the generated architecture
    CALCULATED = "C"          # formula applied to S/A inputs
    MANUAL_EXTERNAL = "M"     # finance, compliance, sponsor, benchmarks


class CostAnchors(BaseModel):
    """Named assumptions from Appendix B, overridable by the registry.

    Pinned as a version so every line of an estimate can cite the sheet it
    came from — that is what makes the estimate auditable.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = "appendix-b-v1.0"
    currency: str = "AED"

    hourly_rate_doctor: float = 200.0
    hourly_rate_nurse: float = 80.0
    hourly_rate_admin: float = 60.0

    cost_per_error_clinical: float = 5000.0
    cost_per_error_operational: float = 500.0

    # Annual run cost as a fraction of build cost.
    annual_run_cost_ratio: float = 0.15
    # Year-1 operational saving discount applied when data is not fully
    # digital (Q24).
    not_digital_discount: float = 0.70

    def hourly_rate(self, role_band: str) -> float:
        return {
            "doctor": self.hourly_rate_doctor,
            "nurse": self.hourly_rate_nurse,
            "admin": self.hourly_rate_admin,
        }[role_band]


class BusinessCaseLine(BaseModel):
    """One costed or valued line, carrying its provenance."""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: float | None
    unit: str = "AED"
    bucket: ProvenanceBucket
    formula: str = ""
    source: str = ""
    # True when the input needed to compute this was absent. The
    # no-fabrication rule: never substitute a plausible number.
    requires_input: bool = False


class RolePosition(BaseModel):
    """Per-role annual effort and cost, from the Q17 effort table."""

    model_config = ConfigDict(extra="forbid")

    role: str
    role_band: str
    headcount: int
    annual_hours: float | None = None
    annual_cost: float | None = None
    annual_saving: float | None = None
    requires_input: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class Recommendation(str, Enum):
    PROCEED = "proceed"
    PROCEED_WITH_CONDITIONS = "proceed_with_conditions"
    DEFER = "defer"


class InitialBusinessCase(StepOutput):
    """The S+C business case produced before any architecture exists.

    v2.5's no-fabrication rule is enforced structurally: a case carrying
    any ``requires_input`` line can recommend proceed-with-conditions,
    never proceed.
    """

    anchors_version: str
    currency: str = "AED"

    positions: list[RolePosition] = Field(default_factory=list)
    lines: list[BusinessCaseLine] = Field(default_factory=list)

    annual_operational_saving: float | None = None
    annual_quality_saving: float | None = None
    annual_value: float | None = None
    # Build cost is architecture-derived (bucket A), so it is absent here
    # by design. ROI and payback therefore cannot be computed at this
    # stage and are deliberately left None.
    roi_multiple: float | None = None
    payback_months: float | None = None

    recommendation: Recommendation
    gate_conditions: list[str] = Field(default_factory=list)
    narrative: str = ""

    @property
    def has_placeholders(self) -> bool:
        return any(line.requires_input for line in self.lines) or any(
            p.requires_input for p in self.positions
        )
