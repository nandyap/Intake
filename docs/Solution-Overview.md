# Intake Agent — Solution Overview

**Phase 1 · steps 3–22 · deployed and running**

For the AI CoE, the solution architect and delivery management. Section 1
is non-technical; sections 3 onward assume architecture familiarity.

| | |
|---|---|
| Status | Deployed to the landing zone, running in stub mode |
| Scope | CAFÉ derivation steps 3–22 (19 of the 27-step flow) |
| Produces | A scoping-grade design pack and a funding recommendation |
| Code | ~4,700 lines Python · ~1,300 lines TypeScript |
| Verified | Full-graph run · sponsor rejection rule · reproducibility · HTTP surface |
| Not yet real | 7 of 8 governed artifacts are seeds; agentic steps return placeholders |

---

## 1 · In plain terms

### The problem

Someone in the business has an idea for an AI solution. Today, working out
whether it is worth building takes an architect several days — and two
architects given the same idea will reach different answers. Under delivery
pressure the expensive parts get skipped, and a system ships carrying
controls nobody actually derived.

### What this does

A business team fills in a structured form describing a process they want
to improve. The system then works through the idea the way an architect
would, in a fixed order:

1. States the problem properly, and finds the one person accountable for it.
2. Breaks it into who does what, and to which business objects.
3. Checks which of the organisation's capabilities already cover it.
4. Asks whether something already built does this — is it a build, or an integration?
5. Judges what happens if it fails.
6. **Decides, by rule, whether to continue at all.**

That sixth step matters commercially: it stops spend on ideas that will not
proceed, *before* the expensive analysis runs. It also produces a first
estimate of the money and time the idea would save.

If it passes, the analysis goes to the AI CoE to accept, reject, or send
back for more information. On acceptance the system continues: service
levels, data concepts, the workflow itself, risk classification, the
controls that follow from that risk, the platform to build on, the
components to use, and finally an architecture — which an architect
approves, rejects, or sends back for another pass.

### What it produces

Two things, and both matter.

**A scoping-grade design.** By the end the system has produced what an
SA would produce up to the scoping stage: which capabilities are
involved, what already exists and could be reused, the workflow itself,
the risk classification, the controls that follow from it, the platform
to build on, the components selected with the tradeoffs recorded, and a
composed architecture in conceptual, logical and physical views.

That is real analysis and design work. It is not a deep design document
and not an implementation plan — it is deliberately scoped to the depth
needed to cost the thing and decide on it. It is also a handoff artifact:
it is what the downstream build process picks up.

**A recommendation.** Proceed, proceed with conditions, or defer —
weighing quantified benefit against investment.

The relationship between the two is the point. The design is what makes
the cost real: the cost is the sum of the components the design switched
on. You cannot produce a defensible number without doing the design work
first.

And the recommendation can still be *no*. **A design that is sound but
does not repay its cost is a correct output of this system** — a decision
not to build, reached with the evidence to support it. So is a rejection
at the feasibility gate.

### Why build it rather than keep using architects

The point is not that architects cannot do this — it is the work they
already do. The point is that doing it this way makes it repeatable and
comparable, and frees architect time for the cases that genuinely need
judgement.

| | |
|---|---|
| **Reproducible** | The same submission produces the same answer, whoever runs it. This is tested, not asserted. |
| **Comparable** | Every idea is assessed against the same capability map, the same control rules, the same business-case structure — so they can be ranked against each other. |
| **Governed by construction** | The expensive derivations can no longer be skipped under pressure. Controls are always derived. |
| **Auditable** | Every output records which reference documents it consulted, which version, and how it reasoned. |

### Where humans decide

The system never approves anything. Five decisions belong to people:

- **The business owner** confirms the objective and its value, before any expensive work begins.
- **The AI CoE** accepts, rejects, or asks for more information.
- **An architect** confirms how critical the use case is — the judgement that sets how tightly everything after it is controlled.
- **An architect** approves the design, rejects it, or sends it back for another pass.
- **The business owner again**, if the proposed solution has drifted from what was originally asked for.

The two *verdicts* in between — feasibility and readiness — are decided by
rules in code, not by judgement and not by a model. Same inputs, same
verdict, every time.

---

## 2 · What exists today

Deployed into the existing AI Landing Zone: a web application, a backend
service, and the derivation engine.

**Working for real:**

- The complete 19-step flow, start to finish
- All five human decision points, with the send-back paths
- All five rule-based services — feasibility, readiness, risk, controls, architecture composition
- The initial business case, calculating real money from the submitted effort data
- A web interface: submit, watch the derivation, make decisions, see what was relied on

**Deliberately not real yet:**

- The eight AI agents return correctly-structured placeholders instead of
  reasoning. The plumbing around them is complete; they are waiting on a
  model key.
- Seven of the eight reference documents are **stand-ins we wrote**, clearly
  marked as such, because the governed versions have not been delivered.

This is not a gap left by accident. It is the point of the sequencing —
explained next.

---

## 3 · The approach, and why

### Build the skeleton first

