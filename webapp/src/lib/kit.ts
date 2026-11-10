import type {
  AnswerInput,
  Correction,
  DocumentKind,
  Education,
  Experience,
  LanguageLevel,
  Profile,
  ProfileInput,
  Project,
  ProjectInput,
  ProjectStage,
  Reference,
  TeamMember,
} from "./kitTypes"

export const KIT_PITCH = "Fill this once. The Blesser extension uses it to fill application forms for you."

export const DOCUMENT_KINDS: { value: DocumentKind; label: string }[] = [
  { value: "cv", label: "CV" },
  { value: "cover_letter", label: "Cover letter" },
  { value: "pitch_deck", label: "Pitch deck" },
  { value: "transcript", label: "Transcript" },
  { value: "certificate", label: "Certificate" },
  { value: "budget", label: "Budget" },
  { value: "financials", label: "Financials" },
  { value: "id_document", label: "ID document" },
  { value: "photo", label: "Photo" },
  { value: "logo", label: "Logo" },
  { value: "other", label: "Other" },
]

export const kindLabel = (kind: string) => DOCUMENT_KINDS.find((k) => k.value === kind)?.label ?? "Other"

export const STAGES: { value: ProjectStage; label: string }[] = [
  { value: "idea", label: "Idea" },
  { value: "prototype", label: "Prototype" },
  { value: "early_revenue", label: "Early revenue" },
  { value: "growth", label: "Growth" },
  { value: "other", label: "Other" },
]

export const stageLabel = (stage: string) => STAGES.find((s) => s.value === stage)?.label ?? "Other"

export const LANGUAGE_LEVELS: { value: LanguageLevel; label: string }[] = [
  { value: "basic", label: "Basic" },
  { value: "conversational", label: "Conversational" },
  { value: "fluent", label: "Fluent" },
  { value: "native", label: "Native" },
]

export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024
export const UPLOAD_EXTENSIONS = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "csv", "png", "jpg", "jpeg", "webp"]
export const UPLOAD_ACCEPT = UPLOAD_EXTENSIONS.map((e) => `.${e}`).join(",")
export const SHORT_BIO_MAX = 300

// --- Empty records -------------------------------------------------------------

export const emptyEducation = (): Education => ({ institution: "", qualification: "", field: "", start: null, end: null, grade: "", country: "" })
export const emptyExperience = (): Experience => ({ organization: "", role: "", start: null, end: null, current: false, location: "", summary: "" })
export const emptyReference = (): Reference => ({ name: "", title: "", organization: "", email: "", phone: "", relationship: "" })
export const emptyTeamMember = (): TeamMember => ({ name: "", role: "", bio: "", email: "", linkedin_url: "", is_founder: false, gender: "" })

export function emptyProject(name = ""): ProjectInput {
  return {
    name, tagline: "", website_url: "", logo_document_id: null, stage: "idea", sector: "", country: "", city: "",
    founded_on: null, legal_status: "", registration_number: "",
    problem: "", solution: "", target_customers: "", market_size: "", business_model: "", competition: "", traction: "", impact: "", why_now: "",
    team: [], team_size: null, women_led: false, youth_led: false,
    revenue_last_12_months: "", funding_raised: "", amount_sought: "", currency: "", use_of_funds: "",
    document_ids: [], custom_fields: [],
  }
}

// --- Normalisation before a save ----------------------------------------------------

const blank = (row: object) => Object.values(row).every((v) => v === "" || v === null || v === false || (typeof v === "string" && !v.trim()))

/** Adds https:// to a bare domain so "siwa.africa" passes URL validation. */
export function normalizeUrl(value: string): string {
  const v = value.trim()
  if (!v) return ""
  if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return v
  return `https://${v.replace(/^\/+/, "")}`
}

/** A month input ("2019-09") or a full date, as an ISO date; empty is null. */
export function monthToDate(value: string | null | undefined): string | null {
  const v = (value ?? "").trim()
  if (!v) return null
  if (/^\d{4}-\d{2}$/.test(v)) return `${v}-01`
  return v
}

/** The yyyy-mm a month input wants from a stored date. */
export const dateToMonth = (value: string | null | undefined) => (value ?? "").slice(0, 7)

/** A year field's text as a whole year, or null when empty or not a plausible year. */
export function parseYear(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const n = typeof value === "number" ? value : Number(String(value).trim())
  if (!Number.isInteger(n) || n < 1900 || n > 2100) return null
  return n
}

const trimAll = <T extends object>(row: T): T =>
  Object.fromEntries(Object.entries(row).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v])) as T

const rows = <T extends object>(list: T[], fix: (row: T) => T = (r) => r): T[] => list.map((r) => fix(trimAll(r))).filter((r) => !blank(r))

function omit<T extends object, K extends keyof T>(row: T, keys: K[]): Omit<T, K> {
  const copy = { ...row }
  for (const k of keys) delete copy[k]
  return copy
}

