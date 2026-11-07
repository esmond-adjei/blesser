/** Read a run's settings out of what people already typed: the interest
 * names degree, place and field; the last run supplies the rest. No model calls. */
import type { ProgramSeed, RunListItem, SchoolTier } from "./types"
import { ANYWHERE, DEGREE_VOCAB, FIELD_VOCAB, PLACE_VOCAB, findInText } from "./vocab"

export interface Inferred {
  degrees: string[]
  places: string[]
  fields: string[]
}

export function inferFromInterest(text: string): Inferred {
  return {
    degrees: findInText(text, DEGREE_VOCAB),
    places: findInText(text, PLACE_VOCAB),
    fields: findInText(text, FIELD_VOCAB).slice(0, 2),
  }
}

/** Run-size presets: (programmes, professors kept, faculty per programme). */
export const RUN_SIZES = {
  quick: { label: "Quick", maxPrograms: 5, maxProfessors: 15, maxPerProgram: 3 },
  standard: { label: "Standard", maxPrograms: 10, maxProfessors: 30, maxPerProgram: 5 },
  deep: { label: "Deep", maxPrograms: 20, maxProfessors: 60, maxPerProgram: 6 },
} as const
export type RunSize = keyof typeof RUN_SIZES

export function sizeOf(v: { maxPrograms: number; maxProfessors: number; maxPerProgram: number }): RunSize | "custom" {
  for (const [key, s] of Object.entries(RUN_SIZES) as [RunSize, (typeof RUN_SIZES)[RunSize]][]) {
    if (s.maxPrograms === v.maxPrograms && s.maxProfessors === v.maxProfessors && s.maxPerProgram === v.maxPerProgram)
      return key
  }
  return "custom"
}

const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean)

/** "either" predates multi-select degrees: it meant PhD or Master's. */
export function normalizeDegrees(levels: string[]): string[] {
  const out = levels.flatMap((l) => (l.toLowerCase() === "either" ? ["phd", "masters"] : [l]))
  return [...new Set(out)]
}

export interface RunDefaults {
  degrees: string[]
  regions: string[]
  schoolTiers: SchoolTier[]
  maxPrograms: number
  maxProfessors: number
  maxPerProgram: number
  flowId: string
  /** The run's model: "system", a configured provider, or "default"
   * (not picked: the account's default, Auto unless it opted in). */
  model: string
}

/** Defaults carried over from the newest discovery run, if any. */
export function defaultsFromRuns(runs: RunListItem[] | undefined): RunDefaults {
  const last = (runs ?? []).find((r) => r.region !== "(preselected list)")
  const size = RUN_SIZES.standard
  if (!last)
    return {
      degrees: ["phd"],
      regions: [],
      schoolTiers: [],
      maxPrograms: size.maxPrograms,
      maxProfessors: size.maxProfessors,
      maxPerProgram: size.maxPerProgram,
      flowId: "standard",
      model: "default",
    }
  const regions = split(last.region).filter((r) => r !== ANYWHERE)
  return {
    degrees: normalizeDegrees(split(last.degree_level)).slice(0, 4),
    regions,
    schoolTiers: last.school_tiers ?? [],
    maxPrograms: last.max_programs ?? size.maxPrograms,
    maxProfessors: last.max_professors ?? size.maxProfessors,
    maxPerProgram: last.max_professors_per_program ?? size.maxPerProgram,
    flowId: last.flow_id ?? "standard",
    // Never carried over: each run starts on the account default.
    model: "default",
  }
}

/** Places used in earlier runs, newest first, for one-click picks. */
export function recentPlaces(runs: RunListItem[] | undefined): string[] {
  const seen = new Set<string>()
  for (const r of runs ?? []) {
    if (r.region === "(preselected list)") continue
    for (const p of split(r.region)) if (p !== ANYWHERE) seen.add(p)
  }
  return [...seen].slice(0, 5)
}

/** Pasted target schools, one per line: "School — Programme", "School |
 * Programme" or a department URL. A line without a programme gets `fallbackProgram`. */
export function parseSchoolLines(text: string, fallbackProgram: string): ProgramSeed[] {
  const out: ProgramSeed[] = []
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^[-*•\d.)\s]+(?=\S)/, "")
    if (!line) continue
    const url = /https?:\/\/\S+/.exec(line)?.[0] ?? null
    const rest = url ? line.replace(url, "").trim() : line
    // No comma split: "University of California, Berkeley" is one school.
    const parts = rest.split(/\s+[—–-]\s+|\s*\|\s*|\t/).map((p) => p.trim()).filter(Boolean)
    let school = parts[0] ?? ""
    if (!school && url) {
      try {
        school = new URL(url).hostname.replace(/^www\./, "")
      } catch {
        school = url
      }
    }
    if (!school) continue
    out.push({
      school_name: school,
      program_name: parts.slice(1).join(", ") || fallbackProgram,
      school_country: "",
      department_url: url ?? "",
    })
  }
  return out
}
