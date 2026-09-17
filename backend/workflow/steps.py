"""Concrete step executors for the Phase 1 derivation graph.

Each step is either:

* a **D0 service** — plain Python delegating to ``deterministic/``, or
* a **D1/D2 agent** — an LLM proposal passed through the schema gate,
  falling back to a schema-valid stub when no model provider is
  configured.

The stub fallback is what makes Sprint 1 possible: the whole graph, its
loops and its gates can be exercised end to end before a single prompt is
written. Every stub output carries ``is_stub=True`` so a stubbed run can
never be mistaken for a real derivation.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.envelope import DesignPack, DeterminismTier, GapFlag, GapFlagType
from contracts.steps import (
    BuildSurfaceDecision,
    CapabilityMatch,
    ComponentChoice,
    ComponentSelection,
    ContainmentRecord,
    CoverageMap,
    CriticalityBand,
    CriticalityBandOutput,
    CriticalityConfirmation,
    DeterminismClassification,
    Element,
    ElementInventory,
    ElementType,
    FacetAssignment,
    FacetVector,
    GovernanceTier,
    OntologyDelta,
    OutcomeAssertion,
    OutcomeAssertions,
    QualityAttributes,
    QualityScenario,
    RealisationConfidence,
    RealisationEntry,
    RealisationMatch,
    ReuseRecommendation,
    StepTier,
    UseCaseRecord,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)
from contracts.submission import Submission
from deterministic import (
    business_case,
    composition,
    feasibility,
    policy,
    readiness,
    risk_derivation,
)
from knowledge.retrieval import get_store
from workflow.executors import StepExecutor
from workflow.prompts import PROMPTS
from workflow.runtime import propose

logger = logging.getLogger(__name__)


def _submission(pack: DesignPack) -> Submission:
    return Submission.model_validate(pack.outputs["submission"])


class AgentStep(StepExecutor):
    """A D1/D2 step: an agent proposes, the schema gate validates.

    ``agent`` is None in stub mode, in which case :meth:`stub` supplies a
    schema-valid placeholder.
    """

    def __init__(
        self,
        step_number: int,
        step_name: str,
        performed_by: str,
        tier: DeterminismTier,
        schema: type,
        agent: Any = None,
    ):
        self.performed_by = performed_by
        self.tier = tier
        self.schema = schema
        self.agent = agent
        super().__init__(step_number, step_name)

    def user_content(self, pack: DesignPack) -> str:
        """Assemble this step's inputs from the design pack."""
        raise NotImplementedError

    def stub(self, pack: DesignPack) -> Any:
        """Schema-valid placeholder used when no model is configured."""
        raise NotImplementedError

    def artifact_ids(self) -> tuple[str, ...]:
        """Governed artifacts this step reads. Resolved fail-closed."""
        return ()

    async def derive(self, pack: DesignPack) -> Any:
        refs = []
        for artifact in get_store().resolve_many(*self.artifact_ids()):
            refs.append(artifact.ref)

        if self.agent is None:
            output = self.stub(pack)
            output.is_stub = True
        else:
            output = await propose(
                agent=self.agent,
                system_prompt=PROMPTS[self.step_number],
                user_content=self.user_content(pack),
                schema=self.schema,
                # Provenance is ours to state, never the model's to claim.
                provenance={
                    "step": self.step_number,
                    "tier": self.tier,
                    "performed_by": self.performed_by,
                },
            )

        output.step = self.step_number
        output.tier = self.tier
        output.performed_by = self.performed_by

        # Deduplicate on identity, keeping order. A document read twice was
        # still only read once.
        seen: set[tuple[str, str]] = set()
        merged = []
        for ref in refs + list(output.artifacts_consulted):
            key = (ref.artifact_id, ref.version)
            if key not in seen:
                seen.add(key)
                merged.append(ref)
        output.artifacts_consulted = merged
        return output


# ---------------------------------------------------------------------------
# Step 3 — Frame use case (D1 · Business Analyst)
# ---------------------------------------------------------------------------

