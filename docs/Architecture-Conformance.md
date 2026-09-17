# Architecture Conformance — build vs. the 27-step reference flow

**Date:** 2026-09-17
**Reference:** Lead SA's 27-step architecture diagram
**Build:** `intake-agent/` Phase 1, deployed, stub mode

Evidence of conformance, and an honest list of where the build and the
reference diagram differ. Written so a reviewer can check every claim
against the code.

---

## Summary

| | |
|---|---|
| Agentic steps matching the diagram's tier **and** role | **14 of 14** |
| Deterministic services matching | **5 of 5** |
| Steps in Phase 1 scope implemented | **19 of 20** (step 12 deferred) |
| Corrections made after reviewing the diagram | 1 (tier definitions) |
| Genuine gaps against the diagram | 3 |
| Structural question needing a decision | 1 (the gate model) |

The spine of the architecture — which step is deterministic, which is
agentic, and which architecture role owns it — matches the reference
exactly. The differences are at the human-decision layer, and they trace
to a source conflict rather than to a build error.

---

## 1 · Step-by-step conformance

Every agentic step, as declared in `backend/workflow/steps.py`.

| # | Step | Diagram | Build | |
|---|---|---|---|---|
| 3 | Frame use case | D1 · Business Analyst | D1 · Business Analyst | ✅ |
| 4 | Decompose elements | D2 · Business Architect | D2 · Business Architect | ✅ |
| 5 | Match capabilities | D1 · Business Architect | D1 · Business Architect | ✅ |
| 6 | Match realisations | D1 · Application Architect | D1 · Application Architect | ✅ |
| 7 | Assign criticality band | D1 · Risk Officer | D1 · Risk Officer | ✅ |
| 9 | Derive quality attributes | D2 · Product Owner | D2 · Product Owner | ✅ |
| 10 | Check ontology | D1 · Data Architect | D1 · Data Architect | ✅ |
| 11 | Sequence workflow | D2 · Business Analyst | D2 · Business Analyst | ✅ |
| 13 | Confirm criticality class | D1 · Risk Officer | D1 · Risk Officer | ✅ |
| 14 | Declare assertions | D1 · Product Owner | D1 · Product Owner | ✅ |
| 16 | Classify determinism | D1 · Solution Architect | D1 · Solution Architect | ✅ |
| 17 | Assign facet vectors | D1 · Risk Officer | D1 · Risk Officer | ✅ |
| 20 | Select build surface | D1 · Technology Architect | D1 · Technology Architect | ✅ |
| 21 | Select components | D1 · Solution Architect | D1 · Solution Architect | ✅ |

Deterministic services, as declared in `backend/deterministic/`:

| # | Step | Diagram | Build | |
|---|---|---|---|---|
| 8 | Feasibility verdict | D0 · Feasibility svc | D0 · Feasibility service | ✅ |
| 15 | Readiness verdict | D0 · Readiness svc | D0 · Readiness service | ✅ |
| 18 | Derive exposure/influence | D0 · Risk derivation svc | D0 · Risk derivation service | ✅ |
| 19 | Evaluate obligations | D0 · Policy svc | D0 · Policy service | ✅ |
| 22 | Compose architecture | D0 · Composition svc | D0 · Composition service | ✅ |

**Verify:**

```powershell
cd backend
Select-String -Path 'workflow\steps.py' -Pattern '^\s+(\d+), "([^"]+)", "([^"]+)",\s*$' -Context 0,1
Select-String -Path 'deterministic\*.py' -Pattern 'performed_by="([^"]+)"'
```

### Ordering

The diagram runs risk (17–19) before design (20–22), so the solution
inherits its guardrails rather than having them applied afterwards. The
build declares exactly that chain:

```python
builder.add_chain([s16, s17, s18, s19, s20, s21, s22])
```

The sponsor independently confirmed this ordering in her email of
11 September.

---

## 2 · Correction made after reviewing the diagram

**The determinism tier definitions in our seed register were wrong.**

