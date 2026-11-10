import type { Corrected, FieldDescriptor, FillFeedback, Review, ReviewRow } from "./types"

type Value = string | string[] | null

export interface Groups {
  filled: ReviewRow[]
  drafted: ReviewRow[]
  needs: ReviewRow[]
}

export function groupRows(rows: ReviewRow[]): Groups {
  const out: Groups = { filled: [], drafted: [], needs: [] }
  for (const row of rows) out[row.status].push(row)
  return out
}

const isEmpty = (value: Value) => value === null || value === "" || (Array.isArray(value) && value.length === 0)

export function sameValue(a: Value, b: Value): boolean {
  if (isEmpty(a) && isEmpty(b)) return true
  const list = (v: Value) => (Array.isArray(v) ? v : v === null ? [] : [v]).map((s) => s.trim().toLowerCase()).sort()
  const [x, y] = [list(a), list(b)]
  return x.length === y.length && x.every((s, i) => s === y[i])
}

function optionLabel(field: FieldDescriptor, value: string): string {
  return field.options.find((o) => o.value === value)?.label || value
}

/** The value as the member reads it: option labels, not option codes. */
export function displayValue(row: Pick<ReviewRow, "value" | "field" | "document">): string {
  if (row.document) return row.document
  if (row.value === null) return ""
  const list = Array.isArray(row.value) ? row.value : [row.value]
  return list.map((v) => optionLabel(row.field, v)).join(", ")
}

const RECORDS: Record<string, string> = {
  profile: "your profile",
  education: "your education",
  experience: "your experience",
  reference: "your referee",
  references: "your referee",
  project: "your project",
}

const INFERRED: Record<string, string> = { address_parts: "address", experience: "current job", education: "education" }

const words = (path: string) => path.replace(/[._]+/g, " ").trim()

function noteDetail(note: string): string {
  const match = /^From [^:]+:\s*(.+)$/.exec(note)
  return match ? words(match[1]) : ""
}

/** Source and rule in plain words, e.g. "From your nationality". */
export function describeSource(row: Pick<ReviewRow, "source" | "rule" | "note" | "value" | "field" | "document" | "status">): string {
  const rule = row.rule ?? ""
  const shown = displayValue(row)
  if (row.source === "member") return "Your change, remembered for this site"
  if (rule === "correction") return "Your earlier correction"
  if (rule === "model:choice") return "Chosen by Blesser, review"
  if (rule.startsWith("inferred:")) return `From your ${INFERRED[rule.slice("inferred:".length)] ?? words(rule.slice("inferred:".length))}`
  if (rule.startsWith("concept:")) {
    if (/^Matched\b/.test(row.note)) return row.note
    const topic = noteDetail(row.note) || words(rule.slice("concept:".length))
    return shown ? `Matched your ${topic} to '${shown}'` : `Matched your ${topic}`
  }
  if (rule.startsWith("qualifier:")) {
    const [record, ...rest] = rule.slice("qualifier:".length).split(".")
    if (!rest.length) return row.source === "project" ? `From your project: ${words(record)}` : `From your ${words(record)}`
    return `From ${RECORDS[record] ?? `your ${words(record)}`}: ${words(rest.join("."))}`
  }
  switch (row.source) {
    case "drafted":
      return "Drafted by Blesser, review"
    case "answer":
      return "From your saved answers"
    case "document":
      return row.note ? `Your ${row.note.replace(/^Default /, "default ").toLowerCase().replace(/\bcv\b/, "CV")}` : "From your documents"
    case "project": {
      const detail = noteDetail(row.note)
      return detail ? `From your project: ${detail}` : "From your project"
    }
    case "profile": {
      const detail = noteDetail(row.note)
      return detail ? `From your ${detail}` : "From your profile"
    }
    default:
      return row.note
  }
}

function patch(review: Review, key: string, change: (row: ReviewRow) => ReviewRow): Review {
  return { ...review, rows: review.rows.map((row) => (row.key === key ? change(row) : row)) }
}

export function applyEdit(review: Review, key: string, value: Value): Review {
  return patch(review, key, (row) =>
    isEmpty(value)
      ? { ...row, status: "needs", value: null, document: null, pageEdit: null, reason: "You cleared it" }
      : { ...row, status: "filled", value, document: null, source: "member", rule: "correction", confidence: "high", reason: "", pageEdit: null },
  )
}

export function applyClear(review: Review, key: string): Review {
  return patch(review, key, (row) => ({ ...row, status: "needs", value: null, document: null, pageEdit: null, reason: "You cleared it" }))
}

export function applyWrongField(review: Review, key: string): Review {
  return patch(review, key, (row) => ({
    ...row,
    status: "needs",
    value: null,
    document: null,
    pageEdit: null,
    reason: "Marked as the wrong field. Blesser won't fill it on this site again.",
  }))
}

const YES = new Set(["yes", "true", "on", "1", "checked"])

function shownList(row: Pick<ReviewRow, "value" | "field">): Value {
  if (row.field.type === "checkbox" && row.field.options.length <= 1 && typeof row.value === "string")
    return YES.has(row.value.trim().toLowerCase()) || row.value === row.field.options[0]?.value ? "Yes" : "No"
  if (row.value === null) return null
  return Array.isArray(row.value) ? row.value.map((v) => optionLabel(row.field, v)) : optionLabel(row.field, row.value)
}

/** Records a change the member typed on the page; ignored when it matches what the panel already shows. */
export function notePageEdit(review: Review, key: string, value: Value): Review {
  return patch(review, key, (row) => {
    if (!row.filled || row.document || sameValue(row.value, value) || sameValue(shownList(row), value)) return { ...row, pageEdit: null }
    return { ...row, pageEdit: { value } }
  })
}

export function dismissPageEdit(review: Review, key: string): Review {
  return patch(review, key, (row) => ({ ...row, value: row.pageEdit ? row.pageEdit.value : row.value, pageEdit: null }))
}

export function markMoved(review: Review, moved: NonNullable<Review["moved"]>): Review {
  if (review.moved === "navigated") return review
  return { ...review, moved }
}

export function feedbackFor(review: Pick<Review, "url" | "host">, row: ReviewRow, corrected: Corrected): FillFeedback {
  return {
    page: { url: review.url, host: review.host },
    field: row.field,
    filled: row.filled ?? { value: null, source: "unfilled", rule: null },
    corrected,
  }
}

export const counts = (review: Review) => {
  const groups = groupRows(review.rows)
  return { filled: groups.filled.length, drafted: groups.drafted.length, needs: groups.needs.length }
}
