"""Agent runtime — one swappable chat client, schema-gated.

Two responsibilities:

* **Client construction.** Core42 Compass is primary; Azure OpenAI and
  Entra ID are alternates.  In production the Compass base URL points at
  the APIM AI Gateway, so the PII gateway and cost caps sit in the path
  without any code change.
* **The schema gate.** A model proposes; this validates against the step's
  pydantic contract and retries on failure.  Unvalidated output never
  enters the design pack.

Determinism settings (``temperature=0``, fixed seed) are applied here
rather than per-agent so no individual agent can opt out of them.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError, create_model

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

# Provenance a model must never author.
#
# These record *who produced this output and what it read*. If a model can
# write them it can claim to have consulted a governed document it never
# saw, or mark its own output as non-stub. Observed in a live run: an
# agent reported reading ``capability_map_v3.2``, which does not exist.
#
# The step sets every one of these from the orchestrator's own knowledge
# after validation, so they are facts rather than claims.
_PROVENANCE_FIELDS = frozenset(
    {
        "step",
        "tier",
        "performed_by",
        "artifacts_consulted",
        "produced_at",
        "is_stub",
    }
)


@functools.lru_cache(maxsize=None)
def proposal_schema(schema: type[BaseModel]) -> type[BaseModel]:
    """The subset of ``schema`` a model is allowed to fill in.

    Provenance is removed. ``gap_flags`` and ``requires_input`` are kept
    deliberately: those are how an agent admits it could not resolve
    something, and that admission is the whole no-fabrication mechanism.
    An agent may say what it failed to do; it may not say what it read.
    """
    fields: dict[str, Any] = {
        name: (field.annotation, field)
        for name, field in schema.model_fields.items()
        if name not in _PROVENANCE_FIELDS
    }
    return create_model(f"{schema.__name__}Proposal", **fields)


@functools.lru_cache(maxsize=None)
def _schema_text(gate: type[BaseModel]) -> str:
    """The proposal schema as compact JSON, for inclusion in the prompt."""
    return json.dumps(gate.model_json_schema(), separators=(",", ":"))


class SchemaGateError(RuntimeError):
    """Raised when a model could not produce schema-valid output.

    Fail-closed: the step does not proceed on malformed output.
    """


def determinism_options() -> dict[str, Any]:
    """The sampling controls every agent is built with.

    Applied centrally, not per agent, so no individual agent can opt out
    of them.

    Reasoning models (gpt-5.x, o-series) reject ``temperature`` and
    ``seed`` outright, so for those this returns ``{}`` and reproducibility
    rests on the schema gate and version-pinned retrieval instead. That is
    a weaker guarantee and is reported as such by ``/api/health`` rather
    than being quietly assumed.
    """
    if not settings.supports_sampling_controls:
        logger.warning(
            "Model %r does not accept sampling controls - temperature and "
            "seed will NOT be sent. Reproducibility rests on the schema "
            "gate and pinned retrieval only.",
            settings.active_chat_model,
        )
        return {}

    return {
        "temperature": settings.model_temperature,
        "seed": settings.model_seed,
    }


def create_chat_client() -> Any:
    """Build the chat client from configuration.

    Priority: Compass -> Entra ID -> Azure OpenAI API key.

    Returns None when no provider is configured, which is the Sprint 1
    stub mode — the graph still runs end to end.
    """
    if settings.compass_api_key:
        from agent_framework.openai import OpenAIChatClient
        from openai import AsyncOpenAI

        logger.info(
            "Chat client: Core42 Compass (model=%s, base_url=%s)",
            settings.compass_chat_model,
            settings.compass_api_base_url,
        )
        return OpenAIChatClient(
            # NB: the parameter is ``model``, not ``model_id``. This path
            # was unreachable until a key existed, so the wrong keyword
            # survived until the first real call.
            model=settings.compass_chat_model,
            async_client=AsyncOpenAI(
                base_url=settings.compass_api_base_url,
                api_key=settings.compass_api_key,
            ),
        )

    if settings.use_entra_id:
        from agent_framework.azure import AzureAIClient
        from azure.identity.aio import DefaultAzureCredential

        logger.info("Chat client: Azure AI (Entra ID, per-service identity)")
        return AzureAIClient(
            project_endpoint=settings.foundry_project_endpoint,
            model_deployment_name=settings.foundry_model_deployment_name,
            credential=DefaultAzureCredential(),
        )

    logger.warning(
        "No model provider configured — agents will run as stubs. "
        "Set COMPASS_API_KEY or USE_ENTRA_ID to enable real derivation."
    )
    return None


def _strip_fences(text: str) -> str:
    """Remove markdown fences a model may wrap JSON in."""
    return _FENCE.sub("", text).strip()


def _extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating surrounding prose."""
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost JSON object or array in the response.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise SchemaGateError(f"response contained no parseable JSON: {text[:200]!r}")