class FrameUseCase(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            3, "Frame use case", "Business Analyst",
            DeterminismTier.D1, UseCaseRecord, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        corrections = pack.outputs.get("owner_corrections", "")
        return (
            f"Task description (Q5): {sub.q5_task_description}\n"
            f"Biggest value (Q8): {sub.q8_biggest_value}\n"
            f"Goals (Q7): {', '.join(sub.q7_goals)}\n"
            f"Submitter: {sub.q1_full_name}, {sub.q3_job_title}, {sub.q2_department}\n"
            f"Relationship to task (Q4): {sub.q4_relationship.value}\n"
            f"Org unit (Q0): {sub.q0_org_unit.value}\n"
            f"Additional context (Q29): {sub.q29_additional_context}\n"
            + (f"\nOWNER CORRECTIONS FROM A PREVIOUS PASS: {corrections}\n" if corrections else "")
        )

    def stub(self, pack: DesignPack) -> UseCaseRecord:
        sub = _submission(pack)
        return UseCaseRecord(
            step=3, tier=DeterminismTier.D1, performed_by="Business Analyst",
            problem_statement=sub.q5_task_description[:280],
            accountable_owner=sub.q1_full_name,
            expected_change=sub.q8_biggest_value or "Not stated",
            source_channel=sub.channel.value,
        )


# ---------------------------------------------------------------------------
# Step 4 — Decompose elements (D2 · Business Architect)
# ---------------------------------------------------------------------------

class DecomposeElements(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            4, "Decompose elements", "Business Architect",
            DeterminismTier.D2, ElementInventory, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        use_case = pack.get(3) or {}
        return (
            f"Problem statement: {use_case.get('problem_statement')}\n"
            f"Task description (Q5): {sub.q5_task_description}\n"
            f"Systems involved (Q12): {', '.join(sub.q12_systems)}\n"
            f"Systems purpose (Q13): {sub.q13_systems_purpose}\n"
            f"Data types (Q14): {', '.join(sub.q14_data_types)}\n"
            f"Roles involved (Q17): "
            f"{', '.join(r.role for r in sub.q17_effort_table)}\n"
        )

    def stub(self, pack: DesignPack) -> ElementInventory:
        sub = _submission(pack)
        return ElementInventory(
            step=4, tier=DeterminismTier.D2, performed_by="Business Architect",
            active=[
                Element(label=r.role, element_type=ElementType.ACTIVE)
                for r in sub.q17_effort_table
            ] or [Element(label="Unnamed performer", element_type=ElementType.ACTIVE)],
            behavioural=[
                Element(label=c, element_type=ElementType.BEHAVIOURAL)
                for c in (sub.q6_categories or ["Process request"])
            ],
            passive=[
                Element(label=d, element_type=ElementType.PASSIVE)
                for d in (sub.q14_data_types or ["Record"])
            ],
        )


# ---------------------------------------------------------------------------
# Step 5 — Match capabilities (D1 · Business Architect)
# ---------------------------------------------------------------------------

class MatchCapabilities(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            5, "Match capabilities", "Business Architect",
            DeterminismTier.D1, CoverageMap, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        inventory = pack.get(4) or {}
        behavioural = [e["label"] for e in inventory.get("behavioural", [])]
        return "Business functions to map to L3 sub-capabilities:\n" + "\n".join(
            f"- {b}" for b in behavioural
        )

    def stub(self, pack: DesignPack) -> CoverageMap:
        inventory = pack.get(4) or {}
        behavioural = [e["label"] for e in inventory.get("behavioural", [])]
        # The business capability map (L1-L3) has not been provided. Every
        # function is therefore unmatched and raises a gap flag — this is
        # the correct behaviour, not a failure of the step.
        return CoverageMap(
            step=5, tier=DeterminismTier.D1, performed_by="Business Architect",
            matches=[],
            unmatched_functions=behavioural,
            gap_flags=[
                GapFlag(
                    flag_type=GapFlagType.MISSING_ARTIFACT,
                    step=5,
                    context=(
                        "The business capability map (L1-L3 with maturity, gap, "
                        "criticality, AI candidacy and KPIs) has not been provided "
                        "by M42. The 525-tile technology registry does not "
                        "substitute. No function could be matched."
                    ),
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 6 — Match realisations (D1 · Application Architect)
# ---------------------------------------------------------------------------

class MatchRealisations(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            6, "Match realisations", "Application Architect",
            DeterminismTier.D1, RealisationMatch, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        inventory = pack.get(4) or {}
        active = [e["label"] for e in inventory.get("active", [])]
        return (
            "Active elements:\n" + "\n".join(f"- {a}" for a in active) + "\n\n"
            f"Existing systems in use (Q12): {', '.join(sub.q12_systems)}\n"
            f"Write-back targets (Q12b): {', '.join(sub.q12b_write_back_targets)}\n"
        )

    def stub(self, pack: DesignPack) -> RealisationMatch:
        inventory = pack.get(4) or {}
        active = [e["label"] for e in inventory.get("active", [])]
        return RealisationMatch(
            step=6, tier=DeterminismTier.D1, performed_by="Application Architect",
            entries=[
                RealisationEntry(
                    element=a,
                    realisation="unknown — as-is architecture not provided",
                    confidence=RealisationConfidence.SURVEY,
                )
                for a in active
            ],
            reuse_recommendation=ReuseRecommendation.BUILD,
            reuse_rationale=(
                "No as-is architecture was available to check for reuse. "
                "Defaulting to build pending the AI and traditional as-is "
                "architecture artifacts."
            ),
            gap_flags=[
                GapFlag(
                    flag_type=GapFlagType.MISSING_ARTIFACT,
                    step=6,
                    context="AI as-is architecture and traditional as-is architecture not provided.",
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 7 — Assign criticality band (D1 · Risk Officer)
# ---------------------------------------------------------------------------

class AssignCriticalityBand(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            7, "Assign criticality band", "Risk Officer",
            DeterminismTier.D1, CriticalityBandOutput, agent,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return ("criticality-taxonomy",)

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        taxonomy = get_store().resolve("criticality-taxonomy").content
        return (
            f"Failure impact (Q22): {sub.q22_failure_impact.value}\n"
            f"Sensitive data (Q19): {', '.join(sub.q19_sensitive_data)}\n"
            f"Sign-off requirement (Q20): {sub.q20_sign_off.value}\n"
            f"Write-back targets (Q12b): {', '.join(sub.q12b_write_back_targets)}\n"
            f"Org unit (Q0): {sub.q0_org_unit.value}\n"
            f"Error rate (Q18): {sub.q18_error_rate.value}\n\n"
            f"Criticality taxonomy:\n{taxonomy}"
        )

    def stub(self, pack: DesignPack) -> CriticalityBandOutput:
        sub = _submission(pack)
        taxonomy = get_store().resolve("criticality-taxonomy").content

        band = CriticalityBand.ROUTINE
        for entry in taxonomy["classes"]:
            if sub.q22_failure_impact.value in entry["q22_impact"]:
                band = CriticalityBand(entry["band"])
                break

        # Escalation signals raise a band but never lower it.
        escalations: list[str] = []
        if band is CriticalityBand.ROUTINE:
            if sub.involves_sensitive_data:
                band = CriticalityBand.SIGNIFICANT
                escalations.append("sensitive data present (Q19)")
            elif sub.q20_sign_off.value == "Mandatory human approval":
                band = CriticalityBand.SIGNIFICANT
                escalations.append("mandatory human sign-off (Q20)")
            elif {"EMR", "ERP", "HRIS"} & set(sub.q12b_write_back_targets):
                band = CriticalityBand.SIGNIFICANT
                escalations.append("writes to a system of record (Q12b)")

        dominant = next(
            e["dominant_failure_mode"]
            for e in taxonomy["classes"]
            if e["band"] == band.value
        )
        return CriticalityBandOutput(
            step=7, tier=DeterminismTier.D1, performed_by="Risk Officer",
            band=band,
            dominant_failure_mode=dominant,
            rationale=(
                f"Q22 failure impact = {sub.q22_failure_impact.value}"
                + (f"; escalated by {', '.join(escalations)}" if escalations else "")
            ),
        )


# ---------------------------------------------------------------------------
# Step 8 — Feasibility verdict + initial business case (D0)
# ---------------------------------------------------------------------------

class FeasibilityGate(StepExecutor):
    """Deterministic. Also produces the initial (S+C) business case, which
    the sponsor requires before the AI CoE review."""

    def __init__(self):
        super().__init__(8, "Feasibility verdict", id="step_8")

    async def derive(self, pack: DesignPack) -> Any:
        from contracts.envelope import RunStatus
        from contracts.verdicts import FeasibilityOutcome

        sub = _submission(pack)
        verdict = feasibility.evaluate(
            submission=sub,
            use_case=UseCaseRecord.model_validate(pack.get(3)),
            coverage=CoverageMap.model_validate(pack.get(5)),
            realisation=RealisationMatch.model_validate(pack.get(6)),
            criticality=CriticalityBandOutput.model_validate(pack.get(7)),
        )
        case = business_case.build(sub)
        pack.outputs["initial_business_case"] = case.model_dump(mode="json")

        # The verdict is terminal for two of its three outcomes; reflect
        # that in the run status so the edges and the UI agree.
        if verdict.outcome is FeasibilityOutcome.REJECT:
            pack.status = RunStatus.REJECTED
        elif verdict.outcome is FeasibilityOutcome.RETURN_AS_INTEGRATION:
            pack.status = RunStatus.RETURNED_AS_INTEGRATION

        return verdict


# ---------------------------------------------------------------------------
# Step 9 — Derive quality attributes (D2 · Product Owner)
# ---------------------------------------------------------------------------

class DeriveQualityAttributes(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            9, "Derive quality attributes", "Product Owner",
            DeterminismTier.D2, QualityAttributes, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        coverage = pack.get(5) or {}
        functions = [m["business_function"] for m in coverage.get("matches", [])]
        functions = functions or coverage.get("unmatched_functions", [])
        return (
            "Business functions:\n" + "\n".join(f"- {f}" for f in functions) + "\n\n"
            f"Volume pattern (Q16): {sub.q16_volume_pattern.value}\n"
            f"Annual volume: {sub.q16_annual_volume}\n"
            f"Change frequency (Q15): {sub.q15_change_frequency.value}\n"
            f"Urgency (Q25): {sub.q25_urgency.value}\n"
        )

    def stub(self, pack: DesignPack) -> QualityAttributes:
        coverage = pack.get(5) or {}
        functions = [m["business_function"] for m in coverage.get("matches", [])]
        functions = functions or coverage.get("unmatched_functions", [])
        return QualityAttributes(
            step=9, tier=DeterminismTier.D2, performed_by="Product Owner",
            scenarios=[
                QualityScenario(
                    source="business user",
                    stimulus=f"requests {fn}",
                    environment="normal operation",
                    artifact=fn,
                    response="completes successfully",
                )
                for fn in functions
            ],
            gap_flags=[
                GapFlag(
                    flag_type=GapFlagType.MISSING_SERVICE_LEVEL,
                    step=9,
                    context=(
                        "No business service levels were available. Every level "
                        "must come from an existing business commitment; none "
                        "were provided, so no response measure was set."
                    ),
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 10 — Check ontology (D1 · Data Architect)
# ---------------------------------------------------------------------------

class CheckOntology(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            10, "Check ontology", "Data Architect",
            DeterminismTier.D1, OntologyDelta, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        inventory = pack.get(4) or {}
        passive = [e["label"] for e in inventory.get("passive", [])]
        return "Business objects to check:\n" + "\n".join(f"- {p}" for p in passive)

    def stub(self, pack: DesignPack) -> OntologyDelta:
        inventory = pack.get(4) or {}
        passive = [e["label"] for e in inventory.get("passive", [])]
        return OntologyDelta(
            step=10, tier=DeterminismTier.D1, performed_by="Data Architect",
            absent_concepts=passive,
            gap_flags=[
                GapFlag(
                    flag_type=GapFlagType.UNDEFINED_CONCEPT,
                    step=10,
                    context=(
                        "The organisation ontology was not provided (Phase 3 "
                        f"dependency). {len(passive)} business object(s) could "
                        "not be verified as defined concepts."
                    ),
                    owning_body="ontology_council",
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 11 — Sequence workflow (D2 · Business Analyst)
# ---------------------------------------------------------------------------

class SequenceWorkflow(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            11, "Sequence workflow", "Business Analyst",
            DeterminismTier.D2, WorkflowGraph, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        sub = _submission(pack)
        inventory = pack.get(4) or {}
        return (
            f"Task description (Q5): {sub.q5_task_description}\n"
            f"Step count (Q10): {sub.q10_step_count.value}\n"
            f"Conditional logic (Q11): {sub.q11_conditional_logic.value}\n\n"
            f"Active elements: {[e['label'] for e in inventory.get('active', [])]}\n"
            f"Behavioural elements: {[e['label'] for e in inventory.get('behavioural', [])]}\n"
            f"Passive elements: {[e['label'] for e in inventory.get('passive', [])]}\n"
        )

    def stub(self, pack: DesignPack) -> WorkflowGraph:
        inventory = pack.get(4) or {}
        behavioural = [e["label"] for e in inventory.get("behavioural", [])]
        active = [e["label"] for e in inventory.get("active", [])]
        passive = [e["label"] for e in inventory.get("passive", [])]
        performer = active[0] if active else "Unnamed performer"
        data_class = passive[0] if passive else "Record"

        nodes = [
            WorkflowNode(
                node_id=f"n{i + 1}",
                activity_verb=fn,
                performing_element=performer,
            )
            for i, fn in enumerate(behavioural)
        ]
        edges = [
            WorkflowEdge(
                from_node=nodes[i].node_id,
                to_node=nodes[i + 1].node_id,
                data_class=data_class,
                business_object=data_class,
            )
            for i in range(len(nodes) - 1)
        ]
        return WorkflowGraph(
            step=11, tier=DeterminismTier.D2, performed_by="Business Analyst",
            nodes=nodes, edges=edges,
        )


# ---------------------------------------------------------------------------
# Step 13 — Confirm criticality class (D1 · Risk Officer)
# ---------------------------------------------------------------------------

class ConfirmCriticality(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            13, "Confirm criticality class", "Risk Officer",
            DeterminismTier.D1, CriticalityConfirmation, agent,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return ("criticality-taxonomy",)

    def user_content(self, pack: DesignPack) -> str:
        band = pack.get(7) or {}
        workflow = pack.get(11) or {}
        return (
            f"Provisional band: {band.get('band')}\n"
            f"Dominant failure mode: {band.get('dominant_failure_mode')}\n"
            f"Workflow nodes: {len(workflow.get('nodes', []))}\n"
        )

    def stub(self, pack: DesignPack) -> CriticalityConfirmation:
        band = pack.get(7) or {}
        value = band.get("band", CriticalityBand.ROUTINE.value)
        return CriticalityConfirmation(
            step=13, tier=DeterminismTier.D1, performed_by="Risk Officer",
            is_homogeneous=True,
            class_per_branch={"default": CriticalityBand(value)},
            architect_confirmed=False,
        )


# ---------------------------------------------------------------------------
# Step 14 — Declare assertions (D1 · Product Owner)
# ---------------------------------------------------------------------------

class DeclareAssertions(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            14, "Declare assertions", "Product Owner",
            DeterminismTier.D1, OutcomeAssertions, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        confirmation = pack.get(13) or {}
        workflow = pack.get(11) or {}
        return (
            f"Criticality class: {confirmation.get('class_per_branch')}\n"
            f"Workflow nodes: "
            f"{[n['activity_verb'] for n in workflow.get('nodes', [])]}\n"
        )

    def stub(self, pack: DesignPack) -> OutcomeAssertions:
        sub = _submission(pack)
        return OutcomeAssertions(
            step=14, tier=DeterminismTier.D1, performed_by="Product Owner",
            assertions=[
                OutcomeAssertion(
                    statement=(
                        "The process completes without exceeding its stated "
                        "error tolerance."
                    ),
                    source_of_truth=(
                        ", ".join(sub.q12_systems) or "system of record (unnamed)"
                    ),
                    evaluation_schedule="monthly",
                    threshold=f"error rate at or below {sub.q18_error_rate.value}",
                    owning_monitor="Azure Monitor",
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 15 — Readiness verdict (D0)
# ---------------------------------------------------------------------------

class ReadinessGate(StepExecutor):
    def __init__(self):
        super().__init__(15, "Readiness verdict", id="step_15")

    async def derive(self, pack: DesignPack) -> Any:
        from contracts.envelope import RunStatus
        from contracts.verdicts import ReadinessOutcome

        verdict = readiness.evaluate(
            workflow=WorkflowGraph.model_validate(pack.get(11)),
            criticality=CriticalityConfirmation.model_validate(pack.get(13)),
            assertions=OutcomeAssertions.model_validate(pack.get(14)),
            quality=QualityAttributes.model_validate(pack.get(9)),
            ontology=OntologyDelta.model_validate(pack.get(10)),
        )
        if verdict.outcome is ReadinessOutcome.FAIL:
            pack.status = RunStatus.REJECTED
        return verdict


# ---------------------------------------------------------------------------
# Step 16 — Classify determinism (D1 · Solution Architect)
# ---------------------------------------------------------------------------

class ClassifyDeterminism(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            16, "Classify determinism", "Solution Architect",
            DeterminismTier.D1, DeterminismClassification, agent,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return ("determinism-criteria-register",)

    def user_content(self, pack: DesignPack) -> str:
        workflow = pack.get(11) or {}
        register = get_store().resolve("determinism-criteria-register").content
        guidance = pack.outputs.get("re_prompt_guidance", "")
        return (
            f"Workflow nodes:\n{workflow.get('nodes', [])}\n\n"
            f"Determinism criteria register:\n{register}\n"
            + (f"\nARCHITECT RE-PROMPT GUIDANCE: {guidance}\n" if guidance else "")
        )

    def stub(self, pack: DesignPack) -> DeterminismClassification:
        workflow = pack.get(11) or {}
        nodes = workflow.get("nodes", [])
        return DeterminismClassification(
            step=16, tier=DeterminismTier.D1, performed_by="Solution Architect",
            step_tiers=[
                StepTier(
                    node_id=n["node_id"],
                    tier="D1",
                    irreducible=True,
                    necessity_rationale="Stub classification — not derived.",
                )
                for n in nodes
            ],
            containment=[
                ContainmentRecord(
                    node_id=n["node_id"],
                    input_bounded=True,
                    output_bounded=True,
                )
                for n in nodes
            ],
            governance_tier=GovernanceTier.GUIDED_STOCHASTIC,
        )


# ---------------------------------------------------------------------------
# Step 17 — Assign facet vectors (D1 · Risk Officer)
# ---------------------------------------------------------------------------

class AssignFacetVectors(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            17, "Assign facet vectors", "Risk Officer",
            DeterminismTier.D1, FacetAssignment, agent,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return ("facet-schema",)

    def user_content(self, pack: DesignPack) -> str:
        workflow = pack.get(11) or {}
        schema = get_store().resolve("facet-schema").content
        return (
            f"Workflow nodes:\n{workflow.get('nodes', [])}\n\n"
            f"Facet schema and verb defaults:\n{schema}\n"
        )

    def stub(self, pack: DesignPack) -> FacetAssignment:
        workflow = pack.get(11) or {}
        sub = _submission(pack)
        schema = get_store().resolve("facet-schema").content
        defaults = schema["verb_defaults"]
        base = dict(defaults["_default"])

        # Sensitivity is a property of the submission, not the verb.
        if sub.involves_sensitive_data:
            base["data_sensitivity"] = "regulated"

        vectors = []
        for node in workflow.get("nodes", []):
            verb = node["activity_verb"].split()[0].lower()
            facets = {**base, **defaults.get(verb, {})}
            facets["determinism"] = "D1"
            vectors.append(FacetVector(node_id=node["node_id"], facets=facets))

        return FacetAssignment(
            step=17, tier=DeterminismTier.D1, performed_by="Risk Officer",
            vectors=vectors,
        )


# ---------------------------------------------------------------------------
# Steps 18, 19 — deterministic risk and policy
# ---------------------------------------------------------------------------

class DeriveRisk(StepExecutor):
    def __init__(self):
        super().__init__(18, "Derive exposure and influence", id="step_18")

    async def derive(self, pack: DesignPack) -> Any:
        return risk_derivation.derive(
            FacetAssignment.model_validate(pack.get(17))
        )


class EvaluateObligations(StepExecutor):
    def __init__(self):
        super().__init__(19, "Evaluate obligations", id="step_19")

    async def derive(self, pack: DesignPack) -> Any:
        from contracts.verdicts import RiskDerivation

        return policy.evaluate(
            submission=_submission(pack),
            facet_assignment=FacetAssignment.model_validate(pack.get(17)),
            risk=RiskDerivation.model_validate(pack.get(18)),
        )


# ---------------------------------------------------------------------------
# Step 20 — Select build surface (D1 · Technology Architect)
# ---------------------------------------------------------------------------

class SelectBuildSurface(AgentStep):
    def __init__(self, agent: Any = None):
        super().__init__(
            20, "Select build surface", "Technology Architect",
            DeterminismTier.D1, BuildSurfaceDecision, agent,
        )

    def artifact_ids(self) -> tuple[str, ...]:
        return ("build-surface-matrix",)

    def user_content(self, pack: DesignPack) -> str:
        controls = pack.get(19) or {}
        realisation = pack.get(6) or {}
        matrix = get_store().resolve("build-surface-matrix").content
        return (
            f"Required obligations: "
            f"{[o['obligation_id'] for o in controls.get('obligations', [])]}\n"
            f"Realisation match: {realisation.get('reuse_recommendation')}\n\n"
            f"Build surface matrix:\n{matrix}\n"
        )

    def stub(self, pack: DesignPack) -> BuildSurfaceDecision:
        controls = pack.get(19) or {}
        required = {o["obligation_id"] for o in controls.get("obligations", [])}
        matrix = get_store().resolve("build-surface-matrix").content

        chosen = None
        conditional: list[str] = []
        for surface in matrix["surfaces"]:
            enforceability = surface.get("enforceability")
            if not isinstance(enforceability, dict):
                continue
            if any(enforceability.get(o) == "unavailable" for o in required):
                continue
            chosen = surface
            conditional = [
                o for o in required if enforceability.get(o) == "conditional"
            ]
            break

        if chosen is None:
            return BuildSurfaceDecision(
                step=20, tier=DeterminismTier.D1,
                performed_by="Technology Architect",
                surface="none",
                rationale=(
                    "No surface can enforce every required obligation. v2.5 "
                    "directs a return to step 17 rather than selecting a "
                    "different runtime."
                ),
                conditional_obligations=sorted(required),
            )

        return BuildSurfaceDecision(
            step=20, tier=DeterminismTier.D1, performed_by="Technology Architect",
            surface=chosen["surface"],
            rationale=chosen["when_to_use"],
            conditional_obligations=sorted(conditional),
        )


# ---------------------------------------------------------------------------
# Step 21 — Select components (D1 · Solution Architect)
# ---------------------------------------------------------------------------

class SelectComponents(AgentStep):
    def __init__(self, agent: Any = None, registry: Any = None):
        self.registry = registry
        super().__init__(
            21, "Select components", "Solution Architect",
            DeterminismTier.D1, ComponentSelection, agent,
        )

    def user_content(self, pack: DesignPack) -> str:
        controls = pack.get(19) or {}
        surface = pack.get(20) or {}
        quality = pack.get(9) or {}
        return (
            f"Build surface: {surface.get('surface')}\n"
            f"Control requirements: "
            f"{[o['obligation_id'] for o in controls.get('obligations', [])]}\n"
            f"Quality scenarios: {len(quality.get('scenarios', []))}\n"
        )

    def stub(self, pack: DesignPack) -> ComponentSelection:
        surface = pack.get(20) or {}
        # The 525-tile registry serves this step; it is not wired into the
        # stub path so a stubbed run never looks like a real selection.
        return ComponentSelection(
            step=21, tier=DeterminismTier.D1, performed_by="Solution Architect",
            components=[
                ComponentChoice(
                    capability="orchestration",
                    chosen_id="stub-orchestration",
                    chosen_name=surface.get("surface", "unknown"),
                    rationale="Stub selection — capability registry not queried.",
                )
            ],
            gap_flags=[
                GapFlag(
                    flag_type=GapFlagType.MISSING_ARTIFACT,
                    step=21,
                    context=(
                        "Component selection ran in stub mode. The 525-tile "
                        "capability registry was not queried."
                    ),
                )
            ],
        )


# ---------------------------------------------------------------------------
# Step 22 — Compose architecture (D0)
# ---------------------------------------------------------------------------

class ComposeArchitecture(StepExecutor):
    def __init__(self):
        super().__init__(22, "Compose architecture", id="step_22")

    async def derive(self, pack: DesignPack) -> Any:
        from contracts.verdicts import ControlRequirementSet, RiskDerivation

        return composition.compose(
            use_case=UseCaseRecord.model_validate(pack.get(3)),
            coverage=CoverageMap.model_validate(pack.get(5)),
            workflow=WorkflowGraph.model_validate(pack.get(11)),
            determinism=DeterminismClassification.model_validate(pack.get(16)),
            risk=RiskDerivation.model_validate(pack.get(18)),
            controls=ControlRequirementSet.model_validate(pack.get(19)),
            surface=BuildSurfaceDecision.model_validate(pack.get(20)),
            components=ComponentSelection.model_validate(pack.get(21)),
        )
