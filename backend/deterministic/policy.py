"""Step 19 — Evaluate obligations (D0).

Turns derived risk classes into a control requirement set.  Obligations
are never chosen; they are triggered.  The trigger expressions live in the
obligation artifact so the control set changes under governance without an
application release.

The G-series count is unresolved: the final scope says G01-G26, Hamza's
consolidated email says G01-G14.  The seed uses G01-G14 and CAFE M3
supersedes it.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.envelope import DeterminismTier
from contracts.steps import FacetAssignment
from contracts.submission import OrgUnit, Submission
from contracts.verdicts import (
    ControlRequirementSet,
    ExposureClass,
    InfluenceClass,
    Obligation,
    RiskDerivation,
    RuleOutcome,
    RuleProvenance,
)
from knowledge.retrieval import get_store

logger = logging.getLogger(__name__)

STEP = 19
ARTIFACT_ID = "obligation-set"


def _node_context(
    node_id: str,
    facets: dict[str, str],
    risk: dict[str, Any],
    submission: Submission,
) -> dict[str, Any]:
    """Flatten everything a trigger may test into one namespace."""
    return {
        **facets,
        "exposure": risk.get("exposure"),
        "influence": risk.get("influence"),
        "org_unit": submission.q0_org_unit.value,
        "sensitive_data": submission.q19_sensitive_data,
        "node_id": node_id,
    }


def _triggered(obligation_id: str, ctx: dict[str, Any]) -> bool:
    """Evaluate an obligation's trigger against one node's context.

    Triggers are expressed declaratively in the artifact as prose; this
    maps each obligation id to its predicate. Keeping the predicates in
    code (rather than eval-ing artifact strings) is deliberate — an
    artifact must never be able to execute.
    """
    sensitive = {s.lower() for s in ctx.get("sensitive_data", [])}

    predicates: dict[str, Any] = {
        # L1 universal — always on.
        "G01": True,
        "G02": True,
        "G03": True,
        "G04": True,
        "G05": True,
        "G06": True,
        # L2 AI-specific — conditional on the derived classes.
        "G07": ctx.get("data_sensitivity") in {"confidential", "regulated"}
        or ctx.get("exposure") == ExposureClass.EXTERNAL.value,
        "G08": ctx.get("actor") != "system" or ctx.get("audience") != "none",
        "G09": ctx.get("determinism") in {"D1", "D2"},
        "G10": ctx.get("determinism") in {"D1", "D2"},
        "G11": ctx.get("effect_class") == "read",
        "G12": ctx.get("determinism") in {"D1", "D2"},
        # L3 group-specific.
        "G13": ctx.get("influence") == InfluenceClass.DETERMINATIVE.value
        or ctx.get("reversibility") == "irreversible",
        # L4 healthcare-conditional.
        "G14": ctx.get("org_unit") == OrgUnit.CLINICAL.value
        or "regulated" in sensitive,
    }
    return bool(predicates.get(obligation_id, False))


def evaluate(
    submission: Submission,
    facet_assignment: FacetAssignment,
    risk: RiskDerivation,
) -> ControlRequirementSet:
    """Build the control requirement set for this solution."""
    artifact = get_store().resolve(ARTIFACT_ID)
    catalogue = artifact.content["obligations"]

    risk_by_node = {c.node_id: c.model_dump(mode="json") for c in risk.classes}
    facets_by_node = {v.node_id: v.facets for v in facet_assignment.vectors}

    # obligation_id -> nodes that triggered it
    triggered: dict[str, list[str]] = {}
    for node_id, facets in facets_by_node.items():
        ctx = _node_context(
            node_id, facets, risk_by_node.get(node_id, {}), submission
        )
        for entry in catalogue:
            if _triggered(entry["id"], ctx):
                triggered.setdefault(entry["id"], []).append(node_id)

    obligations: list[Obligation] = []
    evaluated: list[RuleOutcome] = []
    for entry in catalogue:
        nodes = triggered.get(entry["id"], [])
        evaluated.append(
            RuleOutcome(
                rule_id=entry["id"],
                description=entry["title"],
                provenance=RuleProvenance.SEED,
                triggered=bool(nodes),
                detail=(
                    f"layer {entry['layer']} · {len(nodes)} node(s)"
                    if nodes
                    else f"layer {entry['layer']} · not triggered"
                ),
            )
        )
        if nodes:
            obligations.append(
                Obligation(
                    obligation_id=entry["id"],
                    title=entry["title"],
                    applies_to_nodes=nodes,
                    trigger=entry.get("trigger", ""),
                    failure_mode=entry.get("failure_mode", ""),
                )
            )

    logger.info(
        "Control requirement set: %d of %d obligations triggered",
        len(obligations),
        len(catalogue),
    )

    return ControlRequirementSet(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Policy service",
        artifacts_consulted=[artifact.ref],
        obligations=obligations,
        rules_evaluated=evaluated,
    )