The conventional order is to build agents, then wire them together. We did
the reverse: the entire flow, every gate, every send-back path and every
rule-based service was built and proven first, with the AI steps returning
structurally valid placeholders.

Three reasons:

**It decouples us from artifact delivery.** The engine depends on reference
documents that have not arrived. Had we built agent-first, we would now be
idle. Instead the hard part — orchestration, gates, contracts, control
derivation — is done and tested.

**The contracts get proven before anything depends on them.** Every step's
inputs and outputs are a schema, fixed before any prompt was written. A
prompt is cheap to change; a contract every downstream step relies on is
not.

**Swapping a placeholder for a real agent is one line.** The skeleton is not
scaffolding to be thrown away. It is the product; the agents plug into it.

### Seed documents, clearly labelled

Rather than wait, we wrote stand-in versions of the missing reference
documents — derived from real sources wherever possible. The criticality
taxonomy, for instance, is built from the risk questions already in the
intake form, not invented.

Three properties make this safe:

- They are **versioned and labelled**. Every output records which documents
  it used and whether each was a stand-in. The Governance screen shows this
  at a glance.
- They are read through the **same fail-closed contract** as governed ones.
  Swapping one in is a version number change, not a code change.
- They are **deliberately thin** where a known replacement is coming, so we
  do not over-invest in work that will be discarded.

### Fail closed, and never fabricate

Two rules run through the whole system:

**Fail closed.** If a reference document is missing or out of date, the step
that needs it stops. It does not fall back to a default. A derivation that
quietly ran on stale governance is worse than one that refused to run.

**Never fabricate.** Where an input is absent, the output says so and raises
a condition. It does not estimate. This is enforced structurally, not by
discipline: the initial business case *cannot* return an ROI, because ROI
needs a build cost and build cost needs an architecture that does not exist
yet. The field returns empty by construction.

---

## 4 · Technical architecture

```
Browser ──▶ Next.js ──proxy──▶ FastAPI ──▶ MAF typed workflow (19 steps)
                                               │
                 ┌─────────────────────────────┼─────────────────────────┐
                 ▼                             ▼                         ▼
        8 agent services            5 deterministic services    version-pinned
       (bounded contexts)              (plain Python)           artifact store
                 │                             │                (fail-closed)
                 └────── schema gate ──────────┘
                                │
                          Design pack
```

### The determinism boundary

This is the load-bearing decision, and it is worth being precise about.

**The workflow graph decides every transition. Nothing else does.** All 19
steps, 5 gates and 4 send-back loops are declared at build time in
`workflow/graph.py`. No executor and no model chooses what runs next.

The reason is governance, not taste. An orchestrator that picks its own next
step is *open-stochastic* — it would take the whole solution to Board
approval. A statically declared graph keeps it *guided-stochastic*, which
the existing governance tier permits.

Cycles are allowed because they are **declared**. The architect send-back
loop is an edge in the graph with a condition on it, not a runtime decision.
Each loop is bounded at three traversals.

### Three tiers of step

| Tier | What it is | Examples |
|---|---|---|
| **D0** | Plain Python reading governed documents. No model. | Feasibility, readiness, risk derivation, control evaluation, composition |
| **D1** | A model proposes within a closed schema against retrieved data | Framing, capability matching, criticality |
| **D2** | A model reasons over unbounded prose within the declared graph | Element decomposition, workflow sequencing |

The deterministic verdicts are D0 on purpose. A verdict that varies between
runs cannot govern anything.

**"Gate" means two different things here, and the difference matters.** A
*deterministic verdict* (steps 8, 15, 18, 19, 22) is a numbered step that
counts toward the 19 and is decided by rules in code. A *human gate* has no
step number, sits between steps, and is decided by a named person. Step 8
is a verdict; the AI CoE review that follows it is a gate.

### The schema gate

Agents *propose*. A Pydantic model validates. Only validated output enters
the design pack.

On a validation failure the error is fed back to the model to correct
itself, twice; then the step fails closed. Malformed output never reaches
the next step — which matters, because step 19 derives *controls* from step
17's output.

### Agents grouped by domain, not by task

Eight agent services, each owning one vocabulary and one corpus: Business
Analyst, Business Architect, Application Architect, Risk Officer, Product
Owner, Data Architect, Solution Architect, Technology Architect.

The alternative — grouping by verb, so one "matching" service and one
"drafting" service — produces agents reasoning across four unrelated
domains at once. The requirements are explicit on this, and it matches how
the work is actually divided among people.

### Reproducibility as a tested property

The core value claim is that the same submission yields the same
derivation. Because that claim spans model-driven steps, it needs
engineering rather than hope:

- Temperature zero, fixed seed
- Tight output schemas, so there is little room to vary
- Version-pinned retrieval — the same document version every run
- **A regression test** that runs one submission twice and compares the
  resulting design packs field by field, ignoring only timestamps

That test currently passes. It is the assertion that most needs to keep
passing as agents come online.

### Infrastructure

Two container apps on the existing Container Apps environment. Separate
managed identity per service — no shared account. Images build server-side,
so no local container runtime is needed. Deployment is `azd`.

