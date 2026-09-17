"""A model must not author its own provenance.

Observed in a live run: the step-5 agent reported consulting
``capability_map_v3.2``, an artifact that does not exist, and the step-7
agent reported the criticality taxonomy twice. Both were accepted into
the design pack, because the full step schema — including the provenance
envelope — was being handed to the model as its response format.

Provenance is the audit trail. If a model can write it, the audit trail
records what the model said it did rather than what it did.

This check asserts the model is never shown those fields, and that any it
volunteers anyway are discarded.
"""

import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from contracts.envelope import DeterminismTier  # noqa: E402
from contracts.steps import (  # noqa: E402
    CoverageMap,
    CriticalityBandOutput,
    ElementInventory,
    UseCaseRecord,
)
from workflow.runtime import (  # noqa: E402
    _PROVENANCE_FIELDS,
    proposal_schema,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-20s %(message)s")
log = logging.getLogger("provenance")
log.setLevel(logging.INFO)

# An agent must still be able to admit what it could not resolve.
MUST_KEEP = {"gap_flags", "requires_input"}


def main() -> int:
    failures: list[str] = []

    schemas = [UseCaseRecord, ElementInventory, CoverageMap, CriticalityBandOutput]

    for schema in schemas:
        gate = proposal_schema(schema)
        offered = set(gate.model_fields)

        leaked = sorted(offered & _PROVENANCE_FIELDS)
        if leaked:
            failures.append(f"{schema.__name__}: model can author {leaked}")

        missing = sorted(MUST_KEEP - offered)
        if missing:
            failures.append(
                f"{schema.__name__}: {missing} removed — an agent could no "
                "longer admit an unresolved input"
            )

        if not leaked and not missing:
            log.info(
                "%-22s %d field(s) offered, no provenance",
                schema.__name__,
                len(offered),
            )

    # -- a fabricated artifact reference must not survive ------------------
    gate = proposal_schema(CoverageMap)
    hostile = {
        "matches": [],
        "unmatched_functions": ["claims intake"],
        "unmatched_in_scope_capabilities": [],
        "gap_flags": [],
        "requires_input": [],
        # What the live model actually did.
        "artifacts_consulted": [
            {"artifact_id": "capability_map_v3.2", "version": "3.2", "is_seed": False}
        ],
        "is_stub": False,
        "performed_by": "Totally Real Architect",
        "step": 99,
    }

    stripped = {k: v for k, v in hostile.items() if k not in _PROVENANCE_FIELDS}
    validated = gate.model_validate(stripped)

    rebuilt = CoverageMap.model_validate(
        {
            **validated.model_dump(),
            "step": 5,
            "tier": DeterminismTier.D1,
            "performed_by": "Business Architect",
        }
    )

    if rebuilt.artifacts_consulted:
        failures.append(
            "a fabricated artifact reference survived into the step output"
        )
    else:
        log.info("fabricated artifact reference discarded")

    if rebuilt.performed_by != "Business Architect":
        failures.append(
            f"model overrode performed_by: {rebuilt.performed_by!r}"
        )
    else:
        log.info("performed_by set by the orchestrator, not the model")

    if rebuilt.step != 5:
        failures.append(f"model overrode step number: {rebuilt.step}")

    if rebuilt.is_stub:
        failures.append("is_stub was taken from the model")

    if failures:
        log.error("")
        for f in failures:
            log.error("FAIL: %s", f)
        return 1

    log.info("")
    log.info("provenance is orchestrator-authored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
