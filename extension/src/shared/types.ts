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
  rule?: string | null
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

export type RowStatus = "filled" | "drafted" | "needs"

export interface ReviewRow {
  key: string
  label: string
  field: FieldDescriptor
  status: RowStatus
  value: string | string[] | null
  document: string | null
  source: FillSource | "member" | null
  rule: string | null
  confidence: Fill["confidence"] | null
  note: string
  reason: string
  /** What Blesser first put there; feedback reports it. */
  filled: { value: string | string[] | null; source: string; rule: string | null } | null
  /** A change the member made on the page that hasn't been remembered or dismissed. */
  pageEdit: { value: string | string[] | null } | null
}

export interface Review {
  tabId: number
  url: string
  host: string
  title: string
  at: string
  rows: ReviewRow[]
  matchedOpportunityId: string | null
  applied: boolean
  remainingToday: number | null
  /** "navigated": the tab loaded another page; "step": new fields appeared on the same page. */
  moved: "navigated" | "step" | null
}

export interface TrackedApplication {
  title: string
  deadline: string
  deadline_date: string | null
}

export type Corrected = { value: string | string[] | null } | { wrong_field: true }

export interface FillFeedback {
  page: { url: string; host: string }
  field: FieldDescriptor
  filled: { value: string | string[] | null; source: string; rule: string | null }
  corrected: Corrected
}

export interface ProblemReport {
  page: { url: string; host: string; title: string }
  fields: FieldDescriptor[]
  note: string
}

export interface WriteResult {
  ok: boolean
  reason: string
  value: string | string[] | null
}

export type PageMessage =
  | { type: "blesser.edited"; key: string; value: string | string[] | null }
  | { type: "blesser.step"; added: number }

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

export type PanelMessage =
  | { type: "status" }
  | { type: "connect" }
  | { type: "disconnect" }
  | { type: "prefs"; prefs: Prefs }
  | { type: "fill"; tabId: number }
  | { type: "review"; tabId: number }
  | { type: "trackedApplication"; tabId: number }
  | { type: "focus"; tabId: number; key: string }
  | { type: "markApplied"; tabId: number }
  | { type: "edit"; tabId: number; key: string; value: string | string[] | null }
  | { type: "clear"; tabId: number; key: string }
  | { type: "wrongField"; tabId: number; key: string }
  | { type: "remember"; tabId: number; key: string }
  | { type: "dismissEdit"; tabId: number; key: string }
  | { type: "reportPreview"; tabId: number }
  | { type: "report"; tabId: number; report: ProblemReport }
  | { type: "settings"; settings: Settings }

export type Reply<T> = { ok: true; data: T } | { ok: false; error: string }
