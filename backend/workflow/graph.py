"""The static derivation graph — steps 3 to 22.

This module *is* the process. Every transition is declared here at build
time; no executor and no model chooses what runs next. That is what keeps
the solution guided-stochastic: an orchestrator selecting its own next
step would be open-stochastic and would take the whole solution to Board
approval.

Three cycles are declared, all bounded:

1. ``owner_confirmation``   — owner asks for corrections, return to 3
2. ``coe_return_for_info``  — AI CoE returns for information, return to 3
3. ``architect_re_prompt``  — architect re-prompts, return to 16
   (and divergence rejected, return to 3)

Declared cycles are legal. Runtime step selection is not.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import Workflow, WorkflowBuilder

from contracts.envelope import DesignPack, RunStatus
from contracts.verdicts import FeasibilityOutcome, ReadinessOutcome
from workflow.executors import (
    ArchitectReviewGate,
    CoEReviewGate,
    CriticalityGate,
    DivergenceGate,
    OwnerConfirmationGate,
    TerminalExecutor,
)
from workflow.steps import (
    AssignCriticalityBand,
    AssignFacetVectors,
    CheckOntology,
    ClassifyDeterminism,
    ComposeArchitecture,
    ConfirmCriticality,
    DeclareAssertions,
    DecomposeElements,
    DeriveQualityAttributes,
    DeriveRisk,
    EvaluateObligations,
    FeasibilityGate,
    FrameUseCase,
    MatchCapabilities,
    MatchRealisations,
    ReadinessGate,
    SelectBuildSurface,
    SelectComponents,
    SequenceWorkflow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Edge conditions — pure predicates over the design pack
# ---------------------------------------------------------------------------

def _is_pack(msg: Any) -> bool:
    return isinstance(msg, DesignPack)


def _terminated(msg: Any) -> bool:
    """A run that ended early must not continue down the main spine."""
    return _is_pack(msg) and msg.status in {
        RunStatus.REJECTED,
        RunStatus.RETURNED_AS_INTEGRATION,
        RunStatus.FAILED,
        RunStatus.COMPLETED,
    }


def _running(msg: Any) -> bool:
    return _is_pack(msg) and not _terminated(msg)


def _owner_confirmed(msg: Any) -> bool:
    if not _running(msg):
        return False
    return bool((msg.outputs.get("owner_confirmation") or {}).get("confirmed"))


def _owner_wants_changes(msg: Any) -> bool:
    if not _is_pack(msg) or _terminated(msg):
        return False
    confirmation = msg.outputs.get("owner_confirmation")
    return confirmation is not None and not confirmation.get("confirmed")


def _feasibility_is(outcome: FeasibilityOutcome):
    def predicate(msg: Any) -> bool:
        if not _running(msg):
            return False
        verdict = msg.get(8)
        return bool(verdict) and verdict.get("outcome") == outcome.value

    return predicate


def _feasibility_stops(msg: Any) -> bool:
    """Reject or return-as-integration — both end the run at step 8.

    MAF requires each edge to be unique, so the two terminal outcomes share
    one edge; the verdict itself records which of them fired.
    """
    if not _is_pack(msg):
        return False
    verdict = msg.get(8)
    return bool(verdict) and verdict.get("outcome") in {
        FeasibilityOutcome.REJECT.value,
        FeasibilityOutcome.RETURN_AS_INTEGRATION.value,
    }


def _coe_accepted(msg: Any) -> bool:
    if not _running(msg):
        return False
    return (msg.outputs.get("coe_review") or {}).get("decision") == "approve"


def _coe_returned(msg: Any) -> bool:
    if not _is_pack(msg) or _terminated(msg):
        return False
    return (msg.outputs.get("coe_review") or {}).get("decision") == "return_for_info"


def _readiness_ok(msg: Any) -> bool:
    if not _running(msg):
        return False
    verdict = msg.get(15)
    return bool(verdict) and verdict.get("outcome") in {
        ReadinessOutcome.PASS.value,
        ReadinessOutcome.CONDITIONAL.value,
    }


def _readiness_failed(msg: Any) -> bool:
    if not _is_pack(msg):
        return False
    verdict = msg.get(15)
    return bool(verdict) and verdict.get("outcome") == ReadinessOutcome.FAIL.value


def _criticality_confirmed(msg: Any) -> bool:
    if not _running(msg):
        return False
    return bool(
        (msg.outputs.get("criticality_confirmation") or {}).get("confirmed")
    )


def _architect_re_prompted(msg: Any) -> bool:
    if not _is_pack(msg) or msg.status is RunStatus.REJECTED:
        return False
    return (msg.outputs.get("architect_review") or {}).get("decision") == "re_prompt"


def _needs_divergence_approval(msg: Any) -> bool:
    return (
        _is_pack(msg)
        and msg.status is RunStatus.AWAITING_DIVERGENCE_APPROVAL
    )


def _architect_settled(msg: Any) -> bool:
    """Approved with no divergence, or rejected — either way, done."""
    if not _is_pack(msg):
        return False
    if _architect_re_prompted(msg) or _needs_divergence_approval(msg):
        return False
    return msg.outputs.get("architect_review") is not None


def _divergence_rejected(msg: Any) -> bool:
    if not _is_pack(msg) or msg.status is RunStatus.REJECTED:
        return False
    approval = msg.outputs.get("divergence_approval")
    return approval is not None and not approval.get("confirmed")


def _divergence_settled(msg: Any) -> bool:
    if not _is_pack(msg):
        return False
    return msg.status in {RunStatus.COMPLETED, RunStatus.REJECTED}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(
    agents: dict[int, Any] | None = None,
    checkpoint_storage: Any = None,
) -> Workflow:
    """Declare and build the static derivation graph.

    Args:
        agents: step number -> MAF agent. Any step without an entry runs
            as a schema-valid stub, which is the Sprint 1 mode.
        checkpoint_storage: MAF checkpoint store (Cosmos in production) so
            a paused or interrupted run resumes at the exact step.
    """
    agents = agents or {}

    # --- nodes -----------------------------------------------------------
    s3 = FrameUseCase(agents.get(3))
    owner_gate = OwnerConfirmationGate()
    s4 = DecomposeElements(agents.get(4))
    s5 = MatchCapabilities(agents.get(5))
    s6 = MatchRealisations(agents.get(6))
    s7 = AssignCriticalityBand(agents.get(7))
    s8 = FeasibilityGate()
    coe_gate = CoEReviewGate()
    s9 = DeriveQualityAttributes(agents.get(9))
    s10 = CheckOntology(agents.get(10))
    s11 = SequenceWorkflow(agents.get(11))
    s13 = ConfirmCriticality(agents.get(13))
    criticality_gate = CriticalityGate()
    s14 = DeclareAssertions(agents.get(14))
    s15 = ReadinessGate()
    s16 = ClassifyDeterminism(agents.get(16))
    s17 = AssignFacetVectors(agents.get(17))
    s18 = DeriveRisk()
    s19 = EvaluateObligations()
    s20 = SelectBuildSurface(agents.get(20))
    s21 = SelectComponents(agents.get(21))
    s22 = ComposeArchitecture()
    architect_gate = ArchitectReviewGate()
    divergence_gate = DivergenceGate()
    terminal = TerminalExecutor()

    builder = WorkflowBuilder(
        start_executor=s3,
        name="m42-intake-derivation",
        description="CAFE derivation, steps 3-22 (Phase 1)",
        checkpoint_storage=checkpoint_storage,
        max_iterations=200,
    )

    # --- stretch 1: framing and owner confirmation ------------------------
    builder.add_edge(s3, owner_gate)
    # LOOP 1 — owner asks for corrections
    builder.add_edge(owner_gate, s3, condition=_owner_wants_changes)
    builder.add_edge(owner_gate, s4, condition=_owner_confirmed)
    builder.add_edge(owner_gate, terminal, condition=_terminated)

    # --- stretch 2: cheap derivation to the feasibility gate --------------
    builder.add_chain([s4, s5, s6, s7, s8])

    # --- the feasibility gate: three deterministic outcomes ---------------
    builder.add_edge(s8, coe_gate, condition=_feasibility_is(FeasibilityOutcome.PROCEED))
    builder.add_edge(s8, terminal, condition=_feasibility_stops)

    # --- the AI CoE review ------------------------------------------------
    # LOOP 2 — returned for further information
    builder.add_edge(coe_gate, s3, condition=_coe_returned)
    builder.add_edge(coe_gate, s9, condition=_coe_accepted)
    builder.add_edge(coe_gate, terminal, condition=_terminated)

    # --- stretch 3: deep derivation to the readiness gate -----------------
    # Step 12 (Contract sources) is deferred — no green inputs in Phase 1.
    builder.add_chain([s9, s10, s11, s13])

    # The criticality class sets the control rigour for steps 18, 19 and 21,
    # so the diagram marks step 13 a human decision. Readiness rule R02
    # fails closed if this gate has not set ``architect_confirmed``.
    builder.add_edge(s13, criticality_gate)
    builder.add_edge(criticality_gate, s14, condition=_criticality_confirmed)
    builder.add_edge(criticality_gate, terminal, condition=_terminated)

    builder.add_chain([s14, s15])

    builder.add_edge(s15, s16, condition=_readiness_ok)
    builder.add_edge(s15, terminal, condition=_readiness_failed)

    # --- stretch 4: risk, controls, surface, components, composition ------
    # Risk assessment precedes solution design so the design inherits its
    # guardrails — confirmed by the sponsor, and the v2.5 ordering.
    builder.add_chain([s16, s17, s18, s19, s20, s21, s22])

    # --- stretch 5: architect review and divergence -----------------------
    builder.add_edge(s22, architect_gate)
    # LOOP 3 — architect re-prompts the derivation
    builder.add_edge(architect_gate, s16, condition=_architect_re_prompted)
    builder.add_edge(
        architect_gate, divergence_gate, condition=_needs_divergence_approval
    )
    builder.add_edge(architect_gate, terminal, condition=_architect_settled)

    # LOOP 3b — owner rejects the divergence, back to reframing
    builder.add_edge(divergence_gate, s3, condition=_divergence_rejected)
    builder.add_edge(divergence_gate, terminal, condition=_divergence_settled)

    workflow = builder.build()
    logger.info(
        "Derivation graph built: 19 steps (3-22, less deferred step 12), "
        "5 gates, 4 declared cycles, %d agent(s) wired (rest run as stubs)",
        len(agents),
    )
    return workflow
