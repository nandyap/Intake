import type { RunStatus } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  pending: "bg-slate-50 text-slate-600 border-slate-200",
  rejected: "bg-rose-50 text-rose-700 border-rose-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
  returned_as_integration: "bg-amber-50 text-amber-700 border-amber-200",
  awaiting_owner_confirmation: "bg-amber-50 text-amber-700 border-amber-200",
  awaiting_coe_review: "bg-amber-50 text-amber-700 border-amber-200",
  awaiting_criticality_confirmation: "bg-amber-50 text-amber-700 border-amber-200",
  awaiting_architect_review: "bg-amber-50 text-amber-700 border-amber-200",
  awaiting_divergence_approval: "bg-amber-50 text-amber-700 border-amber-200",
};

export function StatusBadge({ status }: { status: RunStatus | string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${style}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

/** D0 is deterministic code; D1/D2 are agentic and guided. */
export function TierBadge({ tier }: { tier: string }) {
  return (
    <span
      className={`tier-${tier} inline-block rounded border px-1.5 py-0.5 font-mono text-[11px]`}
      title={
        tier === "D0"
          ? "Deterministic — produced by code reading governed artifacts"
          : "Guided-stochastic — an agent proposed, a schema gate validated"
      }
    >
      {tier}
    </span>
  );
}

/** Marks output that relied on a seed artifact rather than a governed one. */
export function SeedBadge({ label = "seed" }: { label?: string }) {
  return (
    <span
      className="inline-block rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700"
      title="This output relied on a seed artifact authored by Factory, not a governed M42 artifact. It must be re-derived once the governed artifact is delivered."
    >
      {label}
    </span>
  );
}
