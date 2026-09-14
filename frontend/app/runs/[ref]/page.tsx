"use client";

import { use, useCallback, useEffect, useState } from "react";

import { SeedBadge, StatusBadge, TierBadge } from "@/components/badges";
import { GateConsole } from "@/components/gate-console";
import {
  api,
  STEP_META,
  type RunSummary,
  type Timeline,
} from "@/lib/api";

export default function RunPage({
  params,
}: {
  params: Promise<{ ref: string }>;
}) {
  const { ref } = use(params);

  const [run, setRun] = useState<RunSummary | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [runRes, timelineRes] = await Promise.all([
        api.getRun(ref),
        api.getTimeline(ref),
      ]);
      setRun(runRes);
      setTimeline(timelineRes);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [ref]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        {error}
      </div>
    );
  }
  if (!run || !timeline) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  const businessCase = run.recommendation;
  const loops = Object.entries(run.loop_counts);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-xl font-semibold">
            {run.tracking_reference}
          </h1>
          <StatusBadge status={run.status} />
        </div>
        <p className="text-sm text-slate-500">
          {run.steps_completed.length} of 19 steps · {run.gap_flag_count} gap
          flag{run.gap_flag_count === 1 ? "" : "s"}
          {businessCase && ` · ${businessCase.replace(/_/g, " ")}`}
          {run.annual_value !== null &&
            ` · ${run.annual_value.toLocaleString()} AED annual value`}
        </p>
        {loops.length > 0 && (
          <p className="text-xs text-slate-500">
            Declared loops traversed:{" "}
            {loops.map(([k, v]) => `${k.replace(/_/g, " ")} ×${v}`).join(", ")}
          </p>
        )}
      </header>

      {run.pending_gates.length > 0 && (
        <GateConsole
          trackingReference={ref}
          gate={run.pending_gates[0]}
          onAnswered={load}
        />
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Derivation timeline
        </h2>
        <div className="overflow-hidden rounded border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Step</th>
                <th className="px-4 py-2 font-medium">Performed by</th>
                <th className="px-4 py-2 font-medium">Tier</th>
                <th className="px-4 py-2 font-medium">Artifacts consulted</th>
                <th className="px-4 py-2 font-medium">Flags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {timeline.steps.map((step) => (
                <tr key={step.step} className="align-top hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-xs text-slate-400">
                      {step.step}
                    </span>{" "}
                    <span className="text-slate-800">
                      {STEP_META[step.step]?.name ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">
                    {step.performed_by}
                  </td>
                  <td className="px-4 py-2.5">
                    <TierBadge tier={step.tier} />
                    {step.is_stub && (
                      <span className="ml-1.5">
                        <SeedBadge label="stub" />
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {step.artifacts.length === 0 ? (
                      <span className="text-slate-400">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {step.artifacts.map((a) => (
                          <span
                            key={a.id}
                            className="inline-flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600"
                            title={`${a.id} @ ${a.version}`}
                          >
                            {a.id}
                            {a.is_seed && <SeedBadge />}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">
                    {step.gap_flags > 0 && (
                      <span className="text-amber-700">
                        {step.gap_flags} gap
                      </span>
                    )}
                    {step.requires_input > 0 && (
                      <span className="ml-2 text-amber-700">
                        {step.requires_input} needs input
                      </span>
                    )}
                    {step.gap_flags === 0 && step.requires_input === 0 && (
                      <span className="text-slate-400">clean</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {timeline.gap_flags.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Gap flags → Review Board
          </h2>
          <ul className="space-y-2">
            {timeline.gap_flags.map((flag, i) => (
              <li
                key={i}
                className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm"
              >
                <div className="flex items-center gap-2 text-xs font-medium text-amber-800">
                  <span className="font-mono">step {flag.step}</span>
                  <span>·</span>
                  <span>{flag.flag_type.replace(/_/g, " ")}</span>
                  <span>·</span>
                  <span>{flag.owning_body.replace(/_/g, " ")}</span>
                </div>
                <p className="mt-1 text-amber-900">{flag.context}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Run history
        </h2>
        <ol className="space-y-1 font-mono text-xs text-slate-600">
          {timeline.history.map((entry, i) => (
            <li key={i}>{entry}</li>
          ))}
        </ol>
      </section>
    </div>
  );
}
