"""FastAPI server — intake, run control and human gates.

Endpoint groups:

* ``/api/submissions``  steps 1-2: validate and persist, issue a tracking
  reference, start the derivation.
* ``/api/runs``         read the design pack, the timeline and the gates.
* ``/api/runs/.../gates`` answer a human decision point.
* ``/api/artifacts``    the fail-closed status board.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from contracts.envelope import RunStatus
from contracts.submission import Submission
from contracts.verdicts import (
    ArchitectReviewResponse,
    CoEReviewResponse,
    CriticalityConfirmationResponse,
    OwnerConfirmationResponse,
)
from knowledge.retrieval import ArtifactUnavailable, get_store
from runs import Run, manager, new_tracking_reference
import samples

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(name)-28s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="M42 Intake Agent",
    description="CAFE derivation, steps 3-22 (Phase 1)",
    version="0.1.0",
)

# A missing model provider must not silently produce placeholder design
# packs. It must also not crash-loop a container: a process that exits at
# import gives a deployment that hangs for twenty minutes and a log line
# nobody reads, which is worse to diagnose than a service that starts and
# says exactly what is wrong.
#
# So the guard refuses the *operation*, not the *process*. Health answers,
# the reason is visible, and no derivation can run.
try:
    settings.require_model_provider()
    _misconfiguration: str | None = None
except RuntimeError as exc:
    _misconfiguration = str(exc)

if _misconfiguration:
    logger.error("=" * 70)
    for line in _misconfiguration.splitlines():
        logger.error(line)
    logger.error("Submissions will be refused with HTTP 503 until resolved.")
    logger.error("=" * 70)
elif settings.has_model_provider:
    logger.info(
        "Model provider configured: %s (sampling controls %s)",
        settings.active_chat_model,
        "on" if settings.supports_sampling_controls else "off",
    )
else:
    logger.warning(
        "STUB MODE - ALLOW_STUB_AGENTS is set. The 14 agentic steps will "
        "return placeholder output marked is_stub. Not a derivation."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SubmissionRequest(BaseModel):
    """The Q0-Q30 form payload, minus the server-issued identifiers."""

    model_config = {"extra": "allow"}


class GateAnswer(BaseModel):
    request_id: str
    # Shape depends on the gate; validated against the concrete response
    # model once the gate type is known.
    payload: dict[str, Any]


def _run_summary(run: Run) -> dict[str, Any]:
    pack = run.pack
    case = pack.outputs.get("initial_business_case", {})
    return {
        "tracking_reference": pack.tracking_reference,
        "submission_id": pack.submission_id,
        "status": pack.status.value,
        "current_step": pack.current_step,
        "steps_completed": sorted(int(k) for k in pack.outputs if k.isdigit()),
        "gap_flag_count": len(pack.gap_flags),
        "loop_counts": pack.loop_counts,
        "awaiting_human": run.is_awaiting_human,
        "pending_gates": [
            {
                "request_id": p.request_id,
                "gate_type": p.gate_type,
                "data": p.data.model_dump(mode="json")
                if hasattr(p.data, "model_dump")
                else p.data,
            }
            for p in run.pending
        ],
        "recommendation": case.get("recommendation"),
        "annual_value": case.get("annual_value"),
        "error": run.error,
        "started_at": run.started_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Health and artifacts
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        # Deliberately still "ok": the service is up and answering. Whether
        # it can derive is a separate, explicit field - a probe must not
        # restart a container whose only problem is configuration.
        "status": "ok",
        "can_derive": _misconfiguration is None,
        "misconfiguration": _misconfiguration,
        "model_provider_configured": settings.has_model_provider,
        "mode": settings.mode,
        "model": settings.active_chat_model or None,
        # True only when stub mode was deliberately waived in, so a
        # placeholder run can never be mistaken for a real one.
        "stub_mode_waived": settings.allow_stub_agents
        and not settings.has_model_provider,
        # Whether reproducibility is backed by sampling controls or rests
        # on the schema gate and pinned retrieval alone. Reported rather
        # than assumed - a reasoning model cannot honour temperature/seed.
        "sampling_controls": (
            settings.supports_sampling_controls
            if settings.has_model_provider
            else None
        ),
        "fail_closed": settings.fail_closed,
        "seeds_allowed": settings.allow_seed_artifacts,
    }


@app.get("/api/artifacts")
async def artifacts() -> dict[str, Any]:
    """Fail-closed status board.

    Surfaces which governed artifacts are real and which are still seeds —
    the single most important operational question in Phase 1.
    """
    try:
        entries = get_store().describe()
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "artifacts": entries,
        "seed_count": sum(1 for e in entries if e["status"] == "seed"),
        "total": len(entries),
    }


# ---------------------------------------------------------------------------
# Example submissions
# ---------------------------------------------------------------------------

@app.get("/api/samples")
async def list_samples() -> dict[str, Any]:
    """Example submissions, for demonstrations and manual testing.

    Each one exercises a different path: proceed, reject at the
    feasibility gate, or proceed-with-conditions.
    """
    return {"samples": samples.list_samples()}


@app.get("/api/samples/{sample_id}")
async def get_sample(sample_id: str) -> dict[str, Any]:
    """A full submission payload, ready to post to /api/submissions."""
    payload = samples.get_sample(sample_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="unknown sample")
    return payload


# ---------------------------------------------------------------------------
# Steps 1-2 — receive, validate, persist, issue tracking reference
# ---------------------------------------------------------------------------

@app.post("/api/submissions")
async def create_submission(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a submission, then start the derivation.

    All channels converge here. Every later step reads the persisted
    record, never the channel, so the same submission produces the same
    derivation regardless of how it arrived.
    """
    if _misconfiguration:
        raise HTTPException(status_code=503, detail=_misconfiguration)

    payload.setdefault("submission_id", f"SUB-{uuid.uuid4().hex[:8].upper()}")
    payload.setdefault("tracking_reference", new_tracking_reference())

    try:
        submission = Submission.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run = await manager.start(submission)
    logger.info("submission %s accepted", submission.tracking_reference)
    return _run_summary(run)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@app.get("/api/runs")
