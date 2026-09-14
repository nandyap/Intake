"""Step 18 — Derive exposure and influence (D0).

The facet vectors of step 17 go in; exposure and influence classes come
out.  No judgement is applied here — that is the point.  Step 17 assigns
facets with justification; this step derives risk classes by rule so two
identical facet sets always produce identical classes.

This asymmetry is the design driver for the whole control surface: the
intake system can do little harm itself, yet it determines what a system
built next quarter will be required to do.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.envelope import DeterminismTier
from contracts.steps import FacetAssignment
from contracts.verdicts import (
    ExposureClass,
    InfluenceClass,
    RiskDerivation,
    StepRiskClass,
)
from knowledge.retrieval import get_store

logger = logging.getLogger(__name__)

STEP = 18
ARTIFACT_ID = "facet-schema"


def _matches(facets: dict[str, str], when: dict[str, Any]) -> bool:
    """True when every condition in ``when`` holds for these facets."""
    for facet_name, expected in when.items():
        actual = facets.get(facet_name)
        if actual is None:
            return False
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _apply(rules: list[dict[str, Any]], facets: dict[str, str]) -> tuple[str, str]:
    """Walk the ordered rule list, returning (class, reason).

    First match wins, so rule order in the artifact is significant.
    """
    for rule in rules:
        if "default" in rule:
            return rule["default"], "default"
        if _matches(facets, rule.get("when", {})):
            conditions = ", ".join(f"{k}={v}" for k, v in rule["when"].items())
            return rule["class"], conditions
    return "contained", "no rule matched"


def derive(facet_assignment: FacetAssignment) -> RiskDerivation:
    """Derive an exposure and influence class for every step."""
    artifact = get_store().resolve(ARTIFACT_ID)
    rules = artifact.content["derivation_rules"]
    exposure_rules = rules["exposure"]
    influence_rules = rules["influence"]

    classes: list[StepRiskClass] = []
    for vector in facet_assignment.vectors:
        exposure_value, exposure_why = _apply(exposure_rules, vector.facets)
        influence_value, influence_why = _apply(influence_rules, vector.facets)

        classes.append(
            StepRiskClass(
                node_id=vector.node_id,
                exposure=ExposureClass(exposure_value),
                influence=InfluenceClass(influence_value),
                derived_from=[
                    f"exposure: {exposure_why}",
                    f"influence: {influence_why}",
                ],
            )
        )

    logger.info("Derived exposure/influence for %d steps", len(classes))

    return RiskDerivation(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Risk derivation service",
        artifacts_consulted=[artifact.ref],
        classes=classes,
    )
