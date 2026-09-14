"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";

/**
 * Submission form — Appendix A, Q0–Q30.
 *
 * This is the short path. The full 8-section questionnaire and the batch
 * upload follow; the fields here are the ones the Phase 1 derivation and
 * the initial business case actually consume.
 */
export default function SubmitPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    const form = new FormData(e.currentTarget);
    const get = (k: string) => String(form.get(k) ?? "");
    const num = (k: string) => {
      const v = form.get(k);
      return v === null || v === "" ? null : Number(v);
    };

    const payload: Record<string, unknown> = {
      pathway: "comprehensive",
      channel: "form",
      q0_org_unit: get("q0"),
      q1_full_name: get("q1"),
      q2_department: get("q2"),
      q3_job_title: get("q3"),
      q4_relationship: get("q4"),
      q5_task_description: get("q5"),
      q6_categories: splitList(get("q6")),
      q7_goals: splitList(get("q7")),
      q8_biggest_value: get("q8"),
      q10_step_count: get("q10"),
      q11_conditional_logic: get("q11"),
      q12_systems: splitList(get("q12")),
      q12b_write_back_targets: splitList(get("q12b")),
      q13_systems_purpose: get("q13"),
      q14_data_types: splitList(get("q14")),
      q15_change_frequency: get("q15"),
      q16_volume_pattern: get("q16"),
      q16_annual_volume: num("q16v"),
      q17_effort_table: [
        {
          role: get("role"),
          role_band: get("role_band"),
          headcount: Number(get("headcount") || 1),
          frequency_per_week: Number(get("freq") || 1),
          current_minutes: num("current_min"),
          expected_minutes: num("expected_min"),
        },
      ],
      q18_error_rate: get("q18"),
      q19_sensitive_data: splitList(get("q19")),
      q20_sign_off: get("q20"),
      q22_failure_impact: get("q22"),
      q24_data_readiness: get("q24"),
      q25_urgency: get("q25"),
      q28_estimated_annual_benefit_aed: num("q28"),
      q29_additional_context: get("q29"),
    };

    try {
      const run = await api.submit(payload);
      router.push(`/runs/${run.tracking_reference}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="max-w-3xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">New submission</h1>
        <p className="mt-1 text-sm text-slate-500">
          Agentic AI Use Case Readiness · the record persisted here drives the
          whole derivation.
        </p>
      </header>

      <Section title="Org and submitter" sub="Q0–Q4">
        <Select name="q0" label="Q0 · Part of the org" options={ORG} />
        <Field name="q1" label="Q1 · Full name" required />
        <Field name="q2" label="Q2 · Department / team" required />
        <Field name="q3" label="Q3 · Job title" required />
        <Select name="q4" label="Q4 · Relationship to this task" options={REL} />
      </Section>

      <Section title="Background" sub="Q5–Q8">
        <Area
          name="q5"
          label="Q5 · Describe the task and what triggers it"
          required
          rows={4}
          hint="State the problem, not a solution. Note where the human-led version is limited: time, cost, errors, waiting, rework, key-person dependency."
        />
        <Field name="q6" label="Q6 · Categories" hint="comma separated" />
        <Field name="q7" label="Q7 · Goals" hint="comma separated" />
        <Area name="q8" label="Q8 · Biggest value this would deliver" rows={2} />
      </Section>

      <Section title="Workflow structure" sub="Q10–Q17">
        <Select name="q10" label="Q10 · Distinct steps" options={STEPS} />
        <Select name="q11" label="Q11 · Conditional logic" options={LOGIC} />
        <Field name="q12" label="Q12 · Systems used" hint="comma separated" />
        <Field
          name="q12b"
          label="Q12b · Write-back targets"
          hint="EMR, ERP, HRIS, Dataverse, None"
        />
        <Field name="q13" label="Q13 · What the systems are used for" />
        <Field name="q14" label="Q14 · Data types" hint="comma separated" />
        <Select name="q15" label="Q15 · Change frequency" options={CHANGE} />
        <Select name="q16" label="Q16 · Volume pattern" options={VOLUME} />
        <Field name="q16v" label="Annual volume" type="number" />
      </Section>

      <Section
        title="Effort table"
        sub="Q17 — drives the business case"
        hint="Leave minutes blank if unknown. A missing value is reported as 'requires input', never estimated."
      >
        <Field name="role" label="Role" required />
        <Select name="role_band" label="Cost band" options={BANDS} />
        <Field name="headcount" label="Headcount" type="number" required />
        <Field name="freq" label="Times per week" type="number" required />
        <Field name="current_min" label="Minutes today" type="number" />
        <Field name="expected_min" label="Minutes after" type="number" />
      </Section>

      <Section title="Risk and compliance" sub="Q18–Q22">
        <Select name="q18" label="Q18 · Error / rework rate" options={ERRORS} />
        <Field name="q19" label="Q19 · Sensitive data" hint="comma separated" />
        <Select name="q20" label="Q20 · Sign-off required" options={SIGNOFF} />
        <Select
          name="q22"
          label="Q22 · Impact if it fails"
          options={IMPACT}
          hint="Critical means an error would cause severe or permanent harm — these are rejected at the feasibility gate."
        />
      </Section>

      <Section title="Readiness and value" sub="Q24–Q29">
        <Select name="q24" label="Q24 · Data availability" options={READY} />
        <Select name="q25" label="Q25 · Urgency" options={URGENCY} />
        <Field
          name="q28"
          label="Q28 · Estimated annual benefit (AED)"
          type="number"
        />
        <Area name="q29" label="Q29 · Additional context" rows={2} />
      </Section>

      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
      >
        {busy ? "Submitting…" : "Submit and start derivation"}
      </button>
    </form>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Field primitives
// ---------------------------------------------------------------------------

function Section({
  title,
  sub,
  hint,
  children,
}: {
  title: string;
  sub: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="rounded border border-slate-200 bg-white p-5">
      <legend className="px-2 text-sm font-semibold text-slate-700">
        {title} <span className="font-normal text-slate-400">· {sub}</span>
      </legend>
      {hint && <p className="mb-3 text-xs text-slate-500">{hint}</p>}
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function Label({ label, hint }: { label: string; hint?: string }) {
  return (
    <>
      <span className="block text-xs font-medium text-slate-600">{label}</span>
      {hint && <span className="mt-0.5 block text-[11px] text-slate-400">{hint}</span>}
    </>
  );
}

const INPUT =
  "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none";

function Field({
  name,
  label,
  hint,
  type = "text",
  required,
}: {
  name: string;
  label: string;
  hint?: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <Label label={label} hint={hint} />
      <input name={name} type={type} required={required} className={INPUT} />
    </label>
  );
}

function Area({
  name,
  label,
  hint,
  rows = 3,
  required,
}: {
  name: string;
  label: string;
  hint?: string;
  rows?: number;
  required?: boolean;
}) {
  return (
    <label className="block sm:col-span-2">
      <Label label={label} hint={hint} />
      <textarea name={name} rows={rows} required={required} className={INPUT} />
    </label>
  );
}

function Select({
  name,
  label,
  options,
  hint,
}: {
  name: string;
  label: string;
  options: string[];
  hint?: string;
}) {
  return (
    <label className="block">
      <Label label={label} hint={hint} />
      <select name={name} className={INPUT} defaultValue={options[0]}>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

// Option lists — must match the backend enums exactly.
const ORG = ["Engineering", "Operational", "Clinical", "Consultancy"];
const REL = [
  "I perform it myself",
  "I manage the team",
  "I am an internal customer",
];
const STEPS = ["1-5", "6-15", "16-30", ">30"];
const LOGIC = ["No", "A few simple conditions", "Many or nested rules"];
const CHANGE = ["Rarely", "Occasionally", "Frequently"];
const VOLUME = ["Consistent", "Predictable peaks", "Highly variable"];
const BANDS = ["admin", "nurse", "doctor"];
const ERRORS = [
  "Rarely <1%",
  "Occasionally 1-5%",
  "Frequently >5%",
  "Unknown",
];
const SIGNOFF = ["Mandatory human approval", "Audit trail only", "No"];
const IMPACT = ["Low", "Medium", "High", "Critical"];
const READY = ["Yes fully", "Partially", "No, work needed first"];
const URGENCY = ["Critical", "High", "Medium", "Low"];