async def list_runs() -> dict[str, Any]:
    return {"runs": [_run_summary(r) for r in manager.list_runs()]}


@app.get("/api/runs/{tracking_reference}")
async def get_run(tracking_reference: str) -> dict[str, Any]:
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")
    return _run_summary(run)


@app.get("/api/runs/{tracking_reference}/pack")
async def get_pack(tracking_reference: str) -> dict[str, Any]:
    """The full design pack — every step output with its provenance."""
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")
    return run.pack.model_dump(mode="json")


@app.get("/api/runs/{tracking_reference}/steps/{step}")
async def get_step_output(tracking_reference: str, step: int) -> dict[str, Any]:
    """One step's raw validated output.

    The run page renders this when a timeline row is expanded, so a
    reviewer can see exactly what any step produced rather than only the
    curated design pack. The envelope fields every step carries are split
    from the step's own payload, because the two answer different
    questions: the envelope says how far to trust the output, the payload
    is the output.
    """
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")

    output = run.pack.get(step)
    if output is None:
        raise HTTPException(
            status_code=404,
            detail=f"step {step} has not produced output in this run",
        )

    envelope_fields = {
        "step",
        "tier",
        "performed_by",
        "artifacts_consulted",
        "gap_flags",
        "requires_input",
        "produced_at",
        "is_stub",
    }

    return {
        "step": step,
        "envelope": {k: v for k, v in output.items() if k in envelope_fields},
        "payload": {k: v for k, v in output.items() if k not in envelope_fields},
    }


@app.get("/api/runs/{tracking_reference}/timeline")
async def get_timeline(tracking_reference: str) -> dict[str, Any]:
    """Per-step timeline for the run view.

    Carries the determinism tier and the seed/stub markers so a reviewer
    can see at a glance which parts of a derivation are real.
    """
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")

    steps = []
    for key in sorted((k for k in run.pack.outputs if k.isdigit()), key=int):
        output = run.pack.outputs[key]
        steps.append(
            {
                "step": int(key),
                "performed_by": output.get("performed_by"),
                "tier": output.get("tier"),
                "is_stub": output.get("is_stub", False),
                "gap_flags": len(output.get("gap_flags", [])),
                "requires_input": len(output.get("requires_input", [])),
                "artifacts": [
                    {
                        "id": a["artifact_id"],
                        "version": a["version"],
                        "is_seed": a["is_seed"],
                    }
                    for a in output.get("artifacts_consulted", [])
                ],
            }
        )

    return {
        "tracking_reference": tracking_reference,
        "status": run.pack.status.value,
        "steps": steps,
        "history": run.pack.history,
        "gap_flags": [g for g in run.pack.model_dump(mode="json")["gap_flags"]],
    }


