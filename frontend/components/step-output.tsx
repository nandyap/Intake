"use client";

import { useEffect, useState } from "react";

import { SeedBadge } from "@/components/badges";
import { api, type StepOutput } from "@/lib/api";

/**
 * The raw output one step produced.
 *
 * Shown when a timeline row is expanded. The design pack is curated — it
 * reads as a document and omits the steps that do not belong in one. This
 * is the opposite: exactly what the step wrote, with nothing hidden, so a
 * reviewer can answer "is this real?" for any step rather than only for
 * the ones the pack happens to render.
 *
 * The provenance envelope is separated from the payload because the two
 * answer different questions: the envelope says how far to trust the
 * output, the payload is the output.
 */
export function StepOutputPanel({
  trackingReference,
  step,
}: {
  trackingReference: string;
  step: number;
}) {
  const [data, setData] = useState<StepOutput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getStepOutput(trackingReference, step)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [trackingReference, step]);

  if (error) {
    return (
      <div className="px-4 py-3 text-sm text-rose-700">{error}</div>
    );
  }
  if (!data) {
    return (
      <div className="px-4 py-3 text-sm text-slate-500">Loading output…</div>
    );
  }

  const { envelope, payload } = data;
  const entries = Object.entries(payload);

  return (
    <div className="space-y-4 border-l-2 border-teal-200 bg-slate-50 px-5 py-4">
      {envelope.is_stub && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <strong>Placeholder output.</strong> No model provider is
          configured, so this step returned a schema-valid stub rather than
          reasoning. The shape below is what the agent will produce — the
          values are not derived.
        </p>
      )}

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Output
        </h4>
        {entries.length === 0 ? (
          <p className="text-sm text-slate-400">
            This step carries provenance only.
          </p>
        ) : (
          <pre className="max-h-96 overflow-auto rounded border border-slate-200 bg-white p-3 text-[11px] leading-relaxed text-slate-700">
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}
      </div>

      <div className="grid gap-4 text-xs sm:grid-cols-2">
        <div>
          <h4 className="mb-1.5 font-semibold uppercase tracking-wide text-slate-500">
            Provenance
          </h4>
          <dl className="space-y-1 text-slate-600">
            <div className="flex gap-2">
              <dt className="text-slate-400">Produced</dt>
              <dd>{new Date(envelope.produced_at).toLocaleString()}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-slate-400">By</dt>
              <dd>{envelope.performed_by}</dd>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <dt className="text-slate-400">Documents</dt>
              <dd className="flex flex-wrap gap-1">
                {envelope.artifacts_consulted.length === 0 ? (
                  <span className="text-slate-400">none</span>
                ) : (
                  envelope.artifacts_consulted.map((a) => (
                    <span
                      key={a.artifact_id}
                      className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px]"
                    >
                      {a.artifact_id}
                      {a.is_seed && <SeedBadge label="seed" />}
                    </span>
                  ))
                )}
              </dd>
            </div>
          </dl>
        </div>

        <div>
          <h4 className="mb-1.5 font-semibold uppercase tracking-wide text-slate-500">
            Unresolved
          </h4>
          {envelope.gap_flags.length === 0 &&
          envelope.requires_input.length === 0 ? (
            <p className="text-slate-400">Nothing left unresolved.</p>
          ) : (
            <ul className="space-y-1">
              {envelope.gap_flags.map((g, i) => (
                <li key={`g${i}`} className="text-amber-800">
                  • <span className="font-medium">{g.flag_type}</span> —{" "}
                  {g.context}
                </li>
              ))}
              {envelope.requires_input.map((r, i) => (
                <li key={`r${i}`} className="text-amber-800">
                  • <span className="font-medium">{r.field_name}</span> —{" "}
                  {r.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
