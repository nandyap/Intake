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
        default_factory=lambda: os.getenv("COMPASS_CHAT_MODEL", "gpt-5.1")
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

    # Reasoning models (gpt-5.x, o1, o3, o4) reject ``temperature`` and
    # ``seed``: they sample internally and the API returns 400 if either is
    # sent. Auto-detected from the model name; set MODEL_SAMPLING_CONTROLS
    # to true/false to override.
    #
    # This is not cosmetic. Reproducibility is a tested claim, and with a
    # reasoning model it rests on the schema gate and pinned retrieval
    # rather than on sampling controls. ``/api/health`` reports which.
    model_sampling_controls: str = field(
        default_factory=lambda: os.getenv("MODEL_SAMPLING_CONTROLS", "auto").strip().lower()
    )

    # ---- Stub mode -------------------------------------------------------
    # Real agents are the default. Stub mode must be asked for.
    #
    # A stubbed run completes and produces a design pack carrying a
    # recommendation. Every stubbed step is marked ``is_stub``, but the
    # pack still *reads* like a derivation. If a missing or rejected key
    # silently fell back to stubs, a misconfigured deployment would keep
    # answering with placeholder values that look like findings.
    #
    # So a missing provider is an error, not a mode. Set ALLOW_STUB_AGENTS
    # to run without a model on purpose - demos, offline work, CI.
    allow_stub_agents: bool = field(
        default_factory=lambda: _flag("ALLOW_STUB_AGENTS", "false")
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
        """True when some LLM provider is configured."""
        return bool(
            self.compass_api_key or self.use_entra_id or self.foundry_project_endpoint
        )

    @property
    def mode(self) -> str:
        """``agents`` or ``stub`` - what this process will actually do."""
        return "agents" if self.has_model_provider else "stub"

    def require_model_provider(self) -> None:
        """Fail fast when no provider is configured and none was waived.

        Called at startup rather than at the first step, so a
        misconfiguration surfaces as a failed deployment instead of a
        design pack full of placeholders.
        """
        if self.has_model_provider or self.allow_stub_agents:
            return
        raise RuntimeError(
            "No model provider is configured and ALLOW_STUB_AGENTS is not "
            "set.\n\n"
            "The 14 agentic steps would return placeholder output that "
            "still reads like a derivation, so this is treated as a "
            "misconfiguration rather than a mode.\n\n"
            "  - to run for real : set COMPASS_API_KEY (backend/.env "
            "locally, Key Vault in Azure)\n"
            "  - to run stubbed  : set ALLOW_STUB_AGENTS=true\n"
        )

    @property
    def active_chat_model(self) -> str:
        """The model that will actually be called."""
        if self.compass_api_key:
            return self.compass_chat_model
        if self.use_entra_id or self.foundry_project_endpoint:
            return self.foundry_model_deployment_name
        return ""

    @property
    def supports_sampling_controls(self) -> bool:
        """Whether ``temperature`` and ``seed`` may be sent to the model.

        Reasoning families reject both. Sending them anyway produces a 400
        on every single step, which during a demo looks like the whole
        engine is broken.
        """
        if self.model_sampling_controls in {"true", "1", "yes", "on"}:
            return True
        if self.model_sampling_controls in {"false", "0", "no", "off"}:
            return False

        model = self.active_chat_model.lower().replace("_", "-")
        reasoning_prefixes = ("gpt-5", "o1", "o1-", "o3", "o3-", "o4", "o4-")
        return not model.startswith(reasoning_prefixes)

    def __post_init__(self) -> None:
        self.local_state_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
