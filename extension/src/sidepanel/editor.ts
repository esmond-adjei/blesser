import type { FieldDescriptor, ReviewRow } from "../shared/types"

export type EditorKind = "select" | "multi" | "yesno" | "textarea" | "input"

const INPUT_TYPES = new Set(["date", "month", "number", "email", "tel", "url", "time"])

export function editorFor(field: FieldDescriptor): { kind: EditorKind; inputType: string } {
  const single = field.type === "checkbox" && field.options.length <= 1
  if (single) return { kind: "yesno", inputType: "" }
  if (field.type === "select-multiple" || (field.type === "checkbox" && field.options.length > 1)) return { kind: "multi", inputType: "" }
  if (field.options.length && (field.tag === "select" || field.type === "radio")) return { kind: "select", inputType: "" }
  if (field.tag === "textarea" || field.tag === "contenteditable") return { kind: "textarea", inputType: "" }
  return { kind: "input", inputType: INPUT_TYPES.has(field.type) ? field.type : "text" }
}

export const canEdit = (field: FieldDescriptor) => field.type !== "file"

const norm = (s: string) => s.trim().toLowerCase()

function optionValue(field: FieldDescriptor, wanted: string): string {
  const hit = field.options.find((o) => o.value === wanted) ?? field.options.find((o) => norm(o.label) === norm(wanted) || norm(o.value) === norm(wanted))
  return hit?.value ?? ""
}

/** The editor's starting value: option values for choices, plain text otherwise. */
export function initialDraft(row: Pick<ReviewRow, "field" | "value">): string | string[] {
  const { kind } = editorFor(row.field)
  const list = row.value === null ? [] : Array.isArray(row.value) ? row.value : [row.value]
  if (kind === "multi") return list.map((v) => optionValue(row.field, v)).filter(Boolean)
  if (kind === "select") return list.length ? optionValue(row.field, list[0]) : ""
  if (kind === "yesno") {
    if (!list.length) return ""
    return /^(yes|true|on|1|checked)$/i.test(list[0].trim()) || list[0] === row.field.options[0]?.value ? "Yes" : "No"
  }
  return list.join(", ")
}
