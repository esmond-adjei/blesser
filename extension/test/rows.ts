import type { FieldDescriptor, Review, ReviewRow } from "../src/shared/types"

export const descriptor = (key: string, label: string, extra: Partial<FieldDescriptor> = {}): FieldDescriptor => ({
  key, tag: "input", type: "text", name: "", id: "", autocomplete: "", label, placeholder: "", help_text: "", section: "",
  options: [], required: false, max_length: null, word_limit: null, accept: "", ...extra,
})

export function row(key: string, label: string, extra: Partial<ReviewRow> = {}): ReviewRow {
  const value = extra.value ?? "Ama"
  return {
    key, label, field: descriptor(key, label), status: "filled", value, document: null, source: "profile", rule: null, confidence: "high",
    note: "", reason: "", filled: { value, source: extra.source ?? "profile", rule: extra.rule ?? null }, pageEdit: null, ...extra,
  }
}

export const review = (rows: ReviewRow[]): Review => ({
  tabId: 4, url: "https://apply.example.org/form?step=1", host: "apply.example.org", title: "Apply", at: "2026-11-10T09:00:00Z",
  rows, matchedOpportunityId: null, applied: false, remainingToday: 10, moved: null,
})
