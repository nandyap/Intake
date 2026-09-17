"""Compass connectivity check — run this before trusting a demo.

Answers four questions in order, and stops at the first failure:

1. Is a key configured at all?
2. Does the endpoint accept it?
3. Does the configured model exist and respond?
4. Does the schema gate get valid JSON back from it?

Question 4 is the one that matters. A model that answers but cannot
produce schema-valid output will fail every agentic step, and it is far
better to learn that here than three gates into a live walkthrough.

    python -m tests.compass_check

Never prints the key. Only its length and last four characters, which is
enough to tell two keys apart without disclosing either.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Runnable from anywhere: `python backend/tests/compass_check.py`,
# `python .\compass_check.py` from inside tests/, or the documented
# `python -m tests.compass_check` from backend/. This is the one check a
# person runs ad hoc while holding a fresh key, so it should not also
# require getting the working directory right.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from pydantic import BaseModel, Field  # noqa: E402

from config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-20s %(message)s")
log = logging.getLogger("compass")
log.setLevel(logging.INFO)


class _Probe(BaseModel):
    """A deliberately small schema — this is a connectivity test, not a
    capability test."""

    capital: str = Field(description="The capital city")
    country: str = Field(description="The country asked about")


async def main() -> int:
    # -- 1. configuration --------------------------------------------------
    log.info("base URL : %s", settings.compass_api_base_url)
    log.info("model    : %s", settings.compass_chat_model)

    key = settings.compass_api_key
    if not key:
        log.error("")
        log.error("COMPASS_API_KEY is not set.")
        log.error("")
        log.error("Paste the key into backend/.env:")
        log.error("    COMPASS_API_KEY=<your key>")
        log.error("")
        log.error("That file is gitignored. Do not put the key anywhere else.")
        return 1

    log.info("key      : %d chars, ending %r", len(key), key[-4:])
    log.info(
        "sampling : %s",
        "temperature=%s, seed=%s"
        % (settings.model_temperature, settings.model_seed)
        if settings.supports_sampling_controls
        else "not supported by this model - schema gate only",
    )

    # -- 2 & 3. reachability and the model --------------------------------
    from workflow.runtime import create_chat_client, determinism_options, propose

    client = create_chat_client()
    if client is None:
        log.error("no chat client was constructed despite a key being set")
        return 1

    from agent_framework import Agent

    options = determinism_options()
    agent = Agent(
        client,
        name="ConnectivityProbe",
        instructions="You answer with JSON only. No prose, no markdown fences.",
        default_options=options or None,
    )

    log.info("")
    log.info("calling the model...")

    try:
        result = await propose(
            agent=agent,
            system_prompt=(
                "You return only JSON matching the requested schema. "
                "No prose, no markdown fences."
            ),
            user_content=(
                "What is the capital of the United Arab Emirates? "
                'Respond as JSON: {"capital": "...", "country": "..."}'
            ),
            schema=_Probe,
        )
    except Exception as exc:
        detail = str(exc)
        log.error("")
        log.error("FAILED: %s", detail[:600])
        log.error("")

        lowered = detail.lower()
        if "quota" in lowered or "subscription" in lowered:
            log.error(
                "QUOTA OR ACCESS. The key is valid and the endpoint is "
                "reachable, but this account cannot currently call %r.",
                settings.compass_chat_model,
            )
            log.error(
                "Either the subscription has no quota for this model, or "
                "the allowance is exhausted. A full derivation costs ~14 "
                "calls plus retries, so a few test runs can exhaust a "
                "trial allocation."
            )
            log.error("Contact compass.support@core42.ai to confirm entitlement.")
        elif "temperature" in lowered or "seed" in lowered:
            log.error(
                "The model rejected a sampling parameter. Set "
                "MODEL_SAMPLING_CONTROLS=false in backend/.env and retry."
            )
        elif "401" in lowered or "unauthor" in lowered or "api key" in lowered:
            log.error("The key was rejected. Check it was pasted whole.")
        elif "429" in lowered or "rate limit" in lowered:
            log.error("Rate limited. Wait and retry.")
        elif "404" in lowered or "not found" in lowered:
            log.error(
                "The endpoint or model name may be wrong. Confirm %r is "
                "available to your Compass account.",
                settings.compass_chat_model,
            )
        elif "connect" in lowered or "timeout" in lowered or "resolve" in lowered:
            log.error(
                "Could not reach %s — check network or proxy access.",
                settings.compass_api_base_url,
            )
        return 1

    # -- 4. the schema gate ------------------------------------------------
    log.info("")
    log.info("model responded and the schema gate accepted it:")
    log.info("  capital = %s", result.capital)
    log.info("  country = %s", result.country)
    log.info("")
    log.info("Compass is working. The 14 agentic steps will now use it.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
