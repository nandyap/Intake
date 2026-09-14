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
    OwnerConfirmationResponse,
)
from knowledge.retrieval import ArtifactUnavailable, get_store
from runs import Run, manager, new_tracking_reference

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
        "status": "ok",
        "model_provider_configured": settings.has_model_provider,
        "mode": "agents" if settings.has_model_provider else "stub",
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
# Steps 1-2 — receive, validate, persist, issue tracking reference
# ---------------------------------------------------------------------------

@app.post("/api/submissions")
async def create_submission(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a submission, then start the derivation.

    All channels converge here. Every later step reads the persisted
    record, never the channel, so the same submission produces the same
    derivation regardless of how it arrived.
    """
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


# ---------------------------------------------------------------------------
# Human gates
# ---------------------------------------------------------------------------

_GATE_MODELS = {
    "OwnerConfirmationRequest": OwnerConfirmationResponse,
    "CoEReviewRequest": CoEReviewResponse,
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