const uniqueTrimmed = (list: string[]) => [...new Set(list.map((s) => s.trim()).filter(Boolean))]

export function normalizeProfile(p: ProfileInput | Profile): ProfileInput {
  const base = trimAll(omit(p as Profile, ["completeness", "updated_at"]))
  return {
    ...base,
    date_of_birth: base.date_of_birth || null,
    linkedin_url: normalizeUrl(base.linkedin_url),
    website_url: normalizeUrl(base.website_url),
    github_url: normalizeUrl(base.github_url),
    other_links: rows(p.other_links, (l) => ({ ...l, url: normalizeUrl(l.url) })),
    education: rows(p.education, (e) => ({ ...e, start: monthToDate(e.start), end: monthToDate(e.end) })),
    experience: rows(p.experience, (e) => ({ ...e, start: monthToDate(e.start), end: e.current ? null : monthToDate(e.end) })),
    skills: uniqueTrimmed(p.skills),
    languages: p.languages.map((l) => ({ ...l, language: l.language.trim() })).filter((l) => l.language),
    awards: rows(p.awards, (a) => ({ ...a, year: parseYear(a.year) })),
    publications: rows(p.publications, (a) => ({ ...a, year: parseYear(a.year), url: normalizeUrl(a.url) })),
    references: rows(p.references),
    sensitive: { ...trimAll(p.sensitive), passport_expiry: p.sensitive.passport_expiry || null },
  }
}

/** "GHS 25,000" -> "25000": the API takes plain decimals. */
export function normalizeMoney(value: string): string {
  return value.replace(/[\s,]/g, "").replace(/^[^\d.-]+/, "")
}

export function normalizeProject(p: ProjectInput | Project): ProjectInput {
  const base = trimAll(omit(p as Project, ["id", "completeness", "created_at", "updated_at"]))
  const size = base.team_size === null || (base.team_size as unknown) === "" ? null : Math.round(Number(base.team_size))
  return {
    ...base,
    website_url: normalizeUrl(base.website_url),
    founded_on: base.founded_on || null,
    team: rows(p.team, (m) => ({ ...m, linkedin_url: normalizeUrl(m.linkedin_url) })),
    team_size: size !== null && Number.isFinite(size) && size >= 1 ? size : null,
    revenue_last_12_months: normalizeMoney(base.revenue_last_12_months),
    funding_raised: normalizeMoney(base.funding_raised),
    amount_sought: normalizeMoney(base.amount_sought),
    currency: base.currency.toUpperCase(),
    document_ids: [...new Set(p.document_ids)],
    custom_fields: rows(p.custom_fields),
  }
}

export function normalizeAnswer(a: AnswerInput): AnswerInput {
  return { question: a.question.trim(), answer: a.answer.trim(), tags: uniqueTrimmed(a.tags), project_id: a.project_id || null }
}

// --- Display helpers ------------------------------------------------------------

export function completenessLabel(value: number): string {
  const n = Math.round(Math.min(100, Math.max(0, value || 0)))
  if (n === 0) return "Not started"
  if (n < 40) return "Just started"
  if (n < 75) return "Taking shape"
  if (n < 100) return "Nearly there"
  return "Complete"
}

