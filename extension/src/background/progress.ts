import type { ExportField, FormExport, FormProgress, ProgressField } from "../shared/types"
import { blockedReason, cleanDescriptor, type FrameResult, type TabInfo } from "./fill"
import type { Store } from "./store"

export interface FormScripting {
  track(tabId: number): Promise<FrameResult<ProgressField[]>[]>
  snapshot(tabId: number): Promise<FrameResult<ExportField[]>[]>
}

const MAX_FIELDS = 300
const cut = (text: unknown, max: number) => (typeof text === "string" ? text.slice(0, max) : "")

/** Content scripts run inside web pages, so their reports are checked before they are stored. */
export function cleanProgress(fields: unknown): ProgressField[] {
  if (!Array.isArray(fields)) return []
  return fields.slice(0, MAX_FIELDS).flatMap((raw): ProgressField[] => {
    if (!raw || typeof raw !== "object") return []
    const f = raw as Record<string, unknown>
    if (typeof f.key !== "string" || typeof f.label !== "string") return []
    return [{ key: cut(f.key, 50), label: cut(f.label, 300), section: cut(f.section, 200), required: f.required === true, filled: f.filled === true }]
  })
}

/** Starts the live count in every frame of the tab and stores the first reading. */
export async function startProgress(scripting: FormScripting, store: Store, tab: TabInfo): Promise<FormProgress> {
  const blocked = blockedReason(tab.url)
  if (blocked) throw new Error(blocked)
  const frames: Record<string, ProgressField[]> = {}
  for (const { frameId, result } of await scripting.track(tab.id)) frames[String(frameId)] = cleanProgress(result)
  const progress: FormProgress = { tabId: tab.id, url: tab.url, frames }
  await store.saveProgress(progress)
  return progress
}

const cleanValue = (value: unknown): ExportField["value"] =>
  typeof value === "string" ? value.slice(0, 20_000) : Array.isArray(value) ? value.filter((v): v is string => typeof v === "string").map((v) => v.slice(0, 500)) : null

/** The form as it stands, across frames, for the Word export. Stays on this device. */
export async function exportForm(scripting: FormScripting, tab: TabInfo): Promise<FormExport> {
  const blocked = blockedReason(tab.url)
  if (blocked) throw new Error(blocked)
  const fields: ExportField[] = []
  for (const { frameId, result } of await scripting.snapshot(tab.id)) {
    for (const field of result ?? []) {
      if (fields.length >= MAX_FIELDS) break
      fields.push({ ...cleanDescriptor({ ...field, key: `${frameId}:${field.key}` }), value: cleanValue(field.value) })
    }
  }
  if (!fields.length) throw new Error("No form fields found on this page.")
  return { title: tab.title.slice(0, 500), url: tab.url, fields }
}
