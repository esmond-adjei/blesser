import { formatDay } from "@blesser/ui"
import { LANGUAGE_LEVELS } from "./kit"
import type { Education, Experience, KitDocument, ProfileInput, Reference } from "./kitTypes"

/** Profile fields read from a CV. A key is missing when the CV didn't have it. */
export type CvProfile = Partial<Omit<ProfileInput, "sensitive">>

type Scalar = Exclude<
  keyof CvProfile,
  "other_links" | "education" | "experience" | "skills" | "languages" | "awards" | "publications" | "references"
>
type ListKey = "other_links" | "education" | "experience" | "languages" | "awards" | "publications" | "references"

export type Suggestion = {
  /** Stable id for the review checkbox: a field name, or "education:1" for one new entry. */
  id: string
  section: string
  label: string
  value: string
  /** What the profile holds now, when it differs. Unticked by default so nothing is overwritten unasked. */
  current?: string
}

const SCALARS: { key: Scalar; label: string; section: string }[] = [
  { key: "given_name", label: "Given name", section: "Identity" },
  { key: "family_name", label: "Family name", section: "Identity" },
  { key: "preferred_name", label: "Preferred name", section: "Identity" },
  { key: "pronouns", label: "Pronouns", section: "Identity" },
  { key: "date_of_birth", label: "Date of birth", section: "Identity" },
  { key: "gender", label: "Gender", section: "Identity" },
  { key: "nationality", label: "Nationality", section: "Identity" },
  { key: "country_of_birth", label: "Country of birth", section: "Identity" },
  { key: "place_of_birth", label: "Place of birth", section: "Identity" },
  { key: "country_of_residence", label: "Country of residence", section: "Identity" },
  { key: "city", label: "City", section: "Identity" },
  { key: "postal_code", label: "Postal code", section: "Identity" },
  { key: "address_line1", label: "Address line 1", section: "Identity" },
  { key: "address_line2", label: "Address line 2", section: "Identity" },
  { key: "email", label: "Email", section: "Contact" },
  { key: "phone", label: "Phone", section: "Contact" },
  { key: "linkedin_url", label: "LinkedIn", section: "Contact" },
  { key: "website_url", label: "Website", section: "Contact" },
  { key: "github_url", label: "GitHub", section: "Contact" },
  { key: "headline", label: "Headline", section: "About you" },
  { key: "short_bio", label: "Short bio", section: "About you" },
  { key: "long_bio", label: "Long bio", section: "About you" },
]

const fold = (value: string | null | undefined) => (value ?? "").toLowerCase().replace(/\s+/g, " ").trim()
const foldUrl = (value: string) => fold(value).replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/+$/, "")
const same = (key: string, a: string, b: string) => (key.endsWith("_url") ? foldUrl(a) === foldUrl(b) : fold(a) === fold(b))

const year = (iso: string | null) => (iso ? iso.slice(0, 4) : "")
const months = (start: string | null, end: string | null, current = false) => {
  const to = current ? "present" : year(end)
  return year(start) || to ? [year(start), to].filter(Boolean).join(" to ") : ""
}
const join = (...parts: (string | null | undefined)[]) => parts.map((p) => (p ?? "").trim()).filter(Boolean).join(", ")

type ListSpec<T> = {
  section: string
  noun: string
  /** Two entries are the same thing when these match, so a CV never adds a duplicate. */
  key: (item: T) => string
  show: (item: T) => string
}

const LISTS: { [K in ListKey]: ListSpec<NonNullable<CvProfile[K]>[number]> } = {
  other_links: { section: "Contact", noun: "Link", key: (l) => foldUrl(l.url), show: (l) => join(l.label, l.url) },
  education: {
    section: "Education",
    noun: "Education",
    key: (e: Education) => `${fold(e.institution)}|${fold(e.qualification)}`,
    show: (e: Education) => join([e.qualification, e.field].filter(Boolean).join(" in "), e.institution, months(e.start, e.end)),
  },
  experience: {
    section: "Experience",
    noun: "Experience",
    key: (e: Experience) => `${fold(e.organization)}|${fold(e.role)}`,
    show: (e: Experience) => join(e.role, e.organization, months(e.start, e.end, e.current)),
  },
  languages: {
    section: "Skills and languages",
    noun: "Language",
    key: (l) => fold(l.language),
    show: (l) => join(l.language, LANGUAGE_LEVELS.find((x) => x.value === l.level)?.label),
  },
  awards: { section: "Awards and publications", noun: "Award", key: (a) => fold(a.title), show: (a) => join(a.title, a.issuer, a.year ? String(a.year) : "") },
  publications: { section: "Awards and publications", noun: "Publication", key: (a) => fold(a.title), show: (a) => join(a.title, a.venue, a.year ? String(a.year) : "") },
  references: {
    section: "References",
    noun: "Reference",
    key: (r: Reference) => fold(r.name),
    show: (r: Reference) => join(r.name, r.title, r.organization),
  },
}