The container apps, registry, identities and database containers are the
only things created; every landing-zone resource is referenced, never
modified.

---

## 5 · What is real, and what is not

Stated plainly, because the difference matters when reviewing output.

| Component | Status |
|---|---|
| The 19-step flow | **Real.** Runs start to finish. |
| The five human gates | **Real**, including send-back loops. |
| Feasibility verdict | **Real logic**, provisional rules. Rule F01 (reject where failure would cause severe or permanent harm) is a sponsor directive and binding. The rest need confirmation. |
| Readiness verdict | **Real logic**, provisional rules. |
| Risk derivation | **Real logic**, provisional facet schema. |
| Control derivation | **Real logic**, provisional obligation set. |
| Architecture composition | **Real**, but conformance validation is a structural self-check standing in for the proper validator. |
| Initial business case | **Real.** Uses the actual cost anchors and formulas from the requirements. This is the most complete part of the system. |
| The eight agents | **Placeholders.** Structurally valid, not reasoning. |
| Capability matching | **Blocked.** Needs the business capability map. Every function currently raises a gap flag — which is the correct behaviour, not a failure. |

### Known limitations

- **Runs are held in memory.** A container restart loses in-flight runs. The
  database containers exist so access and connectivity are proven ahead of
  implementing persistence.
- **No authentication.** Single sign-on with submitter / approver / admin
  roles is required and not built. Acceptable only while access is
  restricted to the internal network.
- **Step 12 (source contracts) is deferred** — it has no available inputs in
  this phase. The graph node exists, so adding it later is a small change.

---

## 6 · What is needed next

Ordered by impact.

**1 · The CAFÉ framework package.** Its operational models map almost
directly onto four steps we currently serve with stand-ins — determinism
classification, build-surface selection, component selection and
composition. Its validator would replace our structural self-check and
directly strengthen the reproducibility claim. This single package would
convert four provisional areas into governed ones.

**2 · The business capability map (L1–L3)**, with maturity, gap,
criticality, AI candidacy and KPIs. Capability matching cannot produce real
output without it. The technology capability registry is a different
artifact and does not substitute — worth being explicit about, because the
names are similar.

**3 · Confirmation of the gate rules.** Feasibility, readiness, risk
derivation and control evaluation have no detailed specification in the
scope document. These are the deterministic services, where "the agent will
work it out" is not available. Best handled as a working session rather than
a document request — we have written a first pass to react to.

**4 · Real submissions.** The form structure is settled; completed examples
are not. Five to ten, synthetic is fine.

**5 · Model access**, to turn the placeholders into agents. One
configuration change, no code.

### Open questions

- Which requirements version governs — v2.5 or v2.7?
- Control obligations: the scope document says 26, the framework says 14.
- Determinism tiers: the scope says three, the framework says four.
- Attachments: the requirements say no document ingestion, but the form
  offers upload and the step-3 schema lists attachments. Stored but not
  parsed, or parsed?

---

## 7 · Relationship to the earlier prototype

An earlier prototype of this solution exists, and it is worth being precise
about what carried over.

**Its architectural principles were sound, and this build keeps every one of
them**: a deterministic core with non-determinism at the edges, a single
transition authority, schema gates on every boundary, and no agent-to-agent
choreography. Those ideas are not in dispute.

What changed is the realisation surface, and each change traces to a
requirement rather than a preference:

| | Earlier prototype | Now | Driver |
|---|---|---|---|
| Process definition | Spread across a conversational builder, several low-code flows and list columns | One typed workflow in source control | Single transition authority, reviewable as code |
| Agent hosting | Platform-hosted, shared identity | Self-hosted, identity per service | Requirement: per-service workload identity, no shared account |
| Agent grouping | By task | By domain | Requirement: bounded contexts, not verbs |
| Feasibility | Decided by a model | Decided by rules in code | A gate that varies between runs is not a gate |
| Guardrails | Partly bypassed on one path | Enforced on every step | No exceptions available under the control framework |

We also **carried assets forward directly**: the technology capability
registry, the PII gateway, the API gateway policy and the observability
workbooks are reused as-is. The intake questionnaire and the business-case
model are used unchanged — the cost anchors and formulas in the working
business case are exactly those already specified.

---

## Appendix · The 19 steps

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
| ~~12~~ | ~~Contract sources~~ | — | *Deferred — no available inputs* |
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

Risk assessment (17–19) precedes design (20–22) deliberately, so the
solution inherits its guardrails rather than having them applied afterwards.

### The five gates and their send-back paths

Human pauses, not numbered steps — they sit *between* steps and never
count toward the 19.

| Gate | After step | Decision | On send-back |
|---|---|---|---|
| Owner confirmation | 3 | Is this the objective, and is the value right? | → step 3 |
| AI CoE review | 8 | Accept · reject · return for information | → step 3 |
| Criticality confirmation | 13 | Confirm or substitute the criticality class | none — a substitution *is* the correction |
| Architect review | 22 | Approve · reject · re-prompt | → step 16 |
| Divergence approval | after architect | Owner approves departure from the original request | → step 3 |

Four send-back loops, each bounded at three traversals.
