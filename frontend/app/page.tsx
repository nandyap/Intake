"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/badges";
import { api, type Health, type RunSummary } from "@/lib/api";

export default function SubmissionsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [runsRes, healthRes] = await Promise.all([
          api.listRuns(),
          api.health(),
        ]);
        if (cancelled) return;
        setRuns(runsRes.runs);
        setHealth(healthRes);
        setError(null);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    // Runs advance in the background; poll so gates appear without a reload.
    const timer = setInterval(load, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Submissions</h1>
          <p className="mt-1 text-sm text-slate-500">
            Each submission runs the CAFÉ derivation, steps 3 to 22.
          </p>
        </div>
        <Link
          href="/submit"
          className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
        >
          New submission
        </Link>
      </div>

      {health?.mode === "stub" && (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>Stub mode.</strong> No model provider is configured, so every
          agentic step returns a schema-valid placeholder. The graph, its gates
          and the deterministic services are fully exercised; the derivation
          content is not real.
        </div>
      )}

      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : runs.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-10 text-center">
          <p className="text-slate-500">No submissions yet.</p>
          <Link
            href="/submit"
            className="mt-3 inline-block text-sm font-medium text-teal-700 hover:underline"
          >
            Submit the first use case
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Tracking reference</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Progress</th>
                <th className="px-4 py-3 font-medium">Recommendation</th>
                <th className="px-4 py-3 font-medium">Annual value</th>
                <th className="px-4 py-3 font-medium">Gaps</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((run) => (
                <tr key={run.tracking_reference} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/runs/${run.tracking_reference}`}
                      className="font-mono text-xs font-medium text-teal-700 hover:underline"
                    >
                      {run.tracking_reference}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={run.status} />
                    {run.awaiting_human && (
                      <span className="ml-2 text-xs text-amber-700">
                        needs a decision
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {run.steps_completed.length} / 19 steps
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {run.recommendation?.replace(/_/g, " ") ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {run.annual_value
                      ? `${run.annual_value.toLocaleString()} AED`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {run.gap_flag_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
