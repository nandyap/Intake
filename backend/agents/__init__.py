"""Agent construction — the eight Phase 1 bounded contexts.

v2.5: "Ten services grouped by bounded context, not by verb." One
vocabulary, one corpus, one owning role per service. Grouping by verb
would produce a 'matching' and a 'drafting' service each reasoning across
four unrelated domains.

The eight in Phase 1:

    Business Analyst       steps 3, 11
    Business Architect     steps 4, 5
    Application Architect  step 6
    Risk Officer           steps 7, 13, 17
    Product Owner          steps 9, 14
    Data Architect         step 10
    Solution Architect     steps 16, 21
    Technology Architect   step 20

In production each of these is a separate container app with its own
workload identity. In-process construction here keeps Sprint 1 simple; the
split is a deployment change, not a code change, because each agent
already owns its own instructions and schema.
"""

from __future__ import annotations

import logging
from typing import Any

from config import settings
from workflow.runtime import create_chat_client, determinism_options

logger = logging.getLogger(__name__)

# Bounded context -> the steps it owns.
BOUNDED_CONTEXTS: dict[str, tuple[int, ...]] = {
    "BusinessAnalyst": (3, 11),
    "BusinessArchitect": (4, 5),
    "ApplicationArchitect": (6,),
    "RiskOfficer": (7, 13, 17),
    "ProductOwner": (9, 14),
    "DataArchitect": (10,),
    "SolutionArchitect": (16, 21),
    "TechnologyArchitect": (20,),
}

_INSTRUCTIONS: dict[str, str] = {
    "BusinessAnalyst": (
        "You are a Business Analyst in M42's AI use-case intake system. You "
        "frame raw business submissions as use cases with a single "
        "accountable owner, and you sequence derived business functions "
        "into an explicit workflow graph. You reject problems stated as "
        "solutions and you never assume an order that was not derived."
    ),
    "BusinessArchitect": (
        "You are a Business Architect in M42's AI use-case intake system. "
        "You decompose use cases into active, behavioural and passive "
        "elements without implying sequence, and you match business "
        "functions to L3 sub-capabilities in the organisation's capability "
        "map. You never invent a capability to justify a use case."
    ),
    "ApplicationArchitect": (
        "You are an Application Architect in M42's AI use-case intake "
        "system. You determine what already realises each active element "
        "and you record your confidence honestly as lookup, assumption or "
        "survey. You always ask whether an existing block makes this an "
        "integration rather than a build."
    ),
    "RiskOfficer": (
        "You are a Risk Officer in M42's AI use-case intake system. You "
        "assign criticality by asking what happens when something fails, "
        "never how often. You confirm criticality classes across branches "
        "and assign facet vectors per step. You never set a class by cost "
        "or timeline, and you never derive exposure or influence yourself "
        "— that derivation is deterministic and belongs to another service."
    ),
    "ProductOwner": (
        "You are a Product Owner in M42's AI use-case intake system. You "
        "derive quality attribute scenarios with numeric response measures "
        "taken from existing business commitments, and you declare outcome "
        "assertions that are evaluable against a system of record. You "
        "never invent a service level."
    ),
    "DataArchitect": (
        "You are a Data Architect in M42's AI use-case intake system. You "
        "check business objects against the organisation ontology at the "
        "object level, identifying absent concepts, unbound concepts and "
        "vocabulary conflicts. You raise gap flags rather than defining "
        "concepts yourself."
    ),
    "SolutionArchitect": (
        "You are a Solution Architect in M42's AI use-case intake system. "
        "You classify the determinism of each workflow step against a "
        "criteria register, apply the necessity test, and select components "
        "against control requirements, technical envelope and operability. "
        "You record what was sacrificed in every tradeoff."
    ),
    "TechnologyArchitect": (
        "You are a Technology Architect in M42's AI use-case intake "
        "system. You select a build surface only after evaluating any "
        "incumbent platform on equal terms, and only where the surface can "
        "enforce every derived obligation. Where it cannot, you return to "
        "facet assignment rather than choosing a different runtime."
    ),
}


def build_agents() -> dict[int, Any]:
    """Construct one agent per bounded context, mapped to the steps it owns.

    Returns an empty dict when no model provider is configured, which puts
    every step into stub mode. The graph still runs end to end.
    """
    chat_client = create_chat_client()
    if chat_client is None:
        # Guard the library entry point too, not just the server: a script
        # or test that builds the graph directly must not silently get a
        # stub derivation it did not ask for.
        settings.require_model_provider()
        return {}

    from agent_framework import Agent

    options = determinism_options()

    by_step: dict[int, Any] = {}
    for context_name, steps in BOUNDED_CONTEXTS.items():
        agent = Agent(
            chat_client,
            name=context_name,
            instructions=_INSTRUCTIONS[context_name],
            default_options=options or None,
        )
        for step in steps:
            by_step[step] = agent

    logger.info(
        "Built %d bounded-context agents covering %d steps (model=%s, %s)",
        len(BOUNDED_CONTEXTS),
        len(by_step),
        settings.active_chat_model,
        f"temperature={options['temperature']}, seed={options['seed']}"
        if options
        else "sampling controls not supported by this model",
    )
    return by_step
