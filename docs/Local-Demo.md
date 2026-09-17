# Running the demo locally

The whole solution runs on a laptop. No Azure, no credentials, no
container runtime — the derivation engine, all five human gates and every
deterministic service work offline.

```powershell
./scripts/run-local.ps1
```

First run installs dependencies and takes a few minutes; later runs start
in seconds. It opens http://localhost:3000.

**Needs:** Python 3.11+ and Node 20+. That is all.

<details>
<summary>Starting the two services by hand</summary>

```powershell
# Terminal 1
cd backend
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python server.py                 # http://localhost:8000

# Terminal 2
cd frontend
npm install
npm run dev                      # http://localhost:3000
```
</details>

---

## What you are demonstrating

The system takes a business idea and produces two things:

- a **scoping-grade design** — capability coverage, reuse analysis, the
  workflow, risk classification, derived controls, build surface,
  component selection and a composed architecture
- a **funding recommendation** supported by that design

Between them sit two rule-based verdicts and five human decisions.

---

## A ten-minute walkthrough

### 1 · Start with the governance board

Open **Governance** first. It shows 8 reference documents, 7 marked
*seed*.

> Every derivation records which documents it used and whether each was a
> stand-in. Nothing here is hidden behind a confident-looking answer.

This frames the whole demo honestly and pre-empts the obvious question.

### 2 · Run the happy path

**New submission → Insurance pre-authorisation.**

The form has 30 questions; the worked examples skip the typing. This one
is a well-formed submission with complete effort data.

The run stops immediately at the **business owner confirmation** gate.

> Before any expensive analysis runs, the person accountable confirms the
> objective and its value. Confirm it.

### 3 · The feasibility gate and the first business case

After five derivation steps it reaches the **AI CoE review** gate. Point
out what has already happened:

- a feasibility verdict, decided by **rules in code** — not a model
- an initial business case with a real number, from the submitted effort
  data and the agreed cost anchors

> This is the commercial point of the gate. The expensive analysis has
> not run yet. Ideas that will not proceed stop here.

Accept it.

### 4 · The criticality gate — the one that sets the rigour

The run continues through quality attributes, the ontology check and
workflow sequencing, then stops at the **criticality confirmation** gate.

This is the shortest gate to explain and the most important to justify:

> The criticality class is not an output, it is an **input**. Everything
> after it — risk classes, obligations, build surface, components —
> derives its rigour from this one value. An under-classified use case
> produces a design that looks fully compliant against the wrong
> standard. So a person confirms it.

Try **substituting** a different class rather than confirming, then check
the design pack afterwards — the obligations change with it.

> And if this gate were ever bypassed, the readiness verdict fails the
> run rather than proceeding on an unconfirmed class.

### 5 · The design work

After assertions, the run reaches the **readiness verdict** — the second
rule-based decision.

Then the part worth slowing down for: risk classification, the controls
that follow from it, build-surface selection, component selection, and
composition.

> Note the order. Risk is classified *before* the platform is chosen, so
> the design inherits its guardrails rather than having them applied
> afterwards.

It stops at **architect review**. Approve.

### 6 · The deliverable

Click **View design pack**.

This is the answer to "is this just a yes/no?" — it is not. The pack
carries the recommendation, the problem framing, capability coverage,
build-or-reuse, risk, both verdicts *with every rule that was
evaluated*, the workflow, the derived controls, the architecture, and the
business case broken down by provenance.

Two things to point at:

- **The feasibility audit trail.** Every rule, whether it fired, and
  where it came from. Rule F01 is marked *sponsor directive*, not *seed*.
- **The business case provenance.** Every line says whether it came from
  the survey, was calculated, or needs architecture. Build cost is empty
  because it is architecture-derived and the architecture did not exist
  when the case was produced.

### 7 · Show a rejection

Back to **New submission → Paediatric medication dosing**.

Confirm the owner gate, then watch it stop at feasibility.

> Failure impact is *Critical*. The rule rejects on error tolerance even
> though an agent could technically do the task. That is a sponsor
> directive, and the design work never runs — no spend on a use case that
> cannot proceed.

Open the design pack: the rules table shows exactly which rule fired and
why.

### 8 · Show the no-fabrication rule

**New submission → Supplier onboarding.**

This one has incomplete effort data and an unknown error rate.

> The business case does not estimate. It marks the driver *requires
> input* and returns a recommendation of **defer**. A case carrying
> placeholders can never recommend proceed — that is enforced by the
> structure, not by discipline.

---

## Questions you will be asked

**"Is the AI actually doing anything?"**

Not yet, and the interface says so. Steps marked *stub* return
correctly-structured placeholders. Everything else is real: the
orchestration, both gates, risk derivation, control derivation,
composition and the business case. Turning on real agents is a
configuration change, not a code change.

**"How do you know it is reproducible?"**

There is a regression test that runs the same submission twice and
compares the design packs field by field. It currently passes. Temperature
is zero, schemas are tight, and retrieval is version-pinned.

**"Why does capability matching find nothing?"**

The business capability map has not been provided. Every function raises a
gap flag, which is the correct behaviour — the system will not invent a
capability to justify a use case.

**"What if a reference document is missing?"**

The step stops. It does not fall back to a default. A derivation that
quietly ran on stale governance would be worse than one that refused.

---

## Verifying without the interface

```powershell
cd backend
python -m tests.smoke           # full run, rejection rule, reproducibility
python -m tests.api_smoke       # HTTP surface across all five gates
python -m tests.samples_check   # each example behaves as its label claims
python -m tests.demo_check      # samples and design-pack endpoints
```

Interactive API docs are at http://localhost:8000/docs while the backend
is running.

---

## Notes

- State is written to `backend/.state`. Delete it for a clean slate.
- Runs are held in memory; restarting the backend clears them.
- Port 8000 or 3000 already in use is the most common start-up failure.
