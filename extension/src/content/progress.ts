import type { CollectedField, ExportField, ProgressField } from "../shared/types"
import { collectFields, OVERLAY_ID, type Collected } from "./collect"
import { readValue } from "./fill"

type Value = string | string[] | null

const MAX_FIELDS = 300

/** A field counts as filled once it holds an answer; an unticked single checkbox holds none. */
export function isAnswered(field: CollectedField, value: Value): boolean {
  if (value === null) return false
  if (Array.isArray(value)) return value.length > 0
  if (field.type === "checkbox" && field.options.length <= 1) return value === "Yes"
  return value.trim() !== ""
}

const PROMPT = /^(?:choose|select|pick|please)\b/i

/** ARIA widgets hold their state in attributes rather than in a value. */
function customValue(controls: Element[], field: CollectedField): Value {
  if (field.type === "radio" || field.type === "checkbox") {
    const picked = controls.flatMap((c, i) => (c.getAttribute("aria-checked") === "true" ? [field.options[i]?.label || (c.textContent ?? "").trim()] : []))
    return field.type === "radio" ? (picked[0] ?? null) : picked
  }
  const first = controls[0]
  if (!first) return null
  if (first.tagName === "INPUT") return (first as HTMLInputElement).value || null
  const selected = Array.from(first.querySelectorAll('[role="option"][aria-selected="true"]')).map((o) => (o.getAttribute("aria-label") ?? o.textContent ?? "").trim()).filter(Boolean)
  if (selected.length || first.getAttribute("role") === "listbox") return selected.filter((s) => !PROMPT.test(s))[0] ?? null
  const shown = (first.textContent ?? "").replace(/\s+/g, " ").trim()
  return shown && !PROMPT.test(shown) ? shown : null
}

function valueOf(collected: Collected, field: CollectedField): Value {
  const controls = collected.controls.get(field.key) ?? []
  return field.custom ? customValue(controls, field) : readValue(controls, field)
}

/** Fields in a frame with no heading of their own take the frame's name, so they don't merge into the page's unnamed group. */
export function frameSection(win: Window): string {
  if (win === win.top) return ""
  let title = ""
  try {
    title = win.frameElement?.getAttribute("title") ?? ""
  } catch {
    // Cross-origin parent: the frame element is out of reach.
  }
  return (title || win.document.title).replace(/\s+/g, " ").trim().slice(0, 200)
}

export function progressOf(collected: Collected, fallbackSection = ""): ProgressField[] {
  return collected.fields.slice(0, MAX_FIELDS).map((field) => ({
    key: field.key,
    label: field.label || field.placeholder || field.name || "Unlabelled field",
    section: field.section || fallbackSection,
    required: field.required,
    filled: isAnswered(field, valueOf(collected, field)),
  }))
}

/** Every field with its current answer; `custom` is dropped because the export has no use for it. */
export function exportOf(collected: Collected, fallbackSection = ""): ExportField[] {
  return collected.fields.slice(0, MAX_FIELDS).map((field) => {
    const value = valueOf(collected, field)
    const { custom: _custom, ...descriptor } = field
    return { ...descriptor, section: descriptor.section || fallbackSection, value: isAnswered(field, value) ? value : null }
  })
}

export interface ProgressOptions {
  delay?: number
  layout?: boolean
  fallbackSection?: string
}

export interface ProgressTracker {
  snapshot(): ProgressField[]
  stop(): void
}

/** Recounts filled fields after the member types or the form changes, and reports only real changes. */
export function trackProgress(doc: Document, notify: (fields: ProgressField[]) => void, options: ProgressOptions = {}): ProgressTracker {
  const view = doc.defaultView!
  const delay = options.delay ?? 300
  const layout = options.layout ?? true
  let timer = 0
  let last = ""

  const measure = () => {
    const fields = progressOf(collectFields(doc, { layout }), options.fallbackSection)
    last = JSON.stringify(fields)
    return fields
  }
  const check = () => {
    timer = 0
    const before = last
    const fields = measure()
    if (last !== before) notify(fields)
  }
  const schedule = () => {
    view.clearTimeout(timer)
    timer = view.setTimeout(check, delay)
  }
  const observer = new view.MutationObserver((records) => {
    const overlay = doc.getElementById(OVERLAY_ID)
    if (overlay && records.every((r) => overlay.contains(r.target))) return
    schedule()
  })

  doc.addEventListener("input", schedule, true)
  doc.addEventListener("change", schedule, true)
  observer.observe(doc.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "style", "aria-hidden", "aria-checked", "aria-selected"] })

  return {
    snapshot: measure,
    stop() {
      observer.disconnect()
      doc.removeEventListener("input", schedule, true)
      doc.removeEventListener("change", schedule, true)
      view.clearTimeout(timer)
    },
  }
}
