"""Step contracts for the Phase 1 derivation (steps 3-22).

Each model is taken from the "Output — what | to where | schema" column of
the corresponding step table in the final scope document.  These are the
schema gates: an agent proposes, this validates, and only validated output
enters the design pack.

Step 12 (Contract sources) is defined but not wired into the graph — it has
no green inputs in Phase 1.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from contracts.envelope import StepOutput


# ---------------------------------------------------------------------------
# Step 3 — Frame use case (D1 · Business Analyst)
# ---------------------------------------------------------------------------

class UseCaseRecord(StepOutput):
    """Decision logic: state the problem, for whom, and what changes if it
    works. Identify ONE accountable person. Reject a problem stated as a
    solution, and reject shared accountability.
    """

    problem_statement: str
    accountable_owner: str
    expected_change: str
    source_channel: str
    # Set when the submission described a solution rather than a problem,
    # or named shared accountability. Both are rejections at this step.
    framing_rejection: str | None = None


# ---------------------------------------------------------------------------
# Step 4 — Decompose elements (D2 · Business Architect)
# ---------------------------------------------------------------------------

class ElementType(str, Enum):
    ACTIVE = "active"           # who or what performs
    BEHAVIOURAL = "behavioural"  # business functions, verb-plus-object
    PASSIVE = "passive"          # business objects


class Element(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    element_type: ElementType


class ElementInventory(StepOutput):
    """Three typed lists. Sequence nothing — an implied order means the
    workflow has been assumed rather than derived.
    """

    active: list[Element] = Field(default_factory=list)
    behavioural: list[Element] = Field(default_factory=list)
    passive: list[Element] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 5 — Match capabilities (D1 · Business Architect)
# ---------------------------------------------------------------------------

class CapabilityMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_function: str
    l3_capability_id: str
    l3_capability_name: str
    confidence: float = Field(ge=0, le=1)


class CoverageMap(StepOutput):
    """Coverage is checked in BOTH directions. Never invent a capability to
    justify the use case — an unmatched function is a gap flag.
    """

    matches: list[CapabilityMatch] = Field(default_factory=list)
    unmatched_functions: list[str] = Field(default_factory=list)
    unmatched_in_scope_capabilities: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 6 — Match realisations (D1 · Application Architect)
# ---------------------------------------------------------------------------

class RealisationConfidence(str, Enum):
    LOOKUP = "lookup"          # an as-is entry exists
    ASSUMPTION = "assumption"  # only a capability type exists
    SURVEY = "survey"          # neither — someone had to go and look


class ReuseRecommendation(str, Enum):
    REUSE = "reuse"
    EXTEND = "extend"
    BUILD = "build"
    INTEGRATE = "integrate"


class RealisationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element: str
    realisation: str
    confidence: RealisationConfidence
    operator: str = ""
    failure_semantics: str = ""


class RealisationMatch(StepOutput):
    """Ask the reuse question — does a block already realise this
    capability, making this an integration rather than a build?
    """

    entries: list[RealisationEntry] = Field(default_factory=list)
    reuse_recommendation: ReuseRecommendation
    reuse_rationale: str


# ---------------------------------------------------------------------------
# Step 7 — Assign criticality band (D1 · Risk Officer)
# ---------------------------------------------------------------------------

class CriticalityBand(str, Enum):
    ROUTINE = "routine"
    SIGNIFICANT = "significant"
    SEVERE = "severe"


class CriticalityBandOutput(StepOutput):
    """Ask what happens when it fails, not how often. Provisional — this is
    the band for the feasibility verdict, not the confirmed class (step 13).
    """

    band: CriticalityBand
    dominant_failure_mode: str
    rationale: str


# ---------------------------------------------------------------------------
# Step 9 — Derive quality attributes (D2 · Product Owner)
# ---------------------------------------------------------------------------

class QualityScenario(BaseModel):
    """Six-part scenario with a numeric response measure and a percentile."""

    model_config = ConfigDict(extra="forbid")

    source: str
    stimulus: str
    environment: str
    artifact: str
    response: str
    response_measure_value: float | None = None
    response_measure_unit: str = ""
    percentile: int | None = Field(default=None, ge=0, le=100)
    # v2.5: take every level from an existing business commitment — never
    # invent one. Where none exists, raise a gap flag.
    commitment_source: str = ""


class QualityAttributes(StepOutput):
    scenarios: list[QualityScenario] = Field(default_factory=list)
    envelope_values: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step 10 — Check ontology (D1 · Data Architect)
# ---------------------------------------------------------------------------

class OntologyDelta(StepOutput):
    """Two checks at the OBJECT level, not the step level."""

    absent_concepts: list[str] = Field(default_factory=list)
    unbound_concepts: list[str] = Field(default_factory=list)
    logged_conflicts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 11 — Sequence workflow (D2 · Business Analyst)
# ---------------------------------------------------------------------------

class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    activity_verb: str
    performing_element: str


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: str
    to_node: str
    data_class: str
    business_object: str = ""


class WorkflowGraph(StepOutput):
    """One step per business function per active element; split further only
    where determinism, effect class or authorisation changes.
    """

    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 12 — Contract sources (DEFERRED in Phase 1 — no green inputs)
# ---------------------------------------------------------------------------

class RetrievalContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    scope: str
    permission_model: str
    citation_policy: str
    freshness_expectation: str


class SourceContracts(StepOutput):
    contracts: list[RetrievalContract] = Field(default_factory=list)
    permission_propagation: dict[str, str] = Field(default_factory=dict)
    deferred: bool = True


# ---------------------------------------------------------------------------
# Step 13 — Confirm criticality class (D1 · Risk Officer, architect confirms)
# ---------------------------------------------------------------------------

class CriticalityConfirmation(StepOutput):
    """Homogeneous gives one class; heterogeneous with a pre-interpretation
    signal gives a router and one branch per class; heterogeneous without
    one takes the HIGHEST class present. Never set the class by cost or
    timeline.
    """

    is_homogeneous: bool
    class_per_branch: dict[str, CriticalityBand] = Field(default_factory=dict)
    router_definition: dict[str, str] | None = None
    risk_register_links: list[str] = Field(default_factory=list)
    architect_confirmed: bool = False


# ---------------------------------------------------------------------------
# Step 14 — Declare assertions (D1 · Product Owner)
# ---------------------------------------------------------------------------

class OutcomeAssertion(BaseModel):
    """Must be evaluable against a system of record WITHOUT reading anything
    the workflow produced.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str
    source_of_truth: str
    evaluation_schedule: str
    threshold: str
    owning_monitor: str


