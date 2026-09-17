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
  | "awaiting_criticality_confirmation"
  | "awaiting_architect_review"
  | "awaiting_divergence_approval"
  | "rejected"
  | "returned_as_integration"
  | "completed"
  | "failed";

export type GateType =
  | "OwnerConfirmationRequest"
  | "CoEReviewRequest"
  | "CriticalityConfirmationRequest"
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

export interface SampleSummary {
  id: string;
  label: string;
  expect: string;
  why: string;
}

/** The scoping-grade deliverable, shaped for reading. */
export interface DesignPack {
  tracking_reference: string;
  status: RunStatus;
  is_complete: boolean;
  framing: {
    problem_statement: string | null;
    accountable_owner: string | null;
    expected_change: string | null;
  };
  capability_coverage: {
    matched: { business_function: string; l3_capability_name: string }[];
    unmatched_functions: string[];
  };
  reuse: {
    recommendation: string | null;
    rationale: string | null;
    entries: { element: string; realisation: string; confidence: string }[];
  };
  risk: {
    criticality_band: string | null;
    dominant_failure_mode: string | null;
    per_step: { node_id: string; exposure: string; influence: string }[];
  };
  gates: {
    feasibility: {
      outcome: string | null;
      reasons: string[];
      rules: {
        rule_id: string;
        description: string;
        provenance: string;
        triggered: boolean;
        detail: string;
      }[];
    };
    readiness: { outcome: string | null; conditions: string[] };
  };
  workflow: {
    nodes: { node_id: string; activity_verb: string; performing_element: string }[];
    edges: { from_node: string; to_node: string; data_class: string }[];
    governance_tier: string | null;
  };
  quality_attributes: Record<string, unknown>[];
  assertions: Record<string, unknown>[];
  controls: { obligation_id: string; title: string; applies_to_nodes: string[] }[];
  architecture: {
    build_surface: string | null;
    build_surface_rationale: string | null;
    conditional_obligations: string[];
    components: { capability: string; chosen_name: string; rationale: string }[];
    decision_records: Record<string, unknown>[];
    conformance_validated: boolean;
    conformance_violations: string[];
  };
  business_case: {
    recommendation?: string;
    annual_value?: number | null;
    annual_operational_saving?: number | null;
    annual_quality_saving?: number | null;
    currency?: string;
    narrative?: string;
    gate_conditions?: string[];
    lines?: {
      label: string;
      value: number | null;
      bucket: string;
      formula: string;
      source: string;
      requires_input: boolean;
    }[];
    positions?: {
      role: string;
      headcount: number;
      annual_hours: number | null;
      annual_cost: number | null;
      annual_saving: number | null;
      requires_input: boolean;
    }[];
  };
  gap_flags: GapFlag[];
}

/** One step's raw validated output, as produced by that step. */
export interface StepOutput {
  step: number;
  /** Provenance every step carries — says how far to trust the payload. */
  envelope: {
    step: number;
    tier: string;
    performed_by: string;
    produced_at: string;
    is_stub: boolean;
    artifacts_consulted: { artifact_id: string; version: string; is_seed: boolean }[];
    gap_flags: GapFlag[];
    requires_input: { field_name: string; reason: string; gate_condition: string }[];
  };
  /** The step's own output — shape differs per step. */
  payload: Record<string, unknown>;
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

  getStepOutput: (ref: string, step: number) =>
    request<StepOutput>(`/api/runs/${ref}/steps/${step}`),

  getPack: (ref: string) =>
    request<Record<string, unknown>>(`/api/runs/${ref}/pack`),

  getDesign: (ref: string) => request<DesignPack>(`/api/runs/${ref}/design`),

  listSamples: () =>
    request<{ samples: SampleSummary[] }>("/api/samples"),

  getSample: (id: string) =>
    request<Record<string, unknown>>(`/api/samples/${id}`),

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
