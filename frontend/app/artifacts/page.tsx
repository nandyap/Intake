"use client";

import { useEffect, useState } from "react";

import { api, type ArtifactStatus, type Health } from "@/lib/api";

/**
 * Governance board — which governed artifacts exist, and which are seeds.
 *
 * In Phase 1 this is the single most operationally important screen: it
 * shows exactly how much of a derivation rests on artifacts M42 has not
 * yet delivered.
 */
export default function ArtifactsPage() {
  const [artifacts, setArtifacts] = useState<ArtifactStatus[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [counts, setCounts] = useState({ seed: 0, total: 0 });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [res, healthRes] = await Promise.all([
          api.artifacts(),
          api.health(),
        ]);
        setArtifacts(res.artifacts);
        setCounts({ seed: res.seed_count, total: res.total });
        setHealth(healthRes);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  if (error) {
    return (
      <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Governance</h1>
        <p className="mt-1 text-sm text-slate-500">
          Retrieval is version-pinned and fails closed. A stale or missing
          artifact stops the step that needs it.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Artifacts" value={String(counts.total)} />
        <Stat
          label="Still seeds"
          value={String(counts.seed)}
          tone={counts.seed > 0 ? "warn" : "ok"}
        />
        <Stat
          label="Mode"
          value={health?.mode ?? "—"}
          tone={health?.mode === "stub" ? "warn" : "ok"}
        />
      </div>

      {counts.seed > 0 && (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>{counts.seed} artifact(s) are seeds.</strong> They were
          authored by Microsoft Factory so the engine can run before M42
          delivers the governed versions. Any derivation relying on them is
          provisional and must be re-run once the governed artifact lands —
          which is a version bump here, not a code change.
        </div>
      )}

      <div className="overflow-hidden rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Artifact</th>
              <th className="px-4 py-3 font-medium">Version</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Owner</th>
              <th className="px-4 py-3 font-medium">Resolvable</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {artifacts.map((a) => (
              <tr key={a.artifact_id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono text-xs">{a.artifact_id}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  {a.version}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded border px-2 py-0.5 text-xs ${
                      a.status === "seed"
                        ? "border-amber-200 bg-amber-50 text-amber-700"
                        : "border-emerald-200 bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {a.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{a.owner || "—"}</td>
                <td className="px-4 py-3">
                  {a.available ? (
                    <span className="text-emerald-700">yes</span>
                  ) : (
                    <span className="text-rose-700">no — fails closed</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "ok",
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`mt-1 text-2xl font-semibold ${
          tone === "warn" ? "text-amber-700" : "text-slate-900"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
