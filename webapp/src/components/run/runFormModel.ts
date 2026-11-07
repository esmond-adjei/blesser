import type { ProgramSeed, Run, SchoolTier } from "../../lib/types"

/** Degree levels offered. Values are free-form backend prompt text. */
export const DEGREES: { value: string; label: string }[] = [
  { value: "phd", label: "PhD" },
  { value: "masters", label: "Master's" },
  { value: "mba", label: "MBA" },
  { value: "jd", label: "JD, Law" },
  { value: "md", label: "MD, Medicine" },
  { value: "pharmd", label: "PharmD" },
  { value: "mph", label: "MPH" },
  { value: "dds", label: "DDS, Dental" },
]

export const SCHOOL_TIERS: { value: SchoolTier; label: string; hint: string }[] = [
  { value: "top", label: "Top", hint: "Most selective, world top ~50" },
  { value: "strong", label: "Strong", hint: "Highly ranked, ~50-200" },
  { value: "solid", label: "Solid", hint: "Research-active, ~200-500" },
  { value: "accessible", label: "Accessible", hint: "Less selective or regional" },
]

export const RUN_DIALS = {
  maxPrograms: { label: "Programmes", hint: "Schools researched", min: 1, max: 30, fallback: 10 },
  maxProfessors: { label: "Professors", hint: "Matches kept in total", min: 5, max: 100, fallback: 30 },
  maxPerProgram: { label: "Per programme", hint: "Faculty looked at in each", min: 1, max: 20, fallback: 5 },
} as const
export type DialKey = keyof typeof RUN_DIALS

export interface RunFormValue {
  interest: string
  degrees: string[]
  customDegrees: string[]
  regions: string[]
  fields: string[]
  seeds: ProgramSeed[]
  maxPrograms: number
  maxProfessors: number
  maxPerProgram: number
  flowId: string
  /** Tiers to target; empty = no preference. */
  schoolTiers: SchoolTier[]
  /** "default", "system" or a configured provider. */
  model: string
}

export const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean)

export function runToForm(run: Run): RunFormValue {
  const known = new Set(DEGREES.map((d) => d.value))
  // "either" predates multi-select degrees: it meant PhD or Master's.
  const levels = [...new Set(splitList(run.degree_level).flatMap((l) => (l.toLowerCase() === "either" ? ["phd", "masters"] : [l])))]
  return {
    interest: run.interest_statement,
    degrees: levels.filter((l) => known.has(l)),
    customDegrees: levels.filter((l) => !known.has(l)),
    regions: splitList(run.region),
    fields: splitList(run.field),
    seeds: [],
    maxPrograms: run.max_programs ?? RUN_DIALS.maxPrograms.fallback,
    maxProfessors: run.max_professors ?? RUN_DIALS.maxProfessors.fallback,
    maxPerProgram: run.max_professors_per_program ?? RUN_DIALS.maxPerProgram.fallback,
    flowId: run.flow_id ?? "standard",
    schoolTiers: run.school_tiers ?? [],
    model: run.llm_provider ?? "default",
  }
}

export const completeSeeds = (v: RunFormValue) =>
  v.seeds.filter((s) => s.school_name.trim() && s.program_name.trim())

export type RunFormErrors = Partial<Record<"interest" | "degrees" | "scope" | "budgets", string>>

export function validateRun(
  v: RunFormValue,
  mode: "create" | "edit",
  originalInterest?: string,
  original?: RunFormValue,
): RunFormErrors {
  const e: RunFormErrors = {}
  // Edit only re-checks an interest you changed, so older short statements
  // never block a limits-only edit.
  const interestTouched = mode === "create" || v.interest.trim() !== (originalInterest ?? "").trim()
  if (interestTouched && v.interest.trim().length < 20)
    e.interest = "Describe your interests in at least a sentence. Every professor is scored against it."
  if (mode === "create") {
    if (v.degrees.length + v.customDegrees.length === 0) e.degrees = "Pick at least one degree."
    if (completeSeeds(v).length === 0 && (v.regions.length === 0 || v.fields.length === 0))
      e.scope = "Add at least one region and one field, or list specific schools."
  }
  // Edit checks only limits you changed, so runs stored outside the dials'
  // range still save an interest edit.
  const changed = (key: DialKey) => mode === "create" || !original || v[key] !== original[key]
  for (const key of Object.keys(RUN_DIALS) as DialKey[]) {
    const d = RUN_DIALS[key]
    if (changed(key) && (v[key] < d.min || v[key] > d.max))
      e.budgets = `${d.label} must be between ${d.min} and ${d.max}.`
  }
  if ((changed("maxPerProgram") || changed("maxProfessors")) && v.maxPerProgram > v.maxProfessors)
    e.budgets = "Per-programme faculty can't exceed the total professors."
  return e
}
