import type { CollectedField, PageMessage } from "../shared/types"
import { collectFields, OVERLAY_ID, type Collected } from "./collect"
import { filledByBlesser, readValue } from "./fill"

export interface WatchOptions {
  /** Member edits only; Blesser's own writes dispatch untrusted events. Tests swap this out. */
  trusted?: (event: Event) => boolean
  editDelay?: number
  stepDelay?: number
  layout?: boolean
}

export interface Watcher {
  reset(): void
  stop(): void
}

const signature = (f: CollectedField) => (f.name || f.id ? [f.tag, f.type, f.name, f.id] : [f.tag, f.type, f.label]).join("|")

/** Reports member edits to fields Blesser filled, and new fields appearing (the next step of a form). */
export function watchPage(doc: Document, state: () => Collected | null, notify: (message: PageMessage) => void, options: WatchOptions = {}): Watcher {
  const view = doc.defaultView!
  const trusted = options.trusted ?? ((event: Event) => event.isTrusted)
  const editDelay = options.editDelay ?? 600
  const stepDelay = options.stepDelay ?? 700
  const timers = new Map<string, number>()
  let known = new Set((state()?.fields ?? []).map(signature))
  let stepTimer = 0

  const keyOf = (target: EventTarget | null): string | null => {
    const el = target as Element | null
    const current = state()
    if (!el || el.nodeType !== 1 || !current) return null
    for (const [key, controls] of current.controls) if (controls.some((c) => c === el || c.contains(el))) return key
    return null
  }

  const onEdit = (event: Event) => {
    if (!trusted(event)) return
    const key = keyOf(event.target)
    const current = state()
    if (key === null || !current) return
    const controls = current.controls.get(key) ?? []
    if (!controls.some(filledByBlesser)) return
    view.clearTimeout(timers.get(key))
    timers.set(
      key,
      view.setTimeout(() => {
        timers.delete(key)
        const field = current.fields.find((f) => f.key === key)
        if (field) notify({ type: "blesser.edited", key, value: readValue(controls, field) })
      }, editDelay),
    )
  }

  const check = () => {
    stepTimer = 0
    const fields = collectFields(doc, { layout: options.layout ?? true }).fields
    const added = fields.filter((f) => !known.has(signature(f))).length
    fields.forEach((f) => known.add(signature(f)))
    if (added) notify({ type: "blesser.step", added })
  }

  const observer = new view.MutationObserver((records) => {
    const overlay = doc.getElementById(OVERLAY_ID)
    if (overlay && records.every((r) => overlay.contains(r.target))) return
    view.clearTimeout(stepTimer)
    stepTimer = view.setTimeout(check, stepDelay)
  })

  doc.addEventListener("input", onEdit, true)
  doc.addEventListener("change", onEdit, true)
  observer.observe(doc.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "style", "class", "aria-hidden"] })

  return {
    reset() {
      known = new Set((state()?.fields ?? []).map(signature))
    },
    stop() {
      observer.disconnect()
      doc.removeEventListener("input", onEdit, true)
      doc.removeEventListener("change", onEdit, true)
      timers.forEach((t) => view.clearTimeout(t))
      view.clearTimeout(stepTimer)
    },
  }
}