| | Was (build) | Now (diagram legend) |
|---|---|---|
| D1 | "guided-stochastic, bounded — a model proposes within a closed schema" | **bounded-stochastic — agent, enforced schema** |
| D2 | "guided-stochastic, open — a model reasons over unbounded natural language" | **guided-stochastic — agent, plan graph** |

Two things were wrong, and the second matters more:

1. **The names.** D1 is *bounded*-stochastic, not "guided-stochastic,
   bounded".
2. **The plan graph.** The diagram's D2 means the agent produces a *plan
   graph* — it determines structure as well as content. Our wording said
   "reasons over unbounded prose", which describes a different thing and
   omits the structural output entirely.

This mattered because **step 16 classifies every step against this
register**. A wrong register produces wrong classifications, and step 16
feeds the facet vectors that feed the control derivation. Corrected in
`artifacts/seeds/determinism-criteria-register.json` and
`backend/contracts/envelope.py`.

**Also recorded:** "guided-stochastic" appears at two levels in the source
material and must not be conflated. At *step* level it means D2. At
*solution* level (v2.5 §7) it means the whole system stays inside a
statically declared graph — the opposite of open-stochastic. The code
keeps these as separate types: `DeterminismTier` and `GovernanceTier`.

---

## 3 · Gaps against the diagram

Stated plainly. None is hidden in the build; all three are visible in the
code or the documentation.

### 3.1 · Step 13 has no human gate ⚠️

The diagram marks step 13 **H** — *confirm criticality class* is a human
decision.

The build has the field but not the gate:

```python
# contracts/steps.py
architect_confirmed: bool = False   # never set true by a human

# workflow/graph.py
builder.add_chain([s9, s10, s11, s13, s14, s15])   # flows straight through
```

The readiness service at step 15 *reads* `architect_confirmed`, so the
plumbing anticipates it. Only the gate node is missing.

**Impact:** a criticality class is currently confirmed by an agent
proposal alone. Given that the class sets the control rigour for
everything downstream, this is the most substantive of the three gaps.

**Fix:** one gate executor plus two edges. Small, and the pattern already
exists four times over.

### 3.2 · Step 12 deferred

The diagram has step 12 *Contract sources* as D1 · Data Architect.

The build defines the contract (`SourceContracts` in `contracts/steps.py`)
but the node is not wired into the graph. The reason is recorded in the
scope document itself: step 12 has **no green inputs** in Phase 1 — its
required artifact, the grounding source classification, is a Phase 3
dependency.

**This was a documented scope decision, not an omission.** It should be
confirmed rather than assumed.

### 3.3 · Human decisions are not on Teams Approvals

The diagram's legend is specific: *"Human decision via Teams Approvals."*

The build routes all human decisions through a web console
(`frontend/components/gate-console.tsx`). Functionally equivalent —
approve, reject, send back, with the decider's name captured — but the
wrong channel.

The sponsor's email also names **Teams and email** for the AI CoE report,
so two independent sources agree on the channel. The web console should be
treated as an interim surface.

---

## 4 · The structural question: which gate model?

This is the one that needs a decision rather than a fix, and it is worth
stating precisely because the two sources genuinely differ.

**The diagram places human decisions at steps 8, 13 and 26.**

**The sponsor's email of 11 September describes a different set**, and the
build follows the email:

| Build gate | Placed after | Source |
|---|---|---|
| Business owner confirmation | step 3 | Sponsor stage 1 — *"concludes with an agreement on the objective of the solution and the value of achieving it, confirmed by the business owner"* |
| AI CoE review | step 8 | Sponsor stage 2 — *"goes to the AI CoE team through Teams and e-mail, to accept, reject or send back for further information"* |
| Architect review | step 22 | Sponsor stage 3 — *"An Architect should approve this solution, reject it, re-prompt it"* |
| Divergence approval | after architect review | Sponsor stage 3 — *"Any divergence between the proposal and the original request should go back to the business owner"* |

Mapping the two together:

