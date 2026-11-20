import type { AttachedFile, CollectedField, FieldDescriptor, FillInstruction, FillOutcome, Prefs, Review, ReviewRow, WriteResult } from "../shared/types"
import type { Api } from "./api"

export interface FrameResult<T> {
  frameId: number
  result: T
}

export interface Scripting {
  collect(tabId: number): Promise<FrameResult<CollectedField[]>[]>
  fill(tabId: number, frameId: number, instructions: FillInstruction[]): Promise<FillOutcome[]>
  write(tabId: number, frameId: number, key: string, value: string | string[] | null): Promise<WriteResult>
}

export interface TabInfo {
  id: number
  url: string
  title: string
}

const MAX_FIELDS = 300
const cut = (text: string, max: number) => (text.length > max ? text.slice(0, max) : text)

export const NO_ACCESS =
  "Chrome hasn't let Blesser into this page yet. Press the Blesser icon in the toolbar or Alt+Shift+F on the page, or right-click the form and choose Fill with Blesser."

export function blockedReason(url: string): string | null {
  // Chrome hides the address of tabs the extension hasn't been granted.
  if (!url) return NO_ACCESS
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

export const split = (key: string) => {
  const at = key.indexOf(":")
  return { frameId: Number(key.slice(0, at)), local: key.slice(at + 1) }
}

/** Only the descriptor keys, trimmed; anything else a caller attached (values included) is dropped. */
export function cleanDescriptor(field: FieldDescriptor): FieldDescriptor {
  return {
    key: cut(field.key, 50),
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

export const toDescriptor = (field: CollectedField, frameId: number): FieldDescriptor => cleanDescriptor({ ...field, key: `${frameId}:${field.key}` })

export async function collectPage(scripting: Scripting, tab: TabInfo) {
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
  return { collected, fields }
}

const labelOf = (field: FieldDescriptor) => cut(field.label || field.placeholder || field.name || "Unlabelled field", 160)

/** Collect in every frame, ask the API, download documents, then fill frame by frame. */
export async function runFill(api: Api, scripting: Scripting, tab: TabInfo, prefs: Prefs): Promise<Review> {
  const { collected, fields } = await collectPage(scripting, tab)
  if (!fields.length) throw new Error("No form fields found on this page.")

  const response = await api.fill({
    page: { url: tab.url, title: cut(tab.title, 500), host: new URL(tab.url).host },
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
  const fills = new Map(response.fills.map((f) => [f.key, f]))
  const docNames = new Map([...files].map(([id, file]) => [id, file?.name ?? null]))
  const rows: ReviewRow[] = []
  for (const field of fields) {
    const outcome = outcomes.get(field.key)
    const fill = fills.get(field.key)
    if (outcome?.status === "skipped" && outcome.reason === "Already has your answer") continue
    const reason = outcome?.status === "skipped" ? outcome.reason : reasons.get(field.key)
    const done = outcome?.status === "filled" || outcome?.status === "drafted"
    if (!done && !reason && !field.required) continue
    rows.push({
      key: field.key,
      label: labelOf(field),
      field,
      status: done ? (outcome.status as "filled" | "drafted") : "needs",
      value: done ? (fill?.value ?? null) : null,
      document: done && fill?.document_id ? (docNames.get(fill.document_id) ?? null) : null,
      source: fill?.source ?? null,
      rule: fill?.rule ?? null,
      confidence: fill?.confidence ?? null,
      note: fill?.note ?? "",
      reason: done ? "" : reason || "Required, and nothing in your kit fits",
      filled: done && fill ? { value: fill.value, source: fill.source, rule: fill.rule ?? null } : null,
      pageEdit: null,
    })
  }

  const url = new URL(tab.url)
  return {
    tabId: tab.id,
    url: tab.url,
    host: url.hostname,
    title: cut(tab.title, 500),
    at: new Date().toISOString(),
    rows,
    matchedOpportunityId: response.matched_opportunity_id,
    matchedApplicationId: response.matched_application_id ?? null,
    applied: false,
    remainingToday: response.usage.remaining_today,
    moved: null,
  }
}