async def propose(
    agent: Any,
    system_prompt: str,
    user_content: str,
    schema: type[T],
    provenance: dict[str, Any] | None = None,
) -> T:
    """Run an agent and validate its proposal against ``schema``.

    The agent proposes; the schema decides. On a validation failure the
    error is fed back once per configured retry so the model can correct
    itself, then the step fails closed.

    ``provenance`` is stamped on by the caller after validation. It is not
    offered to the model and cannot be overridden by it.
    """
    from agent_framework import Message

    # The model is shown only the fields it may author. Provenance is
    # removed, so a fabricated artifact reference cannot even be expressed.
    gate = proposal_schema(schema)

    # The schema is given to the model as text rather than as a provider
    # ``response_format``. Native structured output cannot express parts of
    # these contracts — an open ``dict[str, str]`` is rejected by strict
    # mode — and binding the engine to one provider's schema dialect would
    # trade a portable contract for a vendor feature. The prompts already
    # promise "JSON matching the required schema"; this supplies the schema
    # that promise refers to.
    #
    # Validation is unchanged either way: the pydantic gate below decides.
    messages = [
        Message(role="system", contents=[system_prompt]),
        Message(
            role="user",
            contents=[
                f"{user_content}\n\n"
                "Return ONLY a JSON object matching this schema. No prose, "
                "no markdown fences, no fields beyond those listed:\n"
                f"{_schema_text(gate)}"
            ],
        ),
    ]

    last_error = ""

    for attempt in range(settings.schema_gate_retries + 1):
        response = await agent.run(messages)
        raw = response.text or ""

        try:
            payload = _extract_json(raw)
            if isinstance(payload, dict):
                # Discard any provenance the model volunteered anyway.
                dropped = sorted(set(payload) & _PROVENANCE_FIELDS)
                if dropped:
                    logger.info(
                        "Discarding model-authored provenance on %s: %s",
                        schema.__name__,
                        ", ".join(dropped),
                    )
                    payload = {
                        k: v for k, v in payload.items() if k not in _PROVENANCE_FIELDS
                    }
            validated = gate.model_validate(payload)
            # Rebuild as the real type, stamping provenance from the
            # orchestrator's own knowledge rather than the model's claim.
            return schema.model_validate(
                {**validated.model_dump(), **(provenance or {})}
            )
        except (SchemaGateError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning(
                "Schema gate rejected %s output (attempt %d/%d): %s",
                schema.__name__,
                attempt + 1,
                settings.schema_gate_retries + 1,
                last_error[:300],
            )
            if attempt < settings.schema_gate_retries:
                messages = messages + [
                    Message(role="assistant", contents=[raw]),
                    Message(
                        role="user",
                        contents=[
                            "Your response failed schema validation with the "
                            f"following error:\n{last_error}\n\n"
                            "Return ONLY corrected JSON matching the required "
                            "schema. No prose, no markdown fences."
                        ],
                    ),
                ]

    raise SchemaGateError(
        f"{schema.__name__} validation failed after "
        f"{settings.schema_gate_retries + 1} attempts: {last_error[:500]}"
    )