const LIST_KEYS = Object.keys(LISTS) as ListKey[]

const display = (key: Scalar, value: string) => (key === "date_of_birth" && value ? formatDay(value, new Date(3000, 0, 1)) : value)

/** New entries from the CV that the profile doesn't already have, in CV order. */
function newItems<K extends ListKey>(key: K, current: ProfileInput, found: CvProfile) {
  const spec = LISTS[key] as ListSpec<unknown>
  const seen = new Set((current[key] as unknown[]).map(spec.key))
  const out: { index: number; item: unknown }[] = []
  ;((found[key] ?? []) as unknown[]).forEach((item, index) => {
    const id = spec.key(item)
    if (id.replace(/\|/g, "") && seen.has(id)) return
    seen.add(id)
    out.push({ index, item })
  })
  return out
}

const newSkills = (current: ProfileInput, found: CvProfile) => {
  const have = new Set(current.skills.map(fold))
  return (found.skills ?? []).filter((s) => {
    const k = fold(s)
    if (!k || have.has(k)) return false
    have.add(k)
    return true
  })
}

/** What the CV would change, field by field. Values the profile already holds are left out. */
export function cvSuggestions(current: ProfileInput, found: CvProfile): Suggestion[] {
  const out: Suggestion[] = []
  for (const { key, label, section } of SCALARS) {
    const value = (found[key] ?? "") as string
    if (!value.trim()) continue
    const now = (current[key] ?? "") as string
    if (same(key, value, now)) continue
    out.push({ id: key, section, label, value: display(key, value), ...(now.trim() ? { current: display(key, now) } : {}) })
  }
  const skills = newSkills(current, found)
  if (skills.length) out.push({ id: "skills", section: "Skills and languages", label: "Skills", value: skills.join(", ") })
  for (const key of LIST_KEYS) {
    const spec = LISTS[key] as ListSpec<unknown>
    for (const { index, item } of newItems(key, current, found)) {
      out.push({ id: `${key}:${index}`, section: spec.section, label: spec.noun, value: spec.show(item) })
    }
  }
  const order = ["Identity", "Contact", "About you", "Education", "Experience", "Skills and languages", "Awards and publications", "References"]
  return out.sort((a, b) => order.indexOf(a.section) - order.indexOf(b.section))
}

/** Ticked by default: empty fields and new entries. Replacing something the member typed is their call. */
export const defaultChoice = (list: Suggestion[]) => new Set(list.filter((s) => s.current === undefined).map((s) => s.id))

/** The profile with the chosen suggestions applied. New entries go after the ones already there. */
export function applyCv(current: ProfileInput, found: CvProfile, chosen: ReadonlySet<string>): ProfileInput {
  const next: ProfileInput = { ...current }
  const write = next as unknown as Record<string, unknown>
  for (const { key } of SCALARS) {
    const value = found[key]
    if (chosen.has(key) && typeof value === "string" && value.trim()) write[key] = value
  }
  if (chosen.has("skills")) next.skills = [...current.skills, ...newSkills(current, found)]
  for (const key of LIST_KEYS) {
    const add = newItems(key, current, found).filter(({ index }) => chosen.has(`${key}:${index}`))
    if (add.length) write[key] = [...(current[key] as unknown[]), ...add.map(({ item }) => item)]
  }
  return next
}

/** The toast after applying, for example "Added 6 details from your CV." */
export function filledMessage(count: number): string {
  return count === 1 ? "Added 1 detail from your CV." : `Added ${count} details from your CV.`
}

const READABLE = new Set(["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"])

/** Documents Blesser can read a CV from, CVs first, then the default, then newest. */
export function readableCvs(docs: KitDocument[]): KitDocument[] {
  return docs
    .filter((d) => READABLE.has(d.content_type))
    .sort((a, b) => Number(b.kind === "cv") - Number(a.kind === "cv") || Number(b.is_default) - Number(a.is_default) || b.created_at.localeCompare(a.created_at))
}
