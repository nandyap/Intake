"""Fail-closed, version-pinned artifact retrieval.

v2.5: "Retrieval resolves only to a signed current version; a stale or
unavailable index fails closed."

This is the single interface every step uses to reach a governed artifact.
Because it is the only path, swapping a seed artifact for a governed one
is a manifest version bump and nothing else changes.

Two properties are deliberately non-negotiable:

1. **Fail closed.** A missing or stale artifact raises, it does not return
   an empty default. A step that cannot read its artifact does not run.
2. **Seeds are never silent.** Every retrieval returns an ``ArtifactRef``
   carrying ``is_seed``, which is recorded in the step output and surfaces
   all the way to the design pack.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from contracts.envelope import ArtifactRef

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"


class ArtifactUnavailable(RuntimeError):
    """Raised when a governed artifact cannot be resolved.

    This is the fail-closed behaviour. Callers must not catch this to
    substitute a default — that would be fabrication.
    """

    def __init__(self, artifact_id: str, reason: str) -> None:
        self.artifact_id = artifact_id
        self.reason = reason
        super().__init__(f"Artifact '{artifact_id}' unavailable: {reason}")


@dataclass(frozen=True)
class Artifact:
    """A resolved governed artifact plus the reference that proves it."""

    ref: ArtifactRef
    content: Any

    @property
    def is_seed(self) -> bool:
        return self.ref.is_seed


class ArtifactStore:
    """Resolves governed artifacts from a signed manifest.

    The manifest is the contract. An artifact not listed in it does not
    exist, regardless of what files are on disk.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root or settings.artifact_root)
        self._manifest: dict[str, dict[str, Any]] | None = None
        self._cache: dict[str, Artifact] = {}

    # -- manifest ---------------------------------------------------------

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if self._manifest is not None:
            return self._manifest

        manifest_path = self._root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise ArtifactUnavailable(
                MANIFEST_NAME, f"no manifest at {manifest_path}"
            )

        with manifest_path.open(encoding="utf-8") as fh:
            raw = json.load(fh)

        entries = raw.get("artifacts")
        if not isinstance(entries, dict):
            raise ArtifactUnavailable(
                MANIFEST_NAME, "manifest has no 'artifacts' object"
            )

        self._manifest = entries
        logger.info(
            "Artifact manifest loaded: %d entries from %s",
            len(entries),
            manifest_path,
        )
        return entries

    # -- resolution -------------------------------------------------------

    def resolve(self, artifact_id: str) -> Artifact:
        """Resolve one artifact, or raise.

        Raises:
            ArtifactUnavailable: not in the manifest, file missing, expired,
                or a seed while seeds are disallowed.
        """
        if artifact_id in self._cache:
            return self._cache[artifact_id]

        entries = self._load_manifest()
        entry = entries.get(artifact_id)
        if entry is None:
            raise ArtifactUnavailable(artifact_id, "not listed in manifest")

        status = entry.get("status", "seed")
        is_seed = status != "governed"

        if is_seed and not settings.allow_seed_artifacts:
            raise ArtifactUnavailable(
                artifact_id,
                "artifact is a seed and ALLOW_SEED_ARTIFACTS is false",
            )

        expires = entry.get("expires_at")
        if expires:
            try:
                expiry = datetime.fromisoformat(expires)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ArtifactUnavailable(
                    artifact_id, f"unparseable expires_at: {expires}"
                ) from exc
            if expiry < datetime.now(timezone.utc):
                # Stale artifacts fail closed. This is the rule that stops a
                # derivation quietly running on outdated governance.
                raise ArtifactUnavailable(
                    artifact_id, f"expired at {expires} (stale — failing closed)"
                )

        rel_path = entry.get("path")
        if not rel_path:
            raise ArtifactUnavailable(artifact_id, "manifest entry has no path")

        path = self._root / rel_path
        if not path.is_file():
            raise ArtifactUnavailable(artifact_id, f"file missing at {path}")

        try:
            with path.open(encoding="utf-8") as fh:
                content = json.load(fh) if path.suffix == ".json" else fh.read()
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactUnavailable(artifact_id, f"unreadable: {exc}") from exc

        artifact = Artifact(
            ref=ArtifactRef(
                artifact_id=artifact_id,
                version=entry.get("version", "unknown"),
                is_seed=is_seed,
            ),
            content=content,
        )
        self._cache[artifact_id] = artifact
        return artifact

    def resolve_many(self, *artifact_ids: str) -> list[Artifact]:
        """Resolve several artifacts. Any one failing fails the whole set.

        A step either has all its governed inputs or it does not run.
        """
        return [self.resolve(aid) for aid in artifact_ids]

    def describe(self) -> list[dict[str, Any]]:
        """Manifest summary for the admin / fail-closed status board."""
        entries = self._load_manifest()
        return [
            {
                "artifact_id": aid,
                "version": e.get("version", "unknown"),
                "status": e.get("status", "seed"),
                "owner": e.get("owner", ""),
                "expires_at": e.get("expires_at"),
                "available": (self._root / e.get("path", "")).is_file(),
            }
            for aid, e in sorted(entries.items())
        ]


_store: ArtifactStore | None = None


def get_store() -> ArtifactStore:
    """Process-wide artifact store."""
    global _store
    if _store is None:
        _store = ArtifactStore()
    return _store
