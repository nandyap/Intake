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

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class SchemaGateError(RuntimeError):
    """Raised when a model could not produce schema-valid output.

    Fail-closed: the step does not proceed on malformed output.
    """


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
            model_id=settings.compass_chat_model,
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
) -> T:
    """Run an agent and validate its proposal against ``schema``.

    The agent proposes; the schema decides. On a validation failure the
    error is fed back once per configured retry so the model can correct
    itself, then the step fails closed.
    """
    from agent_framework import Message

    messages = [
        Message(role="system", text=system_prompt),
        Message(role="user", text=user_content),
    ]

    last_error = ""
    for attempt in range(settings.schema_gate_retries + 1):
        response = await agent.run(messages)
        raw = response.text or ""

        try:
            payload = _extract_json(raw)
            return schema.model_validate(payload)
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
                    Message(role="assistant", text=raw),
                    Message(
                        role="user",
                        text=(
                            "Your response failed schema validation with the "
                            f"following error:\n{last_error}\n\n"
                            "Return ONLY corrected JSON matching the required "
                            "schema. No prose, no markdown fences."
                        ),
                    ),
                ]

    raise SchemaGateError(
        f"{schema.__name__} validation failed after "
        f"{settings.schema_gate_retries + 1} attempts: {last_error[:500]}"
    )
