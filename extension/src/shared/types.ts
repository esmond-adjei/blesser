export type FieldTag = "input" | "textarea" | "select" | "contenteditable"

export interface FieldOption {
  value: string
  label: string
}

export interface FieldDescriptor {
  key: string
  tag: FieldTag
  type: string
  name: string
  id: string
  autocomplete: string
  label: string
  placeholder: string
  help_text: string
  section: string
  options: FieldOption[]
  required: boolean
  max_length: number | null
  word_limit: number | null
  accept: string
}

/** A field as the content script sees it; `custom` marks ARIA widgets it reports but never operates. */
export interface CollectedField extends FieldDescriptor {
  custom: boolean
}

export interface FillRequest {
  page: { url: string; title: string; host: string }
  use: { profile: boolean; project_id: string | null }
  allow_drafting: boolean
  fields: FieldDescriptor[]
}

export type FillSource = "profile" | "project" | "answer" | "document" | "drafted"

export interface Fill {
  key: string
  value: string | string[] | null
  document_id: string | null
  source: FillSource
  confidence: "high" | "medium" | "low"
  note: string
}

export interface FillResponse {
  fills: Fill[]
  unfilled: { key: string; reason: string }[]
  matched_opportunity_id: string | null
  usage: { drafted_fields: number; remaining_today: number }
}

export interface AttachedFile {
  name: string
  type: string
  base64: string
}

export interface FillInstruction {
  key: string
  value: string | string[] | null
  drafted: boolean
  file: AttachedFile | null
}

export type FillStatus = "filled" | "drafted" | "skipped"

export interface FillOutcome {
  key: string
  status: FillStatus
  reason: string
}

export interface ExtensionSession {
  id: string
  name: string
  created_at: string
  last_used_at: string | null
}

export interface ExtensionMe {
  user: { id: string; email: string; display_name: string | null }
  projects: { id: string; name: string; tagline: string }[]
  drafting: { enabled: boolean; remaining_today: number }
}

export interface ConnectPayload {
  type: "blesser.connect"
  state: string
  access_token: string
  refresh_token: string
  session: ExtensionSession
}

export interface NeedsYou {
  key: string
  label: string
  reason: string
}

export interface FillSummary {
  tabId: number
  url: string
  at: string
  filled: number
  drafted: number
  needsYou: NeedsYou[]
  matchedOpportunityId: string | null
  applied: boolean
  remainingToday: number | null
}

export interface Settings {
  apiUrl: string
  appUrl: string
}

export interface Prefs {
  fillAs: string
  allowDrafting: boolean
}

export interface Status {
  settings: Settings
  prefs: Prefs
  connected: boolean
  me: ExtensionMe | null
  error: string | null
}

export type PopupMessage =
  | { type: "status" }
  | { type: "connect" }
  | { type: "disconnect" }
  | { type: "prefs"; prefs: Prefs }
  | { type: "fill"; tabId: number }
  | { type: "lastResult"; tabId: number }
  | { type: "focus"; tabId: number; key: string }
  | { type: "markApplied"; tabId: number }
  | { type: "settings"; settings: Settings }

export type Reply<T> = { ok: true; data: T } | { ok: false; error: string }