| Diagram | Build | Status |
|---|---|---|
| **H** at step 8 | AI CoE review gate, immediately after step 8 | ✅ aligned — the deterministic verdict is computed, then a human accepts, rejects, or returns it |
| **H** at step 13 | — | ❌ **missing** (§3.1) |
| **H** at step 26 | Architect review gate at step 22 | ⚠️ **pulled forward.** Step 26 is out of Phase 1, so the sponsor's stage-3 architect approval was placed at the end of the Phase 1 flow instead |
| — | Business owner confirmation after step 3 | ➕ **added** from the sponsor's email; not in the diagram |
| — | Divergence approval | ➕ **added** from the sponsor's email; not in the diagram |

### Why the build followed the email

The sponsor wrote: *"I will sign-off phase 1 as long as it delivers the
following purpose and business outcomes."* Sign-off is conditioned on
those outcomes, so the build implements them.

The three send-back loops — return-for-info, architect re-prompt,
divergence-to-owner — come from the same source. They are declared
statically as conditional edges, each bounded at three traversals, so they
do not compromise the determinism posture. An orchestrator choosing its
own next step would be open-stochastic; a declared cycle is not.

### What needs deciding

Whether the reference flow should absorb the sponsor's gates, or the build
should drop back to the diagram's three. **The build can move either way
cheaply** — gates are executors plus edges, and the pattern is established.
What it should not do is guess.

Recommended: add the step-13 gate regardless, since both sources support
a human confirming criticality, and resolve the rest as one decision.

---

## 5 · Out of Phase 1, correctly

The diagram shows these with dashed borders as their own sub-workflow
(§4.9):

| # | Step | Diagram |
|---|---|---|
| 23 | Estimate cost | D1 sub-workflow · Cost Engineer |
| 24 | Build business case | D2 sub-workflow · Value Analyst |

Neither is built. **But the S+C portion of the business case is**, at step
8, because the sponsor requires an initial business case at the analysis
stage.

The split follows the four provenance buckets in Appendix B:

- **Initial** (built) = **S** survey-direct + **C** calculated. Computable
  from the questionnaire and the cost anchors with no architecture.
- **Full** (steps 23–24, not built) = adds **A** architecture-derived and
  **M** manual/external.

This is why `roi_multiple` and `payback_months` return `None` rather than a
number: ROI needs build cost, build cost is bucket A, and the architecture
does not exist when the initial case runs. The no-fabrication rule is
enforced structurally rather than by discipline.

Steps 25–27 (delivery artifacts, assemble and route, provision) are not
built and are not in Phase 1.

---

## 6 · What is real, and what is not

Conformance to the diagram's *shape* is not the same as producing real
output.

| | |
|---|---|
| The 19-step flow | **Real.** Runs start to finish |
| Four human gates and their loops | **Real** |
| The five D0 services | **Real logic**, provisional rules |
| Initial business case | **Real.** Uses the actual Appendix B anchors and formulas |
| **The eight agents** | **Placeholders.** Prompts, schemas and wiring exist; no model key, so every agentic step returns a schema-valid stub marked `is_stub`. **They have never made a model call** |
| Capability matching (step 5) | **Blocked.** Needs the business capability map. Every function raises a gap flag — correct behaviour, not a failure |
| Reference documents | **7 of 8 are seeds** we authored. Only the cost anchors are real |

The interface marks every stubbed step and every seed artifact, so a
reviewer can see at a glance which parts of a derivation are real.

---

## 7 · Verifying these claims

```powershell
cd backend
python -m tests.smoke           # 19 steps E2E · severe-harm rejection · reproducibility
python -m tests.api_smoke       # HTTP surface across all four gates
python -m tests.samples_check   # each worked example reaches its labelled outcome
python -m tests.demo_check      # samples and design-pack endpoints
```

All four pass. The reproducibility test runs one submission twice and
compares the resulting design packs field by field — the core value claim
is tested, not asserted.

The graph itself is a single readable file: `backend/workflow/graph.py`.
Every transition in the system is declared there, and nowhere else.
