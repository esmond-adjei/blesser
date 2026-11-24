import type { OpportunityKind } from "./types"

export const SCAN_KINDS: OpportunityKind[] = [
  "scholarship",
  "fellowship",
  "grant",
  "job",
  "internship",
  "accelerator",
  "incubator",
  "competition",
  "training",
  "conference",
  "call_for_proposals",
]

export const MAX_SCAN_KINDS = 3

export const KIND_PLURALS: Record<OpportunityKind, string> = {
  grant: "grants",
  fellowship: "fellowships",
  scholarship: "scholarships",
  accelerator: "accelerators",
  incubator: "incubators",
  competition: "competitions",
  internship: "internships",
  call_for_proposals: "calls for proposals",
  training: "training",
  conference: "conferences",
  job: "jobs",
  other: "other",
}

// Mirrors api/scans/service.py so scans started before listing types still get a specific name.
const KIND_WORDS: [OpportunityKind, string[]][] = [
  ["scholarship", ["scholarship", "bursar", "tuition"]],
  ["fellowship", ["fellowship"]],
  ["grant", ["grant", "funding", "seed fund"]],
  ["job", [" job", "jobs", "hiring", "career", "vacanc", "engineer role"]],
  ["internship", ["internship", "intern "]],
  ["accelerator", ["accelerator"]],
  ["incubator", ["incubat"]],
  ["competition", ["competition", "challenge", "prize", "hackathon"]],
  ["conference", ["conference", "summit"]],
  ["training", ["training", "bootcamp", "course"]],
  ["call_for_proposals", ["call for proposals", "proposals"]],
]

/** The listing types a scan is for: the ones picked, else any its focus names. */
export function scanKinds(kinds: OpportunityKind[] | undefined, focus = ""): OpportunityKind[] {
  if (kinds?.length) return kinds
  const text = ` ${focus.toLowerCase()} `
  return KIND_WORDS.filter(([, words]) => words.some((w) => text.includes(w))).map(([k]) => k).slice(0, MAX_SCAN_KINDS)
}

/** "scholarships", "scholarships and jobs", "grants, jobs and internships". */
export function kindsPhrase(kinds: OpportunityKind[]): string {
  const words = kinds.map((k) => KIND_PLURALS[k] ?? k)
  return words.length < 2 ? (words[0] ?? "") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`
}
