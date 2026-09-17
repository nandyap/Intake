"""Executors — the nodes of the static derivation graph.

Every executor follows the same contract:

* takes the :class:`DesignPack` as its message,
* reads only from the pack (never from the channel),
* writes exactly one schema-validated :class:`StepOutput` back to it,
* forwards the pack to the next node.

This uniform message type is what lets the graph be declared statically
while still carrying accumulating state. The edges — not the executors —
decide what runs next, which is what keeps the solution guided-stochastic.

Note: this module deliberately does NOT use ``from __future__ import
annotations``. MAF introspects handler signatures at decoration time and
needs real type objects, not strings.
"""

import logging
from typing import Any

from agent_framework import Executor, WorkflowContext, handler, response_handler

from contracts.envelope import DesignPack, RunStatus
from contracts.verdicts import (
    ArchitectReviewRequest,
    ArchitectReviewResponse,
    CoEReviewRequest,
    CoEReviewResponse,
    CriticalityConfirmationRequest,
    CriticalityConfirmationResponse,
    OwnerConfirmationRequest,
    OwnerConfirmationResponse,
    ReviewDecision,
)

logger = logging.getLogger(__name__)

# Declared cycles must be bounded — an unbounded loop is an availability
# risk even when it is statically declared.
MAX_LOOP_TRAVERSALS = 3


