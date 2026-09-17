"use client";

import { useState } from "react";

import { api, type PendingGate } from "@/lib/api";

/**
 * The human decision console.
 *
 * Renders whichever gate the run is paused at. Each gate offers exactly
 * the decisions the sponsor specified — including the return-for-info and
 * re-prompt paths, which are declared loops in the graph, not ad-hoc
 * retries.
 */
export function GateConsole({
  trackingReference,
  gate,
  onAnswered,
}: {
  trackingReference: string;
  gate: PendingGate;
  onAnswered: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const [who, setWho] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function answer(payload: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await api.answerGate(trackingReference, gate.request_id, payload);
      setNotes("");
      onAnswered();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const data = gate.data as Record<string, unknown>;

  return (
    <section className="rounded border-2 border-amber-300 bg-amber-50 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-800">
        {GATE_TITLES[gate.gate_type] ?? "Decision required"}
      </h2>
      <p className="mt-1 text-sm text-amber-900">
        {(data.prompt as string) ?? "A human decision is required to continue."}
      </p>

      <dl className="mt-4 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
        {GATE_FIELDS[gate.gate_type]?.map(([key, label]) => {
          const value = data[key];
          if (value === undefined || value === null || value === "") return null;
          return (
            <div key={key}>
              <dt className="text-xs uppercase tracking-wide text-amber-700">
                {label}
              </dt>
              <dd className="text-amber-950">
                {Array.isArray(value)
                  ? value.length > 0
                    ? value.join("; ")
                    : "none"
                  : String(value)}
              </dd>
            </div>
          );
        })}
      </dl>

      <div className="mt-4 space-y-3">
        <input
          value={who}
          onChange={(e) => setWho(e.target.value)}
          placeholder="Your name (recorded in the audit trail)"
          className="w-full rounded border border-amber-300 bg-white px-3 py-2 text-sm"
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes, corrections, or re-prompt guidance"
          rows={2}
          className="w-full rounded border border-amber-300 bg-white px-3 py-2 text-sm"
        />
      </div>

      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {gate.gate_type === "OwnerConfirmationRequest" && (
          <>
            <Button
              disabled={busy}
              tone="approve"
              onClick={() =>
                answer({ confirmed: true, confirmed_by: who, corrections: notes })
              }
            >
              Confirm
            </Button>
            <Button
              disabled={busy}
              tone="return"
              onClick={() =>
                answer({
                  confirmed: false,
                  confirmed_by: who,
                  corrections: notes,
                })
              }
            >
              Request corrections
            </Button>
          </>
        )}

        {gate.gate_type === "CoEReviewRequest" && (
          <>
            <Button
              disabled={busy}
              tone="approve"
              onClick={() =>
                answer({ decision: "approve", reviewed_by: who, notes })
              }
            >
              Accept
            </Button>
            <Button
              disabled={busy}
              tone="return"
              onClick={() =>
                answer({
                  decision: "return_for_info",
                  reviewed_by: who,
                  notes,
                  information_requested: notes ? [notes] : [],
                })
              }
            >
              Return for information
            </Button>
            <Button
              disabled={busy}
              tone="reject"
              onClick={() =>
                answer({ decision: "reject", reviewed_by: who, notes })
              }
            >
              Reject
            </Button>
          </>
        )}

        {gate.gate_type === "CriticalityConfirmationRequest" && (
          <>
            <Button
              disabled={busy}
              tone="approve"
              onClick={() =>
                answer({
                  confirmed: true,
                  confirmed_class: String(data.proposed_class ?? ""),
                  confirmed_by: who,
                  notes,
                })
              }
            >
              Confirm class
            </Button>
            {CRITICALITY_CLASSES.filter(
              (c) => c !== String(data.proposed_class ?? ""),
            ).map((c) => (
              <Button
                key={c}
                disabled={busy}
                tone="return"
                onClick={() =>
                  answer({
                    confirmed: true,
                    confirmed_class: c,
                    confirmed_by: who,
                    notes,
                  })
                }
              >
                Substitute &ldquo;{c}&rdquo;
              </Button>
            ))}
            <Button
              disabled={busy}
              tone="reject"
              onClick={() =>
                answer({ confirmed: false, confirmed_by: who, notes })
              }
            >
              Reject
            </Button>
          </>
        )}

        {gate.gate_type === "ArchitectReviewRequest" && (
          <>
            <Button
              disabled={busy}
              tone="approve"
              onClick={() =>
                answer({ decision: "approve", reviewed_by: who, notes })
              }
            >
              Approve design
            </Button>
            <Button
              disabled={busy}
              tone="return"
              onClick={() =>
                answer({
                  decision: "re_prompt",
                  reviewed_by: who,
                  notes,
                  re_prompt_guidance: notes,
                })
              }
            >
              Re-prompt
            </Button>
            <Button
              disabled={busy}
              tone="reject"
              onClick={() =>
                answer({ decision: "reject", reviewed_by: who, notes })
              }
            >
              Reject
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

const CRITICALITY_CLASSES = ["routine", "significant", "severe"];

const GATE_TITLES: Record<string, string> = {
  OwnerConfirmationRequest: "Business owner confirmation",
  CoEReviewRequest: "AI CoE review",
  CriticalityConfirmationRequest: "Criticality class confirmation (step 13)",
  ArchitectReviewRequest: "Architect review",
};

const GATE_FIELDS: Record<string, [string, string][]> = {
  OwnerConfirmationRequest: [
    ["problem_statement", "Problem"],
    ["accountable_owner", "Accountable owner"],
    ["expected_change", "Expected change"],
    ["stated_objective", "Objective"],
  ],
  CoEReviewRequest: [
    ["feasibility_outcome", "Feasibility"],
    ["criticality_band", "Criticality"],
    ["reuse_recommendation", "Reuse"],
    ["unresolved_inputs", "Unresolved inputs"],
  ],
  CriticalityConfirmationRequest: [
    ["proposed_class", "Proposed class"],
    ["provisional_band", "Provisional band (step 7)"],
    ["dominant_failure_mode", "Dominant failure mode"],
    ["is_homogeneous", "Homogeneous"],
    ["workflow_node_count", "Workflow nodes"],
  ],
  ArchitectReviewRequest: [
    ["build_surface", "Build surface"],
    ["component_count", "Components"],
    ["obligation_count", "Obligations"],
    ["conformance_validated", "Conformance validated"],
    ["conformance_violations", "Violations"],
    ["divergences", "Divergences from request"],
  ],
};

const TONES = {
  approve: "bg-emerald-700 hover:bg-emerald-600",
  return: "bg-amber-700 hover:bg-amber-600",
  reject: "bg-rose-700 hover:bg-rose-600",
};

function Button({
  children,
  onClick,
  disabled,
  tone,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled: boolean;
  tone: keyof typeof TONES;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-4 py-2 text-sm font-medium text-white transition disabled:opacity-50 ${TONES[tone]}`}
    >
      {children}
    </button>
  );
}
