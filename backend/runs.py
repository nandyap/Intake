"""Run manager — one derivation run per submission.

Owns the lifecycle: start a run, pause at a human gate, resume when the
answer arrives.  Runs are held in memory here; the Cosmos-backed store is
a drop-in replacement behind the same interface (and MAF checkpointing
already handles mid-run durability).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents import build_agents
from contracts.envelope import DesignPack, RunStatus
from contracts.submission import Submission
from workflow.graph import build_graph

logger = logging.getLogger(__name__)


@dataclass
class PendingGate:
    """A human decision the run is waiting on."""

    request_id: str
    gate_type: str
    data: Any


@dataclass
class Run:
    """One submission's derivation run."""

    submission: Submission
    workflow: Any
    pack: DesignPack
    pending: list[PendingGate] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_awaiting_human(self) -> bool:
        return bool(self.pending)


class RunManager:
    """Creates and advances derivation runs."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._agents: dict[int, Any] | None = None

    def _agent_map(self) -> dict[int, Any]:
        # Built once — agents are stateless across runs.
        if self._agents is None:
            self._agents = build_agents()
        return self._agents

    # -- lifecycle ---------------------------------------------------------

    async def start(self, submission: Submission) -> Run:
        """Persist the submission and begin the derivation."""
        workflow = build_graph(agents=self._agent_map())

        pack = DesignPack(
            submission_id=submission.submission_id,
            tracking_reference=submission.tracking_reference,
        )
        pack.outputs["submission"] = submission.model_dump(mode="json")

        run = Run(submission=submission, workflow=workflow, pack=pack)
        self._runs[submission.tracking_reference] = run

        await self._advance(run, initial=pack)
        return run

    async def respond(
        self, tracking_reference: str, request_id: str, response: Any
    ) -> Run:
        """Answer a pending gate and resume the run."""
        run = self.get(tracking_reference)
        if run is None:
            raise KeyError(tracking_reference)

        match = next((p for p in run.pending if p.request_id == request_id), None)
        if match is None:
            raise KeyError(f"no pending gate {request_id}")

        await self._advance(run, responses={request_id: response})
        return run

    async def _advance(
        self,
        run: Run,
        initial: DesignPack | None = None,
        responses: dict[str, Any] | None = None,
    ) -> None:
        """Run until the workflow completes or pauses at a gate."""
        try:
            if responses is not None:
                result = await run.workflow.run(responses=responses)
            else:
                result = await run.workflow.run(initial)

            for output in result.get_outputs():
                if isinstance(output, DesignPack):
                    run.pack = output

            run.pending = [
                PendingGate(
                    request_id=event.request_id,
                    gate_type=type(event.data).__name__,
                    data=event.data,
                )
                for event in result.get_request_info_events()
            ]

            if not run.pending and run.pack.status is RunStatus.RUNNING:
                run.pack.status = RunStatus.COMPLETED

        except Exception as exc:
            logger.exception("run %s failed", run.pack.tracking_reference)
            run.error = str(exc)
            run.pack.status = RunStatus.FAILED

    # -- access ------------------------------------------------------------

    def get(self, tracking_reference: str) -> Run | None:
        return self._runs.get(tracking_reference)

    def list_runs(self) -> list[Run]:
        return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)


def new_tracking_reference() -> str:
    """Human-quotable tracking reference issued at step 2."""
    return f"M42-INT-{uuid.uuid4().hex[:8].upper()}"


manager = RunManager()
