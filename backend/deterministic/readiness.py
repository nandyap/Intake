"""Step 15 — Readiness verdict (D0).

Gates the deep derivation: are the outputs of steps 9-14 complete enough
for determinism classification and control derivation to mean anything?

No detailed record exists in the final scope document; these rules are
seeds and are labelled as such in every verdict they produce.
"""

from __future__ import annotations

import logging

from contracts.envelope import DeterminismTier
from contracts.steps import (
    CriticalityConfirmation,
    OntologyDelta,
    OutcomeAssertions,
    QualityAttributes,
    WorkflowGraph,
)
from contracts.verdicts import (
    ReadinessOutcome,
    ReadinessVerdict,
    RuleOutcome,
    RuleProvenance,
)
from knowledge.retrieval import get_store

logger = logging.getLogger(__name__)

STEP = 15
ARTIFACT_ID = "readiness-rules"


def evaluate(
    workflow: WorkflowGraph,
    criticality: CriticalityConfirmation,
    assertions: OutcomeAssertions,
    quality: QualityAttributes,
    ontology: OntologyDelta,
) -> ReadinessVerdict:
    """Produce the readiness verdict.

    A FAIL stops the run. A CONDITIONAL proceeds carrying named conditions
    that must be closed before build hand-off.
    """
    artifact = get_store().resolve(ARTIFACT_ID)

    evaluated: list[RuleOutcome] = []
    conditions: list[str] = []
    outcome = ReadinessOutcome.PASS

    def record(rule_id: str, description: str, triggered: bool, detail: str) -> bool:
        evaluated.append(
            RuleOutcome(
                rule_id=rule_id,
                description=description,
                provenance=RuleProvenance.SEED,
                triggered=triggered,
                detail=detail,
            )
        )
        return triggered

    # -- R01 · no workflow graph (fail) -----------------------------------
    if record(
        "R01",
        "Fail where no workflow graph could be sequenced.",
        not workflow.nodes,
        f"{len(workflow.nodes)} nodes",
    ):
        outcome = ReadinessOutcome.FAIL
        conditions.append(
            "No workflow graph was derived. Steps 16-19 cannot classify "
            "determinism or derive controls without per-step nodes."
        )

    # -- R02 · criticality unconfirmed (fail) ------------------------------
    unconfirmed = (
        not criticality.architect_confirmed and not criticality.class_per_branch
    )
    if record(
        "R02",
        "Fail where the criticality class was not confirmed.",
        unconfirmed,
        f"confirmed={criticality.architect_confirmed}, "
        f"branches={len(criticality.class_per_branch)}",
    ):
        outcome = ReadinessOutcome.FAIL
        conditions.append(
            "Criticality class is unconfirmed. Control derivation would "
            "proceed on an unvalidated rigour level."
        )

    # -- R03 · no assertions (conditional) ---------------------------------
    if record(
        "R03",
        "Conditional where no outcome assertions were declared.",
        not assertions.assertions,
        f"{len(assertions.assertions)} assertions",
    ):
        if outcome is not ReadinessOutcome.FAIL:
            outcome = ReadinessOutcome.CONDITIONAL
        conditions.append(
            "No outcome assertions declared. Assertions must be added before "
            "build hand-off so the solution is monitorable against a system "
            "of record."
        )

    # -- R04 · unsourced service levels (conditional) ----------------------
    unsourced = [
        s for s in quality.scenarios if s.response_measure_value is None
    ]
    if record(
        "R04",
        "Conditional where a quality scenario lacks a numeric response measure.",
        bool(unsourced),
        f"{len(unsourced)} of {len(quality.scenarios)} scenarios unsourced",
    ):
        if outcome is not ReadinessOutcome.FAIL:
            outcome = ReadinessOutcome.CONDITIONAL
        conditions.append(
            f"{len(unsourced)} quality attribute scenario(s) lack a numeric "
            "response measure taken from an existing business commitment. "
            "Service levels must be sourced before component selection."
        )

    # -- R05 · absent ontology concepts (conditional) ----------------------
    if record(
        "R05",
        "Conditional where the ontology check found absent concepts.",
        bool(ontology.absent_concepts),
        f"{len(ontology.absent_concepts)} absent concepts",
    ):
        if outcome is not ReadinessOutcome.FAIL:
            outcome = ReadinessOutcome.CONDITIONAL
        conditions.append(
            "Business objects are not defined as ontology concepts. Gap flags "
            "routed to the Ontology Council; concepts must be defined before "
            "the design is published."
        )

    record(
        "R06",
        "Default outcome.",
        outcome is ReadinessOutcome.PASS,
        outcome.value,
    )

    logger.info("Readiness verdict: %s (%d conditions)", outcome.value, len(conditions))

    return ReadinessVerdict(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Readiness service",
        artifacts_consulted=[artifact.ref],
        outcome=outcome,
        conditions=conditions,
        rules_evaluated=evaluated,
    )
