import type { AttachedFile, CollectedField, FieldDescriptor, FillInstruction, FillOutcome, FillSummary, NeedsYou, Prefs } from "../shared/types"
import type { Api } from "./api"

export interface FrameResult<T> {
  frameId: number
  result: T
}

export interface Scripting {
  collect(tabId: number): Promise<FrameResult<CollectedField[]>[]>
  fill(tabId: number, frameId: number, instructions: FillInstruction[]): Promise<FillOutcome[]>
}

export interface TabInfo {
  id: number
  url: string
  title: string
}

const MAX_FIELDS = 300
const cut = (text: string, max: number) => (text.length > max ? text.slice(0, max) : text)

export function blockedReason(url: string): string | null {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return "Blesser can't fill this page."
  }
  if (!["http:", "https:", "file:"].includes(parsed.protocol)) return "Blesser can't fill browser pages. Open an application form first."
  if (/^(chrome\.google\.com|chromewebstore\.google\.com|microsoftedge\.microsoft\.com)$/.test(parsed.hostname))
    return "Browsers don't let extensions fill store pages."
  return null
}

const split = (key: string) => {
  const at = key.indexOf(":")
  return { frameId: Number(key.slice(0, at)), local: key.slice(at + 1) }
}

function toDescriptor(field: CollectedField, frameId: number): FieldDescriptor {
  return {
    key: `${frameId}:${field.key}`,
    tag: field.tag,
    type: cut(field.type, 50),
    name: cut(field.name, 500),
    id: cut(field.id, 500),
    autocomplete: cut(field.autocomplete, 500),
    label: cut(field.label, 4000),
    placeholder: cut(field.placeholder, 500),
    help_text: cut(field.help_text, 4000),
    section: cut(field.section, 500),
    options: field.options.slice(0, 500).map((o) => ({ value: cut(o.value, 500), label: cut(o.label, 500) })),
    required: field.required,
    max_length: field.max_length,
    word_limit: field.word_limit,
    accept: cut(field.accept, 500),
  }
}

/** Collect in every frame, ask the API, download documents, then fill frame by frame. */
export async function runFill(api: Api, scripting: Scripting, tab: TabInfo, prefs: Prefs): Promise<FillSummary> {
  const blocked = blockedReason(tab.url)
  if (blocked) throw new Error(blocked)
  const frames = await scripting.collect(tab.id)
  const collected = new Map<string, CollectedField>()
  const fields: FieldDescriptor[] = []
  for (const { frameId, result } of frames) {
    for (const field of result ?? []) {
      if (fields.length >= MAX_FIELDS) break
      const descriptor = toDescriptor(field, frameId)
      collected.set(descriptor.key, field)
      fields.push(descriptor)
    }
  }
  if (!fields.length) throw new Error("No form fields found on this page.")

  const url = new URL(tab.url)
  const response = await api.fill({
    page: { url: tab.url, title: cut(tab.title, 500), host: url.host },
    use: { profile: true, project_id: prefs.fillAs === "me" ? null : prefs.fillAs },
    allow_drafting: prefs.allowDrafting,
    fields,
  })

  const files = new Map<string, AttachedFile | null>()
  for (const fill of response.fills) {
    if (!fill.document_id || files.has(fill.document_id)) continue
    files.set(fill.document_id, await api.download(fill.document_id).catch(() => null))
  }

  const byFrame = new Map<number, FillInstruction[]>()
  for (const fill of response.fills) {
    if (!collected.has(fill.key)) continue
    const { frameId, local } = split(fill.key)
    const list = byFrame.get(frameId) ?? []
    list.push({ key: local, value: fill.value, drafted: fill.source === "drafted", file: fill.document_id ? (files.get(fill.document_id) ?? null) : null })
    byFrame.set(frameId, list)
  }
  const outcomes = new Map<string, FillOutcome>()
  for (const [frameId, instructions] of byFrame) {
    const results = await scripting.fill(tab.id, frameId, instructions).catch(() =>
      instructions.map((i): FillOutcome => ({ key: i.key, status: "skipped", reason: "The page changed before Blesser could fill it" })),
    )
    for (const outcome of results) outcomes.set(`${frameId}:${outcome.key}`, outcome)
  }

  const reasons = new Map(response.unfilled.map((u) => [u.key, u.reason]))
  const needsYou: NeedsYou[] = []
  let filled = 0
  let drafted = 0
  for (const field of fields) {
    const outcome = outcomes.get(field.key)
    if (outcome?.status === "filled") filled++
    else if (outcome?.status === "drafted") drafted++
    const reason = outcome?.status === "skipped" ? outcome.reason : reasons.get(field.key)
    if (outcome?.status === "skipped" && outcome.reason === "Already has your answer") continue
    if (reason || (!outcome && field.required)) {
      const label = field.label || field.placeholder || field.name || "Unlabelled field"
      needsYou.push({ key: field.key, label: cut(label, 120), reason: reason || "Required, and nothing in your kit fits" })
    }
  }

  return {
    tabId: tab.id,
    url: tab.url,
    at: new Date().toISOString(),
    filled,
    drafted,
    needsYou,
    matchedOpportunityId: response.matched_opportunity_id,
    applied: false,
    remainingToday: response.usage.remaining_today,
  }
}
