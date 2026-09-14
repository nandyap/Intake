/**
 * API client for the M42 Intake Agent backend.
 *
 * Requests proxy through the Next.js API route so the browser never needs
 * a backend URL, and so the container app can keep the backend on the
 * internal network.
 */

// ---------------------------------------------------------------------------
// Types — mirror the backend pydantic contracts
// ---------------------------------------------------------------------------

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_owner_confirmation"
  | "awaiting_coe_review"
  | "awaiting_architect_review"
  | "awaiting_divergence_approval"
  | "rejected"
  | "returned_as_integration"
  | "completed"
  | "failed";

export type GateType =
  | "OwnerConfirmationRequest"
  | "CoEReviewRequest"
  | "ArchitectReviewRequest";

export interface PendingGate {
  request_id: string;
  gate_type: GateType;
  data: Record<string, unknown>;
}

export interface RunSummary {
  tracking_reference: string;
  submission_id: string;
  status: RunStatus;
  current_step: number;
  steps_completed: number[];
  gap_flag_count: number;
  loop_counts: Record<string, number>;
  awaiting_human: boolean;
  pending_gates: PendingGate[];
  recommendation: string | null;
  annual_value: number | null;
  error: string | null;
  started_at: string;
}

export interface ArtifactRef {
  id: string;
  version: string;
  is_seed: boolean;
}

export interface TimelineStep {
  step: number;
  performed_by: string;
  tier: "D0" | "D1" | "D2";
  is_stub: boolean;
  gap_flags: number;
  requires_input: number;
  artifacts: ArtifactRef[];
}

export interface GapFlag {
  flag_type: string;
  step: number;
  context: string;
  owning_body: string;
}

export interface Timeline {
  tracking_reference: string;
  status: RunStatus;
  steps: TimelineStep[];
  history: string[];
  gap_flags: GapFlag[];
}

export interface ArtifactStatus {
  artifact_id: string;
  version: string;
  status: string;
  owner: string;
  expires_at: string | null;
  available: boolean;
}

export interface Health {
  status: string;
  model_provider_configured: boolean;
  mode: "agents" | "stub";
  fail_closed: boolean;
  seeds_allowed: boolean;
}

/** Step metadata — the owning bounded context and determinism tier. */
export const STEP_META: Record<number, { name: string; owner: string }> = {
  3: { name: "Frame use case", owner: "Business Analyst" },
  4: { name: "Decompose elements", owner: "Business Architect" },
  5: { name: "Match capabilities", owner: "Business Architect" },
  6: { name: "Match realisations", owner: "Application Architect" },
  7: { name: "Assign criticality band", owner: "Risk Officer" },
  8: { name: "Feasibility verdict", owner: "Feasibility service" },
  9: { name: "Derive quality attributes", owner: "Product Owner" },
  10: { name: "Check ontology", owner: "Data Architect" },
  11: { name: "Sequence workflow", owner: "Business Analyst" },
  13: { name: "Confirm criticality class", owner: "Risk Officer" },
  14: { name: "Declare assertions", owner: "Product Owner" },
  15: { name: "Readiness verdict", owner: "Readiness service" },
  16: { name: "Classify determinism", owner: "Solution Architect" },
  17: { name: "Assign facet vectors", owner: "Risk Officer" },
  18: { name: "Derive exposure and influence", owner: "Risk derivation service" },
  19: { name: "Evaluate obligations", owner: "Policy service" },
  20: { name: "Select build surface", owner: "Technology Architect" },
  21: { name: "Select components", owner: "Solution Architect" },
  22: { name: "Compose architecture", owner: "Composition service" },
};

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),

  artifacts: () =>
    request<{ artifacts: ArtifactStatus[]; seed_count: number; total: number }>(
      "/api/artifacts",
    ),

  listRuns: () => request<{ runs: RunSummary[] }>("/api/runs"),

  getRun: (ref: string) => request<RunSummary>(`/api/runs/${ref}`),

  getTimeline: (ref: string) => request<Timeline>(`/api/runs/${ref}/timeline`),

  getPack: (ref: string) =>
    request<Record<string, unknown>>(`/api/runs/${ref}/pack`),

  submit: (payload: Record<string, unknown>) =>
    request<RunSummary>("/api/submissions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  answerGate: (ref: string, requestId: string, payload: Record<string, unknown>) =>
    request<RunSummary>(`/api/runs/${ref}/gates`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, payload }),
    }),
};