class StepExecutor(Executor):
    """Base class for one derivation step.

    Subclasses implement :meth:`derive`. Error handling, provenance and
    forwarding live here so no step can accidentally skip them.
    """

    step_number: int = 0
    step_name: str = ""

    def __init__(self, step_number: int, step_name: str, id: str | None = None):
        self.step_number = step_number
        self.step_name = step_name
        super().__init__(id=id or f"step_{step_number}")

    async def derive(self, pack: DesignPack) -> Any:
        """Produce this step's output. Implemented by subclasses."""
        raise NotImplementedError

    @handler
    async def run_step(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        logger.info(
            "[%s] step %d · %s",
            pack.tracking_reference,
            self.step_number,
            self.step_name,
        )
        pack.status = RunStatus.RUNNING
        try:
            output = await self.derive(pack)
        except Exception as exc:
            # Fail closed: a step that cannot produce validated output does
            # not silently pass a default downstream.
            logger.exception(
                "[%s] step %d failed", pack.tracking_reference, self.step_number
            )
            pack.status = RunStatus.FAILED
            pack.history.append(f"step {self.step_number} FAILED: {exc}")
            await ctx.yield_output(pack)
            return

        pack.record(self.step_number, output)
        await ctx.send_message(pack)


# ---------------------------------------------------------------------------
# Human-in-the-loop gates
# ---------------------------------------------------------------------------


async def _snapshot(pack: DesignPack, ctx: WorkflowContext[DesignPack]) -> None:
    """Save the pack for the response handler and publish it to readers.

    ``set_state`` is what this gate's response handler resumes from.
    ``yield_output`` is what the run page reads *while the run is paused* —
    without it the API keeps serving the pack as it was when the workflow
    last produced output, so a run waiting at the architect gate still
    reports a single completed step.

    Every gate must do both. A gate that saves but does not publish leaves
    the caller reading stale progress.
    """
    ctx.set_state("pack", pack.model_dump(mode="json"))
    await ctx.yield_output(pack)


class OwnerConfirmationGate(Executor):
    """Sponsor stage 1 — the business owner confirms objective and value.

    Placed immediately after framing so the expensive derivation never runs
    on an objective the owner does not recognise.
    """

    def __init__(self, id: str = "gate_owner_confirmation"):
        super().__init__(id=id)

    @handler
    async def request(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        use_case = pack.get(3) or {}
        pack.status = RunStatus.AWAITING_OWNER_CONFIRMATION
        await _snapshot(pack, ctx)

        await ctx.request_info(
            request_data=OwnerConfirmationRequest(
                tracking_reference=pack.tracking_reference,
                problem_statement=use_case.get("problem_statement", ""),
                accountable_owner=use_case.get("accountable_owner", ""),
                expected_change=use_case.get("expected_change", ""),
                stated_objective=use_case.get("expected_change", ""),
                estimated_annual_benefit_aed=pack.outputs.get(
                    "submission_benefit_estimate"
                ),
            ),
            response_type=OwnerConfirmationResponse,
        )

    @response_handler
    async def on_response(
        self,
        original_request: OwnerConfirmationRequest,
        response: OwnerConfirmationResponse,
        ctx: WorkflowContext[DesignPack],
    ) -> None:
        pack = DesignPack.model_validate(ctx.get_state("pack"))

        if response.confirmed:
            pack.status = RunStatus.RUNNING
            pack.history.append(
                f"owner confirmed objective ({response.confirmed_by or 'unnamed'})"
            )
        else:
            count = pack.bump_loop("owner_confirmation")
            pack.history.append(
                f"owner requested corrections (loop {count}): {response.corrections}"
            )
            pack.outputs["owner_corrections"] = response.corrections
            if count > MAX_LOOP_TRAVERSALS:
                pack.status = RunStatus.REJECTED
                pack.history.append(
                    "owner confirmation loop exhausted — closing submission"
                )

        pack.outputs["owner_confirmation"] = response.model_dump(mode="json")
        await ctx.send_message(pack)


class CoEReviewGate(Executor):
    """Sponsor stage 2 — the analysis report goes to the AI CoE.

    Accept, reject, or return for further information. The return path is
    a declared loop back to framing.
    """

    def __init__(self, id: str = "gate_coe_review"):
        super().__init__(id=id)

    @handler
    async def request(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        verdict = pack.get(8) or {}
        criticality = pack.get(7) or {}
        realisation = pack.get(6) or {}
        business_case = pack.outputs.get("initial_business_case", {})

        pack.status = RunStatus.AWAITING_COE_REVIEW
        await _snapshot(pack, ctx)

        await ctx.request_info(
            request_data=CoEReviewRequest(
                tracking_reference=pack.tracking_reference,
                feasibility_outcome=verdict.get("outcome", "proceed"),
                criticality_band=criticality.get("band", "unknown"),
                reuse_recommendation=realisation.get("reuse_recommendation", "build"),
                initial_business_case=business_case,
                unresolved_inputs=[
                    r["field_name"] for r in verdict.get("requires_input", [])
                ],
            ),
            response_type=CoEReviewResponse,
        )

    @response_handler
    async def on_response(
        self,
        original_request: CoEReviewRequest,
        response: CoEReviewResponse,
        ctx: WorkflowContext[DesignPack],
    ) -> None:
        pack = DesignPack.model_validate(ctx.get_state("pack"))
        pack.outputs["coe_review"] = response.model_dump(mode="json")

        if response.decision is ReviewDecision.APPROVE:
            pack.status = RunStatus.RUNNING
            pack.history.append(f"AI CoE accepted ({response.reviewed_by or 'unnamed'})")
        elif response.decision is ReviewDecision.RETURN_FOR_INFO:
            count = pack.bump_loop("coe_return_for_info")
            pack.history.append(
                f"AI CoE returned for information (loop {count}): "
                f"{', '.join(response.information_requested) or response.notes}"
            )
            if count > MAX_LOOP_TRAVERSALS:
                pack.status = RunStatus.REJECTED
                pack.history.append("CoE return loop exhausted — closing submission")
        else:
            pack.status = RunStatus.REJECTED
            pack.history.append(f"AI CoE rejected: {response.notes}")

        await ctx.send_message(pack)


class CriticalityGate(Executor):
    """Step 13 — the architect confirms the criticality class.

    The diagram marks step 13 a human decision, and the reason is
    structural: the criticality class sets the control rigour that steps
    18, 19 and 21 derive from. A class proposed by an agent and never seen
    by a person would let the whole control set rest on an unreviewed
    judgement.

    The architect may confirm the proposed class or substitute a different
    one. A substitution is a decision, not a correction, so this gate has
    no loop back — the corrected class simply replaces the proposed one and
    the derivation continues with it.
    """

    def __init__(self, id: str = "gate_criticality"):
        super().__init__(id=id)

    @handler
    async def request(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        confirmation = pack.get(13) or {}
        provisional = pack.get(7) or {}
        workflow = pack.get(11) or {}

        branches = {
            str(k): str(v)
            for k, v in (confirmation.get("class_per_branch") or {}).items()
        }
        proposed = branches.get("default") or provisional.get("band", "")

        pack.status = RunStatus.AWAITING_CRITICALITY_CONFIRMATION
        await _snapshot(pack, ctx)

        await ctx.request_info(
            request_data=CriticalityConfirmationRequest(
                tracking_reference=pack.tracking_reference,
                proposed_class=proposed,
                provisional_band=provisional.get("band", ""),
                is_homogeneous=bool(confirmation.get("is_homogeneous", True)),
                class_per_branch=branches,
                dominant_failure_mode=provisional.get("dominant_failure_mode", ""),
                workflow_node_count=len(workflow.get("nodes", [])),
            ),
            response_type=CriticalityConfirmationResponse,
        )

    @response_handler
    async def on_response(
        self,
        original_request: CriticalityConfirmationRequest,
        response: CriticalityConfirmationResponse,
        ctx: WorkflowContext[DesignPack],
    ) -> None:
        pack = DesignPack.model_validate(ctx.get_state("pack"))
        pack.outputs["criticality_confirmation"] = response.model_dump(mode="json")

        if not response.confirmed:
            pack.status = RunStatus.REJECTED
            pack.history.append(
                f"architect did not confirm the criticality class: {response.notes}"
            )
            await ctx.send_message(pack)
            return

        confirmation = pack.get(13) or {}
        chosen = response.confirmed_class or original_request.proposed_class

        if chosen != original_request.proposed_class:
            confirmation["class_per_branch"] = {"default": chosen}
            confirmation["is_homogeneous"] = True
            pack.history.append(
                f"architect substituted criticality class "
                f"{original_request.proposed_class or 'none'} -> {chosen} "
                f"({response.confirmed_by or 'unnamed'})"
            )
        else:
            pack.history.append(
                f"architect confirmed criticality class {chosen} "
                f"({response.confirmed_by or 'unnamed'})"
            )

        # The flag the readiness service reads. Only a human sets it.
        confirmation["architect_confirmed"] = True
        pack.outputs["13"] = confirmation
        pack.status = RunStatus.RUNNING

        await ctx.send_message(pack)


class ArchitectReviewGate(Executor):
    """Sponsor stage 3 — an architect approves, rejects or re-prompts.

    Any divergence between the proposal and the original request goes back
    to the business owner before work continues.
    """

    def __init__(self, id: str = "gate_architect_review"):
        super().__init__(id=id)

    @handler
    async def request(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        architecture = pack.get(22) or {}
        surface = pack.get(20) or {}
        components = pack.get(21) or {}
        controls = pack.get(19) or {}

        pack.status = RunStatus.AWAITING_ARCHITECT_REVIEW
        await _snapshot(pack, ctx)

        await ctx.request_info(
            request_data=ArchitectReviewRequest(
                tracking_reference=pack.tracking_reference,
                build_surface=surface.get("surface", "unknown"),
                component_count=len(components.get("components", [])),
                obligation_count=len(controls.get("obligations", [])),
                conformance_validated=architecture.get("conformance_validated", False),
                conformance_violations=architecture.get("conformance_violations", []),
                divergences=_detect_divergences(pack),
            ),
            response_type=ArchitectReviewResponse,
        )

    @response_handler
    async def on_response(
        self,
        original_request: ArchitectReviewRequest,
        response: ArchitectReviewResponse,
        ctx: WorkflowContext[DesignPack],
    ) -> None:
        pack = DesignPack.model_validate(ctx.get_state("pack"))
        pack.outputs["architect_review"] = response.model_dump(mode="json")

        if response.decision is ReviewDecision.RE_PROMPT:
            count = pack.bump_loop("architect_re_prompt")
            pack.outputs["re_prompt_guidance"] = response.re_prompt_guidance
            pack.history.append(
                f"architect re-prompted (loop {count}): {response.re_prompt_guidance}"
            )
            if count > MAX_LOOP_TRAVERSALS:
                pack.status = RunStatus.REJECTED
                pack.history.append("re-prompt loop exhausted — closing submission")
        elif response.decision is ReviewDecision.APPROVE:
            if original_request.divergences:
                # A divergence cannot be waved through by the architect —
                # it belongs to the business owner.
                pack.status = RunStatus.AWAITING_DIVERGENCE_APPROVAL
                pack.history.append(
                    f"architect approved with {len(original_request.divergences)} "
                    "divergence(s) — routing to business owner"
                )
            else:
                pack.status = RunStatus.COMPLETED
                pack.history.append(
                    f"architect approved ({response.reviewed_by or 'unnamed'})"
                )
        else:
            pack.status = RunStatus.REJECTED
            pack.history.append(f"architect rejected: {response.notes}")

        await ctx.send_message(pack)


class DivergenceGate(Executor):
    """The business owner approves any divergence from the original request."""

    def __init__(self, id: str = "gate_divergence"):
        super().__init__(id=id)

    @handler
    async def request(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack]
    ) -> None:
        if pack.status is not RunStatus.AWAITING_DIVERGENCE_APPROVAL:
            # No divergence — pass straight through.
            await ctx.yield_output(pack)
            return

        use_case = pack.get(3) or {}
        await _snapshot(pack, ctx)
        await ctx.request_info(
            request_data=OwnerConfirmationRequest(
                tracking_reference=pack.tracking_reference,
                problem_statement=use_case.get("problem_statement", ""),
                accountable_owner=use_case.get("accountable_owner", ""),
                expected_change=use_case.get("expected_change", ""),
                stated_objective="; ".join(_detect_divergences(pack)),
                prompt=(
                    "The proposed solution diverges from the original request. "
                    "Approve the divergence to continue, or reject to return "
                    "the use case for reframing."
                ),
            ),
            response_type=OwnerConfirmationResponse,
        )

    @response_handler
    async def on_response(
        self,
        original_request: OwnerConfirmationRequest,
        response: OwnerConfirmationResponse,
        ctx: WorkflowContext[DesignPack],
    ) -> None:
        pack = DesignPack.model_validate(ctx.get_state("pack"))
        pack.outputs["divergence_approval"] = response.model_dump(mode="json")

        if response.confirmed:
            pack.status = RunStatus.COMPLETED
            pack.history.append(
                f"business owner approved divergence "
                f"({response.confirmed_by or 'unnamed'})"
            )
        else:
            count = pack.bump_loop("divergence_rejected")
            pack.history.append(
                f"business owner rejected divergence (loop {count}) — "
                "returning for reframing"
            )
            if count > MAX_LOOP_TRAVERSALS:
                pack.status = RunStatus.REJECTED

        await ctx.send_message(pack)


class TerminalExecutor(Executor):
    """Absorbs a run that ended early — rejected, integration, or failed."""

    def __init__(self, id: str = "terminal"):
        super().__init__(id=id)

    @handler
    async def finish(
        self, pack: DesignPack, ctx: WorkflowContext[DesignPack, DesignPack]
    ) -> None:
        logger.info(
            "[%s] run finished: %s", pack.tracking_reference, pack.status.value
        )
        await ctx.yield_output(pack)


def _detect_divergences(pack: DesignPack) -> list[str]:
    """Compare the proposal against what the business owner asked for.

    Sponsor directive: "Any divergence between the proposal and the
    original request should go back to the business owner for approval
    before the work continues."
    """
    divergences: list[str] = []

    realisation = pack.get(6) or {}
    if realisation.get("reuse_recommendation") in {"reuse", "integrate"}:
        divergences.append(
            "The request asked for a build; the analysis recommends reusing "
            "or integrating an existing realisation."
        )

    surface = pack.get(20) or {}
    if surface.get("obligations_incumbent_failed"):
        divergences.append(
            "An incumbent platform was evaluated and rejected on "
            f"{len(surface['obligations_incumbent_failed'])} obligation(s), "
            "changing the delivery surface from what was requested."
        )

    architecture = pack.get(22) or {}
    if architecture.get("conformance_violations"):
        divergences.append(
            f"The composed architecture carries "
            f"{len(architecture['conformance_violations'])} conformance "
            "violation(s) requiring an addendum."
        )

    coverage = pack.get(5) or {}
    if coverage.get("unmatched_functions"):
        divergences.append(
            f"{len(coverage['unmatched_functions'])} requested business "
            "function(s) have no matching capability and are not covered by "
            "the proposed solution."
        )

    return divergences
