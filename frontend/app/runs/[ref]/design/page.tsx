"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { api, type DesignPack } from "@/lib/api";

/**
 * The design pack — the scoping-grade deliverable.
 *
 * Deliberately reads as a document rather than a data dump: this is what
 * an architect reviews and what the downstream build process picks up.
 */
export default function DesignPage({
  params,
}: {
  params: Promise<{ ref: string }>;
}) {
  const { ref } = use(params);
  const [pack, setPack] = useState<DesignPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getDesign(ref)
      .then(setPack)
      .catch((e) => setError((e as Error).message));
  }, [ref]);

  if (error) {
    return (
      <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        {error}
      </div>
    );
  }
  if (!pack) return <p className="text-sm text-slate-500">Loading…</p>;

  const bc = pack.business_case;
  const money = (v?: number | null) =>
    v === null || v === undefined
      ? "—"
      : `${Math.round(v).toLocaleString()} ${bc.currency ?? "AED"}`;

  return (
    <article className="max-w-4xl space-y-10">
      <header className="border-b border-slate-200 pb-5">
        <Link
          href={`/runs/${ref}`}
          className="text-xs text-teal-700 hover:underline"
        >
          ← back to the run
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Design pack</h1>
        <p className="mt-1 font-mono text-sm text-slate-500">
          {pack.tracking_reference}
        </p>
        {!pack.is_complete && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            This derivation did not reach composition, so the pack is partial.
            The sections below show how far it got and why it stopped.
          </p>
        )}
      </header>

      {/* ---- recommendation first: it is what the reader wants ---- */}
      <Section title="Recommendation">
        <div className="rounded border border-slate-200 bg-white p-5">
          <div className="text-lg font-semibold capitalize">
            {bc.recommendation?.replace(/_/g, " ") ?? "not derived"}
          </div>
          {bc.narrative && (
            <p className="mt-2 text-sm text-slate-600">{bc.narrative}</p>
          )}
          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <Stat label="Annual value" value={money(bc.annual_value)} />
            <Stat
              label="Operational saving"
              value={money(bc.annual_operational_saving)}
            />
            <Stat
              label="Quality saving"
              value={money(bc.annual_quality_saving)}
            />
          </dl>
          {bc.gate_conditions && bc.gate_conditions.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm text-amber-800">
              {bc.gate_conditions.map((c, i) => (
                <li key={i}>• {c}</li>
              ))}
            </ul>
          )}
        </div>
      </Section>

      <Section title="The problem">
        <Field label="Problem" value={pack.framing.problem_statement} />
        <Field
          label="Accountable owner"
          value={pack.framing.accountable_owner}
        />
        <Field
          label="Expected change"
          value={pack.framing.expected_change}
        />
      </Section>

      <Section title="Capability coverage">
        {pack.capability_coverage.matched.length > 0 ? (
          <Table
            head={["Business function", "Capability"]}
            rows={pack.capability_coverage.matched.map((m) => [
              m.business_function,
              m.l3_capability_name,
            ])}
          />
        ) : (
          <Empty>
            No function could be matched. The business capability map has not
            been provided, so every function raised a gap flag — the correct
            behaviour, not a failure.
          </Empty>
        )}
        {pack.capability_coverage.unmatched_functions.length > 0 && (
          <p className="mt-2 text-sm text-slate-600">
            Unmatched:{" "}
            {pack.capability_coverage.unmatched_functions.join(", ")}
          </p>
        )}
      </Section>

      <Section title="Build or reuse">
        <Field
          label="Recommendation"
          value={pack.reuse.recommendation}
        />
        <Field label="Rationale" value={pack.reuse.rationale} />
      </Section>

      <Section title="Risk">
        <Field
          label="Criticality band"
          value={pack.risk.criticality_band}
        />
        <Field
          label="Dominant failure mode"
          value={pack.risk.dominant_failure_mode}
        />
        {pack.risk.per_step.length > 0 && (
          <Table
            head={["Step", "Exposure", "Influence"]}
            rows={pack.risk.per_step.map((r) => [
              r.node_id,
              r.exposure,
              r.influence,
            ])}
          />
        )}
      </Section>

      {/* ---- the gates, with their full audit trail ---- */}
      <Section title="Feasibility gate">
        <Field label="Verdict" value={pack.gates.feasibility.outcome} />
        {pack.gates.feasibility.reasons.map((r, i) => (
          <p key={i} className="text-sm text-slate-600">
            {r}
          </p>
        ))}
        {pack.gates.feasibility.rules.length > 0 && (
          <div className="mt-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
              Every rule evaluated
            </p>
            <Table
              head={["Rule", "Test", "Source", "Fired"]}
              rows={pack.gates.feasibility.rules.map((r) => [
                r.rule_id,
                r.description,
                r.provenance.replace(/_/g, " "),
                r.triggered ? "yes" : "no",
              ])}
            />
          </div>
        )}
      </Section>

      {pack.gates.readiness.outcome && (
        <Section title="Readiness gate">
          <Field label="Verdict" value={pack.gates.readiness.outcome} />
          <ul className="space-y-1 text-sm text-slate-600">
            {pack.gates.readiness.conditions.map((c, i) => (
              <li key={i}>• {c}</li>
            ))}
          </ul>
        </Section>
      )}

      {pack.workflow.nodes.length > 0 && (
        <Section title="Workflow">
          <Field
            label="Governance tier"
            value={pack.workflow.governance_tier?.replace(/_/g, " ")}
          />
          <Table
            head={["Step", "Activity", "Performed by"]}
            rows={pack.workflow.nodes.map((n) => [
              n.node_id,
              n.activity_verb,
              n.performing_element,
            ])}
          />
        </Section>
      )}

      {pack.controls.length > 0 && (
        <Section title="Derived controls">
          <p className="mb-2 text-sm text-slate-600">
            {pack.controls.length} obligation
            {pack.controls.length === 1 ? "" : "s"} triggered by the risk
            classification. These constrain the platform and component
            choices below — the design inherits its guardrails rather than
            having them applied afterwards.
          </p>
          <Table
            head={["ID", "Obligation", "Applies to"]}
            rows={pack.controls.map((c) => [
              c.obligation_id,
              c.title,
              `${c.applies_to_nodes.length} step(s)`,
            ])}
          />
        </Section>
      )}

      <Section title="Architecture">
        <Field
          label="Build surface"
          value={pack.architecture.build_surface}
        />
        <Field
          label="Why"
          value={pack.architecture.build_surface_rationale}
        />
        {pack.architecture.components.length > 0 && (
          <Table
            head={["Capability", "Component", "Rationale"]}
            rows={pack.architecture.components.map((c) => [
              c.capability,
              c.chosen_name,
              c.rationale,
            ])}
          />
        )}
        {pack.architecture.conditional_obligations.length > 0 && (
          <p className="mt-3 text-sm text-amber-800">
            Conditional obligations needing an additional component:{" "}
            {pack.architecture.conditional_obligations.join(", ")}
          </p>
        )}
        {pack.architecture.conformance_violations.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm text-rose-700">
            {pack.architecture.conformance_violations.map((v, i) => (
              <li key={i}>• {v}</li>
            ))}
          </ul>
        )}
      </Section>

      {bc.positions && bc.positions.length > 0 && (
        <Section title="Business case detail">
          <Table
            head={["Role", "Headcount", "Annual hours", "Annual cost", "Saving"]}
            rows={bc.positions.map((p) => [
              p.role,
              String(p.headcount),
              p.annual_hours ? Math.round(p.annual_hours).toLocaleString() : "—",
              money(p.annual_cost),
              money(p.annual_saving),
            ])}
          />
          {bc.lines && (
            <div className="mt-4">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                Every line, with its provenance
              </p>
              <Table
                head={["Line", "Value", "Bucket", "Source"]}
                rows={bc.lines.map((l) => [
                  l.label,
                  l.requires_input ? "requires input" : money(l.value),
                  l.bucket,
                  l.source,
                ])}
              />
              <p className="mt-2 text-xs text-slate-500">
                S = survey-direct · A = architecture-derived · C = calculated ·
                M = manual/external. Lines marked “requires input” are never
                estimated.
              </p>
            </div>
          )}
        </Section>
      )}

      {pack.gap_flags.length > 0 && (
        <Section title="Gap flags raised">
          <ul className="space-y-2">
            {pack.gap_flags.map((f, i) => (
              <li
                key={i}
                className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm"
              >
                <span className="font-mono text-xs text-amber-800">
                  step {f.step} · {f.flag_type.replace(/_/g, " ")}
                </span>
                <p className="mt-1 text-amber-900">{f.context}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Presentation helpers
// ---------------------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-3 border-b border-slate-200 pb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  if (!value) return null;
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-40 shrink-0 text-slate-500">{label}</span>
      <span className="text-slate-800">{value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-hidden rounded border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => (
                <td key={j} className="px-3 py-2 align-top text-slate-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-500">
      {children}
    </p>
  );
}
