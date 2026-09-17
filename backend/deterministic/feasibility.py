"""Step 8 — Feasibility verdict (D0).

Placed after the cheap derivations (3-7) and before the expensive ones, so
spend stops early on use cases that will not proceed.  Its inputs are
derived, not estimated, which is what makes the verdict deterministic.

Rule F01 is a sponsor directive, not a seed: a use case where an error
would cause severe or permanent harm is rejected even where an agent could
technically perform it.
"""

from __future__ import annotations

import logging

from contracts.envelope import DeterminismTier, GapFlagType, RequiresInput
from contracts.steps import (
    CoverageMap,
    CriticalityBandOutput,
    RealisationMatch,
    ReuseRecommendation,
    UseCaseRecord,
)
from contracts.submission import DataReadiness, FailureImpact, Submission
from contracts.verdicts import (
    FeasibilityOutcome,
    FeasibilityVerdict,
    RuleOutcome,
    RuleProvenance,
)
from knowledge.retrieval import get_store

logger = logging.getLogger(__name__)

STEP = 8
ARTIFACT_ID = "feasibility-rules"

# The governed artifacts two of these rules need in order to be
# answerable at all. Neither exists yet; both are M42 deliverables.
#
# A rule is only evaluated when the evidence it reasons over is present.
# Asking the store is deliberate: a stub honestly reports a missing
# artifact, but a live agent handed nothing still answers confidently and
# raises no flag, so a rule keyed off the agent's admission stops firing
# precisely when real agents are switched on.
_CAPABILITY_MAP = "business-capability-map"
_AS_IS_ARCHITECTURE = "ai-as-is-architecture"

# Terminal outcomes short-circuit the verdict but every rule still
# evaluates, so the audit trail shows what was considered.
_TERMINAL = {FeasibilityOutcome.REJECT, FeasibilityOutcome.RETURN_AS_INTEGRATION}


