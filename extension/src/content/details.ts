import type { PageDetails } from "../shared/types"
import { squash } from "./text"

const MONTHS: Record<string, number> = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4, may: 5, jun: 6, june: 6,
  jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
}
const MONTH = "(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
const DAY = "(\\d{1,2})(?:st|nd|rd|th)?"
const DATE_PATTERNS: { re: RegExp; parts: (m: RegExpExecArray) => [number, number, number] | null }[] = [
  { re: /\b(\d{4})-(\d{2})-(\d{2})\b/, parts: (m) => [+m[1], +m[2], +m[3]] },
  { re: new RegExp(`\\b${DAY}\\s+(?:of\\s+)?${MONTH}\\.?,?\\s+(\\d{4})\\b`, "i"), parts: (m) => [+m[3], MONTHS[m[2].toLowerCase()], +m[1]] },
  { re: new RegExp(`\\b${MONTH}\\.?\\s+${DAY},?\\s+(\\d{4})\\b`, "i"), parts: (m) => [+m[3], MONTHS[m[1].toLowerCase()], +m[2]] },
  {
    re: /\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b/,
    // Only when the order is certain: 30/11/2026, never 03/04/2026.
    parts: (m) => (+m[1] > 12 && +m[2] <= 12 ? [+m[3], +m[2], +m[1]] : +m[2] > 12 && +m[1] <= 12 ? [+m[3], +m[1], +m[2]] : null),
  },
]
const DEADLINE_WORDS = /\b(?:deadline|closing date|closes|close on|closed on|due date|due by|apply by|submit by|submission date|applications? close|applications? due|last day)\b/i
const ROLLING = /\b(?:rolling basis|rolling deadline|rolling admissions?|applications are reviewed on a rolling)\b/i
const BUILDER_SUFFIX = /\s*[-|:]\s*(?:google forms?|microsoft forms?|typeform|jotform|airtable|tally|submittable|surveymonkey)\s*$/i
const GENERIC_TITLE = /^(?:application(?: form)?|apply(?: now)?|form|untitled form|sign in|home)$/i

function isoDate(y: number, m: number, d: number): string | null {
  const date = new Date(Date.UTC(y, m - 1, d))
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return null
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`
}

/** The first date in the text, with the words it was written in. */
export function findDate(text: string): { text: string; date: string } | null {
  let best: { index: number; text: string; date: string } | null = null
  for (const { re, parts } of DATE_PATTERNS) {
    const m = re.exec(text)
    const p = m && parts(m)
    const date = p && isoDate(...p)
    if (m && date && (!best || m.index < best.index)) best = { index: m.index, text: m[0], date }
  }
  return best && { text: best.text, date: best.date }
}

/** Visible text in reading order, one entry per block, skipping scripts and form controls. */
function blocks(doc: Document): string[] {
  const out: string[] = []
  const walker = doc.createTreeWalker(doc.body ?? doc.documentElement, 4 /* SHOW_TEXT */)
  let current = ""
  let parent: Element | null = null
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement
    if (!el || el.closest("script, style, noscript, template, select, option, textarea, [hidden], [aria-hidden='true']")) continue
    const block = el.closest("p, li, td, th, dd, dt, h1, h2, h3, h4, h5, h6, div, section, label, legend") ?? el
    if (block !== parent && current) {
      out.push(squash(current))
      current = ""
    }
    parent = block
    current += ` ${node.nodeValue ?? ""}`
  }
  if (current.trim()) out.push(squash(current))
  return out.filter(Boolean)
}

/** A deadline stated near a deadline word: the same block, or the block right after a "Deadline" label. */
export function findDeadline(doc: Document): PageDetails["deadline"] {
  const texts = blocks(doc)
  for (let i = 0; i < texts.length; i++) {
    const words = DEADLINE_WORDS.exec(texts[i])
    if (!words) continue
    const after = texts[i].slice(words.index)
    const found = findDate(after.slice(0, 160)) ?? (after.length < 40 && texts[i + 1] ? findDate(texts[i + 1].slice(0, 80)) : null)
    if (found) return { text: found.text, date: found.date, rolling: false }
  }
  const all = texts.join(" ")
  if (ROLLING.test(all)) return { text: "Rolling", date: null, rolling: true }
  return null
}

const meta = (doc: Document, selector: string) => squash(doc.querySelector<HTMLMetaElement>(selector)?.content ?? "")

const APPLICATION_SUFFIX = /\s*[-:|]\s*(?:online\s+)?(?:application(?:\s+form)?|apply(?:\s+now)?)\s*$/i

/** "Grant X | Funder", "Grant X: application" and "Grant X - Google Forms" all become "Grant X". */
export function cleanTitle(text: string): string {
  let out = squash(text).replace(BUILDER_SUFFIX, "").replace(APPLICATION_SUFFIX, "")
  const [first] = out.split(/\s+\|\s+/)
  if (first.length >= 8) out = first
  return out.trim()
}

export function findTitle(doc: Document): string {
  const h1 = Array.from(doc.querySelectorAll("h1, [role='heading'][aria-level='1']"))
    .map((h) => cleanTitle(h.textContent ?? ""))
    .find((t) => t.length >= 4 && t.length <= 160 && !GENERIC_TITLE.test(t))
  const candidates = [h1, cleanTitle(meta(doc, 'meta[property="og:title"]')), cleanTitle(doc.title)]
  return (candidates.find((t) => t && !GENERIC_TITLE.test(t)) ?? "").slice(0, 300)
}

export function findOrganization(doc: Document): string {
  return (meta(doc, 'meta[property="og:site_name"]') || meta(doc, 'meta[name="application-name"]') || meta(doc, 'meta[name="author"]')).slice(0, 200)
}

/** What the page says about the opportunity, for saving it to the member's applications. */
export function pageDetails(doc: Document): PageDetails {
  return { title: findTitle(doc), organization: findOrganization(doc), deadline: findDeadline(doc) }
}