class OutcomeAssertions(StepOutput):
    assertions: list[OutcomeAssertion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 16 — Classify determinism (D1 · Solution Architect)
# ---------------------------------------------------------------------------

class GovernanceTier(str, Enum):
    GUIDED_STOCHASTIC = "guided_stochastic"
    OPEN_STOCHASTIC = "open_stochastic"
    DETERMINISTIC = "deterministic"


class StepTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    tier: str
    irreducible: bool = False
    necessity_rationale: str = ""


class ContainmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    input_bounded: bool
    output_bounded: bool
    neighbours: list[str] = Field(default_factory=list)
    position_relative_to_commit: str = ""


class DeterminismClassification(StepOutput):
    step_tiers: list[StepTier] = Field(default_factory=list)
    containment: list[ContainmentRecord] = Field(default_factory=list)
    governance_tier: GovernanceTier


# ---------------------------------------------------------------------------
# Step 17 — Assign facet vectors (D1 · Risk Officer)
# ---------------------------------------------------------------------------

class FacetVector(BaseModel):
    """Nine facets per step, defaulted from the activity verb."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    facets: dict[str, str] = Field(default_factory=dict)


class FacetOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    facet: str
    default_value: str
    override_value: str
    justification: str


class FacetAssignment(StepOutput):
    """Do NOT derive exposure or influence here — that is step 18 and it is
    deterministic.
    """

    vectors: list[FacetVector] = Field(default_factory=list)
    override_log: list[FacetOverride] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 20 — Select build surface (D1 · Technology Architect)
# ---------------------------------------------------------------------------

class BuildSurfaceDecision(StepOutput):
    """Ask FIRST whether an incumbent platform already owns the workflow
    graph and system of record. Where a surface cannot enforce an
    obligation, return to step 17 rather than choosing a different runtime.
    """

    surface: str
    rationale: str
    incumbent_evaluated: str | None = None
    obligations_incumbent_failed: list[str] = Field(default_factory=list)
    conditional_obligations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 21 — Select components (D1 · Solution Architect)
# ---------------------------------------------------------------------------

class ComponentChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    chosen_id: str
    chosen_name: str
    alternatives_considered: list[str] = Field(default_factory=list)
    rationale: str


class DecisionRecord(BaseModel):
    """Where the intersection is empty, resolve as a tradeoff and record
    what was sacrificed.
    """

    model_config = ConfigDict(extra="forbid")

    context: str
    drivers: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    decision: str
    sacrifice: str = ""
    compensating_control: str = ""
    review_trigger: str = ""
    approver: str = ""


class ComponentSelection(StepOutput):
    components: list[ComponentChoice] = Field(default_factory=list)
    declared_building_blocks: list[dict[str, str]] = Field(default_factory=list)
    decision_records: list[DecisionRecord] = Field(default_factory=list)