const listPhrase = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`

/** The first few empty fields worth filling, as one short sentence; null when nothing obvious is missing. */
export function nextSteps(gaps: string[], max = 3): string | null {
  if (!gaps.length) return null
  const shown = gaps.slice(0, max)
  const more = gaps.length - shown.length
  return `Add ${listPhrase(more ? [...shown, `${more} more`] : shown)}.`
}

export function profileGaps(p: ProfileInput): string[] {
  const checks: [boolean, string][] = [
    [!!(p.given_name.trim() && p.family_name.trim()), "your name"],
    [!!p.phone.trim(), "a phone number"],
    [!!p.country_of_residence.trim(), "where you live"],
    [!!p.nationality.trim(), "your nationality"],
    [!!p.headline.trim(), "a headline"],
    [!!p.short_bio.trim(), "a short bio"],
    [p.education.some((e) => !blank(e)), "your education"],
    [p.experience.some((e) => !blank(e)), "your experience"],
    [p.skills.length > 0, "skills"],
    [p.languages.length > 0, "languages"],
    [!!p.linkedin_url.trim(), "LinkedIn"],
    [p.references.some((r) => !blank(r)), "a reference"],
  ]
  return checks.filter(([ok]) => !ok).map(([, label]) => label)
}

export function projectGaps(p: ProjectInput): string[] {
  const checks: [boolean, string][] = [
    [!!p.tagline.trim(), "a tagline"],
    [!!p.problem.trim(), "the problem"],
    [!!p.solution.trim(), "the solution"],
    [!!p.target_customers.trim(), "target customers"],
    [!!p.business_model.trim(), "the business model"],
    [!!p.traction.trim(), "traction"],
    [p.team.some((m) => !blank(m)), "the team"],
    [!!p.amount_sought.trim(), "the amount you're seeking"],
    [!!p.country.trim(), "the country"],
    [p.document_ids.length > 0, "documents"],
  ]
  return checks.filter(([ok]) => !ok).map(([, label]) => label)
}

/** Words as application forms count them: runs of non-space, ignoring stray punctuation. */
export function wordCount(text: string): number {
  return text.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length
}

export type Limit = { count: number; unit: "words" | "characters" }

/** Reads a limit out of a question: "in 100 words", "(max 250 words)", "500 characters max". */
export function limitFromQuestion(question: string): Limit | null {
  const m = question.match(/(\d[\d,]*)\s*(?:-|–)?\s*(words?|characters?|chars?)\b/i)
  if (!m) return null
  const count = Number(m[1].replace(/,/g, ""))
  if (!count) return null
  return { count, unit: /^w/i.test(m[2]) ? "words" : "characters" }
}

export function limitStatus(text: string, limit: Limit | null): { used: number; over: boolean; near: boolean } {
  const used = limit?.unit === "characters" ? text.length : wordCount(text)
  if (!limit) return { used, over: false, near: false }
  return { used, over: used > limit.count, near: used <= limit.count && used >= limit.count * 0.9 }
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B"
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB"]
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v >= 100 || Number.isInteger(v) ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

export const fileExtension = (name: string) => (name.includes(".") ? name.split(".").pop()!.toLowerCase() : "")

/** Why a file can't be uploaded before it leaves the browser, or null. The server checks again by content. */
export function uploadProblem(file: { name: string; size: number }, usage?: { used_bytes: number; limit_bytes: number }): string | null {
  if (!UPLOAD_EXTENSIONS.includes(fileExtension(file.name))) return "That file type isn't supported. Use PDF, Word, PowerPoint, Excel, CSV or an image."
  if (file.size > MAX_UPLOAD_BYTES) return `Files can be up to ${formatBytes(MAX_UPLOAD_BYTES)}.`
  if (file.size === 0) return "That file is empty."
  if (usage && usage.used_bytes + file.size > usage.limit_bytes) return "Not enough storage left. Delete a file you no longer need."
  return null
}

/** A starting kind from the file name; the member can change it. */
export function guessKind(filename: string): DocumentKind {
  const ext = fileExtension(filename)
  const name = filename.toLowerCase().replace(/[_.-]+/g, " ")
  const has = (re: RegExp) => re.test(name)
  if (has(/\b(cv|resume|résumé)\b|curriculum/)) return "cv"
  if (has(/cover[\s_-]*letter|motivation/)) return "cover_letter"
  if (has(/pitch|deck/)) return "pitch_deck"
  if (has(/transcript/)) return "transcript"
  if (has(/certificate|cert\b|diploma|registration/)) return "certificate"
  if (has(/budget/)) return "budget"
  if (has(/financ|p&l|balance|cash[\s_-]*flow/)) return "financials"
  if (has(/passport|national[\s_-]*id|\bid[\s_-]*card|ghana[\s_-]*card/)) return "id_document"
  if (has(/logo/)) return "logo"
  if (["png", "jpg", "jpeg", "webp"].includes(ext)) return "photo"
  if (["xls", "xlsx", "csv"].includes(ext)) return "financials"
  if (["ppt", "pptx"].includes(ext)) return "pitch_deck"
  return "other"
}

/** "Ama_Mensah-CV_2026.pdf" -> "Ama Mensah CV 2026". */
export function titleFromFilename(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, "")
  const words = stem.replace(/[_\s]+/g, " ").replace(/\s*-\s*/g, " ").replace(/(\S)-(\S)/g, "$1 $2").trim()
  return (words || filename).slice(0, 120)
}

/** Masks all but the last four characters, the way the API does. */
export function maskSecret(value: string): string {
  if (!value) return ""
  if (value.length <= 4) return "•".repeat(value.length)
  return `${"•".repeat(Math.min(8, value.length - 4))}${value.slice(-4)}`
}

/** Corrections grouped by site, sites A to Z, newest first within each; `query` matches site, label or value. */
export function groupCorrections(list: Correction[], query = ""): { host: string; items: Correction[] }[] {
  const q = query.trim().toLowerCase()
  const hit = (c: Correction) => !q || [c.host, c.label, correctionValue(c)].some((t) => t.toLowerCase().includes(q))
  const groups = new Map<string, Correction[]>()
  for (const c of list.filter(hit)) groups.set(c.host, [...(groups.get(c.host) ?? []), c])
  return [...groups]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([host, items]) => ({ host, items: items.sort((a, b) => b.updated_at.localeCompare(a.updated_at)) }))
}

export function correctionValue(c: Pick<Correction, "value" | "wrong_field">): string {
  if (c.wrong_field) return "Wrong field: Blesser leaves it alone"
  if (c.value === null || c.value === "" || (Array.isArray(c.value) && !c.value.length)) return "Leave empty"
  return Array.isArray(c.value) ? c.value.join(", ") : c.value
}
