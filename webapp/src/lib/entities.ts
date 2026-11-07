/** Shared wording for entities so every view names facts the same way.
 * Values join with words and commas, never separator dots. */

/** "Computer Science at University of Toronto"; either part may be missing. */
export function professorPlace(program?: string | null, school?: string | null): string {
  if (program && school) return `${program} at ${school}`
  return program || school || "Affiliation unknown"
}

/** OpenAlex ids come bare ("A123") or as URLs. */
export function openAlexUrl(id?: string | null): string | null {
  if (!id) return null
  return id.startsWith("http") ? id : `https://openalex.org/${id}`
}

/** "toronto.ca" from "https://www.toronto.ca/path". */
export function hostOf(url?: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

export function sentence(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1).replace(/_/g, " ") : s
}

/** Candidate statuses that differ from the default and earn a pill in rows and cards. */
const NOTABLE_CANDIDATE_STATUSES = new Set(["approved", "rejected", "drafted", "sent"])

export function notableCandidateStatus(status: string): boolean {
  return NOTABLE_CANDIDATE_STATUSES.has(status)
}

/** Markdown reduced to plain text, for one- or two-line excerpts on cards. */
export function plainText(md?: string | null): string {
  if (!md) return ""
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`~#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim()
}