def evaluate(
    submission: Submission,
    use_case: UseCaseRecord,
    coverage: CoverageMap,
    realisation: RealisationMatch,
    criticality: CriticalityBandOutput,
) -> FeasibilityVerdict:
    """Produce the feasibility verdict.

    Raises:
        ArtifactUnavailable: the rule set could not be resolved. Fail-closed
            is intentional — a gate with no rules must not pass anything.
    """
    artifact = get_store().resolve(ARTIFACT_ID)
    store = get_store()

    evaluated: list[RuleOutcome] = []
    reasons: list[str] = []
    requires_input: list[RequiresInput] = []
    outcome = FeasibilityOutcome.PROCEED
    decided = False

    # -- F01 · sponsor directive · severe or permanent harm ---------------
    f01 = submission.q22_failure_impact is FailureImpact.CRITICAL
    evaluated.append(
        RuleOutcome(
            rule_id="F01",
            description=(
                "Reject where an error would cause severe or permanent harm, "
                "even where an agent could technically perform the task."
            ),
            provenance=RuleProvenance.SPONSOR_DIRECTIVE,
            triggered=f01,
            detail=f"Q22 failure impact = {submission.q22_failure_impact.value}",
        )
    )
    if f01 and not decided:
        outcome = FeasibilityOutcome.REJECT
        decided = True
        reasons.append(
            "Failure impact is Critical: an error would cause severe or "
            "permanent harm. Rejected on error tolerance regardless of "
            "technical feasibility."
        )

    # -- F02 · an existing block already realises this ---------------------
    # Answerable only where an as-is architecture exists to verify the
    # claim against. Step 6 declares no governed artifact, so today the
    # reuse route is a proposal for a human to check, not a verdict.
    as_is_missing = not store.is_available(_AS_IS_ARCHITECTURE)
    proposes_reuse = realisation.reuse_recommendation in {
        ReuseRecommendation.REUSE,
        ReuseRecommendation.INTEGRATE,
    }
    f02 = proposes_reuse and not as_is_missing
    evaluated.append(
        RuleOutcome(
            rule_id="F02",
            description="Return as integration where an existing block already realises the capability.",
            provenance=RuleProvenance.SEED,
            triggered=f02,
            detail=(
                "not evaluated — no as-is architecture was available to "
                f"verify the proposed route "
                f"({realisation.reuse_recommendation.value})"
                if as_is_missing
                else f"Reuse recommendation = {realisation.reuse_recommendation.value}"
            ),
        )
    )
    if f02 and not decided:
        outcome = FeasibilityOutcome.RETURN_AS_INTEGRATION
        decided = True
        reasons.append(
            "An existing realisation already covers this capability: "
            f"{realisation.reuse_rationale or 'see realisation match'}. "
            "This is an integration, not a build."
        )
    elif as_is_missing and proposes_reuse:
        # Not a verdict, but the reviewer must see the claim.
        requires_input.append(
            RequiresInput(
                field_name="reuse_recommendation",
                reason=(
                    "A reuse or integration route was proposed "
                    f"({realisation.reuse_recommendation.value}), but no "
                    "as-is architecture was available to verify that an "
                    "existing block realises this capability."
                ),
                gate_condition=(
                    "Confirm the reuse claim against the AI and traditional "
                    "as-is architectures before committing to a build."
                ),
            )
        )

    # -- F03 · framing rejection ------------------------------------------
    f03 = use_case.framing_rejection is not None
    evaluated.append(
        RuleOutcome(
            rule_id="F03",
            description="Reject where the problem was stated as a solution, or accountability is shared.",
            provenance=RuleProvenance.SEED,
            triggered=f03,
            detail=use_case.framing_rejection or "framing accepted",
        )
    )
    if f03 and not decided:
        outcome = FeasibilityOutcome.REJECT
        decided = True
        reasons.append(f"Framing rejected: {use_case.framing_rejection}")

    # -- F04 · no capability matched in either direction -------------------
    # A use case cannot be rejected for failing to match against an artifact
    # that does not exist. Where the capability map itself is missing, that
    # is a gap flag and a gate condition — not a verdict on the submission.
    #
    # The store is asked directly rather than trusting the step to have
    # flagged it: the stub raises MISSING_ARTIFACT, a live agent does not,
    # and this rule must behave identically in both modes.
    capability_map_missing = not store.is_available(_CAPABILITY_MAP) or any(
        flag.flag_type is GapFlagType.MISSING_ARTIFACT for flag in coverage.gap_flags
    )
    f04 = (
        not coverage.matches
        and bool(coverage.unmatched_functions)
        and not capability_map_missing
    )
    evaluated.append(
        RuleOutcome(
            rule_id="F04",
            description="Reject where no business function matched any capability.",
            provenance=RuleProvenance.SEED,
            triggered=f04,
            detail=(
                "not evaluated — the business capability map was not available"
                if capability_map_missing
                else (
                    f"{len(coverage.matches)} matched, "
                    f"{len(coverage.unmatched_functions)} unmatched"
                )
            ),
        )
    )
    if f04 and not decided:
        outcome = FeasibilityOutcome.REJECT
        decided = True
        reasons.append(
            "No business function could be matched to an L3 capability. "
            "The use case sits outside the current capability map."
        )
    elif capability_map_missing:
        requires_input.append(
            RequiresInput(
                field_name="business_capability_map",
                reason=(
                    "The business capability map (L1-L3) was not available, so "
                    "capability coverage could not be assessed."
                ),
                gate_condition=(
                    "Capability coverage must be re-assessed once M42 provides "
                    "the business capability map. This verdict is provisional "
                    "on that assessment."
                ),
            )
        )

    # -- F05 · data not digitally available (gate condition, not a stop) ---
    f05 = submission.q24_data_readiness is DataReadiness.NOT_READY
    evaluated.append(
        RuleOutcome(
            rule_id="F05",
            description="Flag, do not reject, where data is not digitally available.",
            provenance=RuleProvenance.SEED,
            triggered=f05,
            detail=f"Q24 = {submission.q24_data_readiness.value}",
        )
    )
    if f05:
        requires_input.append(
            RequiresInput(
                field_name="q24_data_readiness",
                reason="Data is not digitally available.",
                gate_condition=(
                    "A data-readiness workstream must precede build. The "
                    "year-1 operational saving carries the Appendix B discount."
                ),
            )
        )

    # -- F06 · default ------------------------------------------------------
    evaluated.append(
        RuleOutcome(
            rule_id="F06",
            description="Default outcome when no terminal rule triggers.",
            provenance=RuleProvenance.SEED,
            triggered=not decided,
            detail="proceed" if not decided else "superseded by an earlier rule",
        )
    )
    if not decided:
        reasons.append(
            "Cheap derivation completed with a matched capability, a single "
            "accountable owner and a tolerable failure impact."
        )

    logger.info(
        "Feasibility verdict for %s: %s (%d rules evaluated)",
        submission.tracking_reference,
        outcome.value,
        len(evaluated),
    )

    return FeasibilityVerdict(
        step=STEP,
        tier=DeterminismTier.D0,
        performed_by="Feasibility service",
        artifacts_consulted=[artifact.ref],
        requires_input=requires_input,
        outcome=outcome,
        reasons=reasons,
        rules_evaluated=evaluated,
    )
