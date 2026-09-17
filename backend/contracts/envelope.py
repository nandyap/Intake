"""Run envelope — provenance, gap flags and the design pack.

Two invariants from v2.5 live here:

* **Auditability** — every artifact records the governed artifact versions
  it consulted, so a derivation can be replayed and explained.
* **No fabrication** — a missing input produces a ``RequiresInput`` marker
  and a gate condition, never a guessed value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeterminismTier(str, Enum):
    """Per-step determinism tier.

    Definitions from the lead SA's 27-step architecture diagram:

    * ``D0`` deterministic — a service or the orchestrator.
    * ``D1`` bounded-stochastic — an agent proposing against an enforced
      schema. The schema fixes the shape; the agent chooses the content.
    * ``D2`` guided-stochastic — an agent producing a plan graph. The
      agent determines structure as well as content.

    Note: "guided-stochastic" also appears at *solution* level in v2.5 §7,
    where it means the whole system stays inside a statically declared
    graph. That is :class:`GovernanceTier`, not this. Do not conflate them.

    Unresolved: the CAFE framework is said to use D0-D3. The scope
    document and the SA diagram both use D0-D2.
    """

    D0 = "D0"
    D1 = "D1"
    D2 = "D2"


class ArtifactRef(BaseModel):
    """A version-pinned reference to a governed artifact.

    ``is_seed`` is deliberately surfaced on every output: an artifact
    authored by us as a stand-in must never be mistaken for a governed one.
    """

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    version: str
    is_seed: bool = False
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class GapFlagType(str, Enum):
    UNMATCHED_FUNCTION = "unmatched_function"
    UNMATCHED_CAPABILITY = "unmatched_capability"
    UNDEFINED_CONCEPT = "undefined_concept"
    VOCABULARY_CONFLICT = "vocabulary_conflict"
    UNDOCUMENTED_REALISATION = "undocumented_realisation"
    MISSING_SERVICE_LEVEL = "missing_service_level"
    FACET_OVERRIDE = "facet_override"
    MISSING_ARTIFACT = "missing_artifact"


class OwningBody(str, Enum):
    """Where a gap flag is routed. Instances never author artifacts."""

    REVIEW_BOARD = "review_board"
    ONTOLOGY_COUNCIL = "ontology_council"
    ARB = "arb"


class GapFlag(BaseModel):
    """Raised when a derivation cannot resolve against a governed artifact.

    v2.5: the solution raises gap flags; it never invents the missing
    concept or capability.
    """

    model_config = ConfigDict(extra="forbid")

    flag_type: GapFlagType
    step: int
    context: str
    owning_body: OwningBody = OwningBody.REVIEW_BOARD
    raised_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RequiresInput(BaseModel):
    """Marks a value that could not be derived without fabricating it.

    A design pack carrying any of these can recommend
    proceed-with-conditions, never proceed.
    """

    model_config = ConfigDict(extra="forbid")

    field_name: str
    reason: str
    gate_condition: str


class StepOutput(BaseModel):
    """Common envelope every step output carries.

    Subclasses add their payload; this guarantees provenance is never
    optional.
    """

    model_config = ConfigDict(extra="forbid")

    step: int
    tier: DeterminismTier
    performed_by: str
    artifacts_consulted: list[ArtifactRef] = Field(default_factory=list)
    gap_flags: list[GapFlag] = Field(default_factory=list)
    requires_input: list[RequiresInput] = Field(default_factory=list)
    produced_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    is_stub: bool = False

    @property
    def is_clean(self) -> bool:
        """True when nothing was left unresolved."""
        return not self.gap_flags and not self.requires_input


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_OWNER_CONFIRMATION = "awaiting_owner_confirmation"
    AWAITING_COE_REVIEW = "awaiting_coe_review"
    AWAITING_CRITICALITY_CONFIRMATION = "awaiting_criticality_confirmation"
    AWAITING_ARCHITECT_REVIEW = "awaiting_architect_review"
    AWAITING_DIVERGENCE_APPROVAL = "awaiting_divergence_approval"
    REJECTED = "rejected"
    RETURNED_AS_INTEGRATION = "returned_as_integration"
    COMPLETED = "completed"
    FAILED = "failed"


class DesignPack(BaseModel):
    """The accumulating design pack repository for one submission.

    Every step reads and writes here, never from the channel. Keyed by
    step number so a resumed run reconstructs identically.
    """

    model_config = ConfigDict(extra="allow")

    submission_id: str
    tracking_reference: str
    status: RunStatus = RunStatus.PENDING
    current_step: int = 0
    outputs: dict[str, Any] = Field(default_factory=dict)
    gap_flags: list[GapFlag] = Field(default_factory=list)
    loop_counts: dict[str, int] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)

    def record(self, step: int, output: StepOutput) -> None:
        """Store a step output and hoist its gap flags to the pack."""
        self.outputs[str(step)] = output.model_dump(mode="json")
        self.gap_flags.extend(output.gap_flags)
        self.current_step = step
        self.history.append(
            f"step {step} · {output.performed_by} · {output.tier.value}"
            + (" · STUB" if output.is_stub else "")
        )

    def get(self, step: int) -> dict[str, Any] | None:
        return self.outputs.get(str(step))

    def bump_loop(self, loop_name: str) -> int:
        """Count a declared loop traversal.

        Cycles are legal because they are declared statically, but they
        must be bounded — an unbounded loop is an availability risk.
        """
        self.loop_counts[loop_name] = self.loop_counts.get(loop_name, 0) + 1
        return self.loop_counts[loop_name]
