"""Application configuration for the M42 Intake Agent backend.

Model access follows the M42 house pattern: Core42 Compass is primary
(OpenAI-compatible), with Azure OpenAI / Entra ID as alternates.  In
production Compass is reached through the APIM AI Gateway, which is a
``COMPASS_API_BASE_URL`` change only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env", override=True)


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"true", "1", "yes", "on"}


@dataclass
class Settings:
    """Central configuration, loaded from environment."""

    # ---- Model provider: Core42 Compass (primary) -------------------------
    # In production this points at the APIM AI Gateway, not Compass directly.
    compass_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "COMPASS_API_BASE_URL", "https://api.core42.ai/v1"
        )
    )
    compass_api_key: str = field(
        default_factory=lambda: os.getenv("COMPASS_API_KEY", "")
    )
    compass_chat_model: str = field(
        default_factory=lambda: os.getenv("COMPASS_CHAT_MODEL", "gpt-4.1")
    )
    compass_embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "COMPASS_EMBEDDING_MODEL", "text-embedding-3-large"
        )
    )

    # ---- Model provider: Azure AI Foundry (alternate) ---------------------
    foundry_project_endpoint: str = field(
        default_factory=lambda: os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
    )
    foundry_model_deployment_name: str = field(
        default_factory=lambda: os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    )
    use_entra_id: bool = field(default_factory=lambda: _flag("USE_ENTRA_ID"))

    # ---- Determinism -----------------------------------------------------
    # Reproducibility is the product. These are not tuning knobs.
    model_temperature: float = field(
        default_factory=lambda: float(os.getenv("MODEL_TEMPERATURE", "0"))
    )
    model_seed: int = field(
        default_factory=lambda: int(os.getenv("MODEL_SEED", "42"))
    )
    schema_gate_retries: int = field(
        default_factory=lambda: int(os.getenv("SCHEMA_GATE_RETRIES", "2"))
    )

    # ---- Governed artifacts ---------------------------------------------
    artifact_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("ARTIFACT_ROOT", str(_BACKEND_DIR.parent / "artifacts"))
        )
    )
    # Fail-closed is mandated by v2.5. Only ever disabled in unit tests.
    fail_closed: bool = field(default_factory=lambda: _flag("FAIL_CLOSED", "true"))
    allow_seed_artifacts: bool = field(
        default_factory=lambda: _flag("ALLOW_SEED_ARTIFACTS", "true")
    )

    # ---- State -----------------------------------------------------------
    # "local" writes the design pack to disk; "cosmos" uses Cosmos DB.
    persistence_mode: str = field(
        default_factory=lambda: os.getenv("PERSISTENCE_MODE", "local").lower()
    )
    cosmos_endpoint: str = field(
        default_factory=lambda: os.getenv("COSMOS_ENDPOINT", "")
    )
    cosmos_database: str = field(
        default_factory=lambda: os.getenv("COSMOS_DATABASE", "intake")
    )
    local_state_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LOCAL_STATE_DIR", "./.state"))
    )

    # ---- Capability registry (Azure AI Search) ---------------------------
    search_endpoint: str = field(
        default_factory=lambda: os.getenv("AZURE_SEARCH_ENDPOINT", "")
    )
    search_index: str = field(
        default_factory=lambda: os.getenv("AZURE_SEARCH_INDEX", "capability-registry-v2")
    )
    search_key: str = field(default_factory=lambda: os.getenv("AZURE_SEARCH_KEY", ""))

    # ---- Server ----------------------------------------------------------
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ]
    )

    @property
    def has_model_provider(self) -> bool:
        """True when some LLM provider is configured.

        When False the graph still runs end-to-end on stub executors, which
        is the Sprint 1 mode.
        """
        return bool(
            self.compass_api_key or self.use_entra_id or self.foundry_project_endpoint
        )

    def __post_init__(self) -> None:
        self.local_state_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
