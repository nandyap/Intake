"""Step 22 — Compose architecture (D0).

Assembles the conceptual, logical and physical views from everything
already derived.  Composition is deterministic because it *arranges*
prior outputs; it does not decide anything new.

``solution_json`` is the CAFE interlock contract (framework section 9.3).
When the CAFE packet arrives, ``drawio_cafe`` becomes the conformance gate
here — it renders the solution and refuses on any violation.  Until then a
structural self-check runs in its place and the output is marked
unvalidated so nobody mistakes it for a conformance pass.
"""

from __future__ import annotations

import logging

from contracts.envelope import DeterminismTier
from contracts.steps import (
    BuildSurfaceDecision,
    ComponentSelection,
    CoverageMap,
    DeterminismClassification,
    UseCaseRecord,
    WorkflowGraph,
)
from contracts.verdicts import ComposedArchitecture, ControlRequirementSet, RiskDerivation

logger = logging.getLogger(__name__)

STEP = 22


def compose(
    use_case: UseCaseRecord,
    coverage: CoverageMap,
    workflow: WorkflowGraph,
    determinism: DeterminismClassification,
    risk: RiskDerivation,
    controls: ControlRequirementSet,
    surface: BuildSurfaceDecision,
    components: ComponentSelection,
) -> ComposedArchitecture:
    """Compose the three architecture views plus the CAFE solution.json."""
    conceptual = {
        "problem_statement": use_case.problem_statement,
        "accountable_owner": use_case.accountable_owner,
        "expected_change": use_case.expected_change,
        "capabilities": [
            {"function": m.business_function, "capability": m.l3_capability_name}
            for m in coverage.matches
        ],
    }

    risk_by_node = {c.node_id: c for c in risk.classes}
    tier_by_node = {t.node_id: t.tier for t in determinism.step_tiers}

    logical = {
        "governance_tier": determinism.governance_tier.value,
        "steps": [
            {
                "node_id": node.node_id,
                "activity": node.activity_verb,
                "performed_by": node.performing_element,
                "tier": tier_by_node.get(node.node_id, "unclassified"),
                "exposure": (
                    risk_by_node[node.node_id].exposure.value
                    if node.node_id in risk_by_node
                    else None
                ),
                "influence": (
                    risk_by_node[node.node_id].influence.value
                    if node.node_id in risk_by_node
                    else None
                ),
            }
            for node in workflow.nodes
        ],
        "edges": [
            {"from": e.from_node, "to": e.to_node, "data_class": e.data_class}
            for e in workflow.edges
        ],
        "obligations": [
            {"id": o.obligation_id, "title": o.title, "nodes": o.applies_to_nodes}
            for o in controls.obligations
        ],
    }

    physical = {
        "build_surface": surface.surface,
        "rationale": surface.rationale,
        "components": [
            {
                "capability": c.capability,
                "component": c.chosen_name,
                "component_id": c.chosen_id,
            }
            for c in components.components
        ],
        "declared_building_blocks": components.declared_building_blocks,
        "conditional_obligations": surface.conditional_obligations,
    }

    solution_json = {
        "schema": "cafe-solution/0.1-provisional",
        "components": [c.chosen_id for c in components.components],
        "edges": [
            {
                "from": e.from_node,
                "to": e.to_node,
                "kind": e.data_class,
            }
            for e in workflow.edges
        ],
        "guardrails": [o.obligation_id for o in controls.obligations],
        "governance_tier": determinism.governance_tier.value,
    }

    violations = _self_check(solution_json, determinism, controls)

    logger.info(
        "Composed architecture: %d components, %d obligations, %d violations",
        len(components.components),
        len(controls.obligations),
        len(violations),
    )

    return ComposedArchitecture(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Composition service",
        conceptual=conceptual,
        logical=logical,
        physical=physical,
        solution_json=solution_json,
        # Deliberately False: a real conformance pass requires the CAFE
        # generator. This self-check is a structural sanity test only.
        conformance_validated=False,
        conformance_violations=violations,
    )


def _self_check(
    solution_json: dict,
    determinism: DeterminismClassification,
    controls: ControlRequirementSet,
) -> list[str]:
    """Structural checks that stand in for the CAFE generator.

    Replace with ``drawio_cafe.validate(solution_json)`` once the CAFE
    packet arrives.
    """
    violations: list[str] = []

    if not solution_json["components"]:
        violations.append("No components selected — the physical view is empty.")

    if determinism.governance_tier.value == "open_stochastic":
        violations.append(
            "Governance tier is open-stochastic. A step selects its own "
            "successor, which requires Board approval and is forbidden in "
            "this solution."
        )

    guardrails = set(solution_json["guardrails"])
    for mandatory in ("G01", "G02", "G05"):
        if mandatory not in guardrails:
            violations.append(
                f"Mandatory universal obligation {mandatory} is absent from "
                "the control requirement set."
            )

    determinative_nodes = {
        node
        for o in controls.obligations
        if o.obligation_id == "G13"
        for node in o.applies_to_nodes
    }
    if determinative_nodes and "G13" not in guardrails:
        violations.append(
            "Determinative or irreversible steps exist without the G13 "
            "human-decision obligation."
        )

    return violations