@app.get("/api/runs/{tracking_reference}/design")
async def get_design(tracking_reference: str) -> dict[str, Any]:
    """The design pack, shaped for reading rather than for machines.

    This is the scoping-grade deliverable: capability coverage, reuse
    analysis, the workflow, risk classification, derived controls, the
    build surface, component selection and the composed architecture —
    plus the business case and the recommendation it supports.
    """
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")

    pack = run.pack
    get = pack.get

    use_case = get(3) or {}
    coverage = get(5) or {}
    realisation = get(6) or {}
    criticality = get(7) or {}
    feasibility = get(8) or {}
    quality = get(9) or {}
    workflow = get(11) or {}
    assertions = get(14) or {}
    readiness = get(15) or {}
    determinism = get(16) or {}
    risk = get(18) or {}
    controls = get(19) or {}
    surface = get(20) or {}
    components = get(21) or {}
    architecture = get(22) or {}

    return {
        "tracking_reference": tracking_reference,
        "status": pack.status.value,
        "is_complete": bool(architecture),
        "framing": {
            "problem_statement": use_case.get("problem_statement"),
            "accountable_owner": use_case.get("accountable_owner"),
            "expected_change": use_case.get("expected_change"),
        },
        "capability_coverage": {
            "matched": coverage.get("matches", []),
            "unmatched_functions": coverage.get("unmatched_functions", []),
        },
        "reuse": {
            "recommendation": realisation.get("reuse_recommendation"),
            "rationale": realisation.get("reuse_rationale"),
            "entries": realisation.get("entries", []),
        },
        "risk": {
            "criticality_band": criticality.get("band"),
            "dominant_failure_mode": criticality.get("dominant_failure_mode"),
            "per_step": risk.get("classes", []),
        },
        "gates": {
            "feasibility": {
                "outcome": feasibility.get("outcome"),
                "reasons": feasibility.get("reasons", []),
                "rules": feasibility.get("rules_evaluated", []),
            },
            "readiness": {
                "outcome": readiness.get("outcome"),
                "conditions": readiness.get("conditions", []),
            },
        },
        "workflow": {
            "nodes": workflow.get("nodes", []),
            "edges": workflow.get("edges", []),
            "governance_tier": determinism.get("governance_tier"),
        },
        "quality_attributes": quality.get("scenarios", []),
        "assertions": assertions.get("assertions", []),
        "controls": controls.get("obligations", []),
        "architecture": {
            "build_surface": surface.get("surface"),
            "build_surface_rationale": surface.get("rationale"),
            "conditional_obligations": surface.get("conditional_obligations", []),
            "components": components.get("components", []),
            "decision_records": components.get("decision_records", []),
            "conceptual": architecture.get("conceptual", {}),
            "logical": architecture.get("logical", {}),
            "physical": architecture.get("physical", {}),
            "conformance_validated": architecture.get("conformance_validated", False),
            "conformance_violations": architecture.get("conformance_violations", []),
        },
        "business_case": pack.outputs.get("initial_business_case", {}),
        "gap_flags": pack.model_dump(mode="json")["gap_flags"],
    }


# ---------------------------------------------------------------------------
# Human gates
# ---------------------------------------------------------------------------

_GATE_MODELS = {
    "OwnerConfirmationRequest": OwnerConfirmationResponse,
    "CoEReviewRequest": CoEReviewResponse,
    "CriticalityConfirmationRequest": CriticalityConfirmationResponse,
    "ArchitectReviewRequest": ArchitectReviewResponse,
}


@app.post("/api/runs/{tracking_reference}/gates")
async def answer_gate(tracking_reference: str, answer: GateAnswer) -> dict[str, Any]:
    """Answer a pending human decision and resume the derivation."""
    run = manager.get(tracking_reference)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown tracking reference")

    gate = next(
        (p for p in run.pending if p.request_id == answer.request_id), None
    )
    if gate is None:
        raise HTTPException(
            status_code=409,
            detail=f"no pending gate with request id {answer.request_id}",
        )

    model = _GATE_MODELS.get(gate.gate_type)
    if model is None:
        raise HTTPException(
            status_code=500, detail=f"unhandled gate type {gate.gate_type}"
        )

    try:
        response = model.model_validate(answer.payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run = await manager.respond(tracking_reference, answer.request_id, response)
    return _run_summary(run)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
