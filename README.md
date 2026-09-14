# M42 Intake Agent — Phase 1

CAFÉ derivation for AI use cases, steps 3 to 22. A business team submits a use
case; the system derives a composed architecture, a control requirement set and
an initial business case, behind human decision gates.

**The outcome is a decision, not a design.** The architecture exists to make the
cost estimate real.

---

## Architecture

```
Next.js frontend  ──proxy──▶  FastAPI  ──▶  MAF static workflow (steps 3–22)
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
            8 agent services            5 deterministic services    fail-closed retrieval
            (bounded contexts)          (D0 — plain Python)         (version-pinned artifacts)
                    │                           │
                    └──── schema gate ──────────┘
                                │
                          Design pack (Cosmos)
```

**The determinism boundary is the anchor.** The typed workflow decides every
transition; agents only *propose* schema-validated output; humans decide at four
gates; retrieved content is data, never instruction; a stale or unavailable
artifact fails closed.

### Why the graph is static

An orchestrator that chose its own next step would be *open-stochastic* and
would take the whole solution to Board approval. Every transition — including
all four rework loops — is declared at build time in `workflow/graph.py`.

---

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
cp .env.example .env                               # leave COMPASS_API_KEY empty for stub mode
python server.py

# Frontend
cd frontend
npm install
npm run dev                                        # http://localhost:3000
```

### Verify

```bash
cd backend
python -m tests.smoke        # full derivation, sponsor rule, reproducibility
python -m tests.api_smoke    # HTTP surface end to end
```

`tests.smoke` asserts three things: the whole graph runs; a `Q22=Critical`
submission is rejected at the feasibility gate; and the same submission run
twice produces a byte-identical design pack.

---

## Stub mode

With no model provider configured, every agentic step returns a *schema-valid
placeholder* and is marked `is_stub`. The graph, its loops, its gates and all
deterministic services are fully exercised.

This is deliberate: it decouples our critical path from M42's artifact
delivery. Wiring a real agent is a one-line change in `agents/__init__.py`.

---

## The 20 steps

| # | Step | Tier | Owner |
|---|---|---|---|
| 3 | Frame use case | D1 | Business Analyst |
| 4 | Decompose elements | D2 | Business Architect |
| 5 | Match capabilities | D1 | Business Architect |
| 6 | Match realisations | D1 | Application Architect |
| 7 | Assign criticality band | D1 | Risk Officer |
| **8** | **Feasibility verdict** + initial business case | **D0** | Feasibility service |
| 9 | Derive quality attributes | D2 | Product Owner |
| 10 | Check ontology | D1 | Data Architect |
| 11 | Sequence workflow | D2 | Business Analyst |
| ~~12~~ | ~~Contract sources~~ | — | **Deferred — no green inputs** |
| 13 | Confirm criticality class | D1 | Risk Officer |
| 14 | Declare assertions | D1 | Product Owner |
| **15** | **Readiness verdict** | **D0** | Readiness service |
| 16 | Classify determinism | D1 | Solution Architect |
| 17 | Assign facet vectors | D1 | Risk Officer |
| **18** | **Derive exposure and influence** | **D0** | Risk derivation service |
| **19** | **Evaluate obligations** | **D0** | Policy service |
| 20 | Select build surface | D1 | Technology Architect |
| 21 | Select components | D1 | Solution Architect |
| **22** | **Compose architecture** | **D0** | Composition service |

Risk (17–19) precedes design (20–22) so the solution inherits its guardrails.

## The four human gates

| Gate | Decision | Loop on rejection |
|---|---|---|
| Owner confirmation | Is this the objective, and is the value right? | → step 3 |
| AI CoE review | Accept / reject / return for information | → step 3 |
| Architect review | Approve / reject / re-prompt | → step 16 |
| Divergence approval | Owner approves departure from the original request | → step 3 |

All four loops are bounded at 3 traversals.

---

## Layout

```
backend/
  contracts/       pydantic schemas — the determinism boundary
  knowledge/       fail-closed, version-pinned retrieval
  deterministic/   D0 services — no LLM, unit-testable
  agents/          8 bounded contexts
  workflow/        the static graph, executors, prompts, schema gate
  tests/           smoke + reproducibility
artifacts/
  manifest.json    signed manifest — the artifact contract
  seeds/           versioned seed artifacts
frontend/          Next.js 16 · React 19 · Tailwind 4
infra/             Bicep on top of the deployed AILZ
```

---

## Governed artifacts

Seven of eight artifacts are currently **seeds** authored by Factory so the
engine can run before M42 delivers governed versions. Every step output records
which artifacts it consulted and whether each was a seed; the Governance screen
surfaces this.

Replacing a seed with a governed artifact is a **version bump in
`artifacts/manifest.json`** — not a code change.

| Artifact | Status | Supersede with |
|---|---|---|
| `cost-anchors` | **provided** (Appendix B) | — |
| `criticality-taxonomy` | seed | M42 Risk |
| `feasibility-rules` | seed — **F01 is a sponsor directive, binding** | M42 AI CoE |
| `readiness-rules` | seed | M42 AI CoE |
| `determinism-criteria-register` | seed | CAFÉ **M1** |
| `facet-schema` | seed | M42 Risk |
| `obligation-set` | seed | CAFÉ **M3** |
| `build-surface-matrix` | seed | CAFÉ **M2** |

**The CAFÉ packet closes four of these at once.** Until it arrives the seeds are
deliberately thin — do not over-invest in them.

---

## Open items

- **CAFÉ packet** — M1–M5 and the `drawio-cafe` generator. The generator becomes
  the step-22 conformance gate, replacing the structural self-check.
- **Business capability map (L1–L3)** — step 5 cannot match without it. The
  525-tile registry is a *technology* registry and does not substitute.
- **Requirements version** — v2.5 vs v2.7 unresolved.
- **G-series count** — scope says G01–G26, CAFÉ says G01–G14. Seeds use G01–G14.
- **Determinism tiers** — scope says D0–D2, CAFÉ says D0–D3.
- **Real submission records** — the schema is solved; populated examples are not.
- **Apollo** — the downstream handoff target has no interface contract.
