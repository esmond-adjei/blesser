import { API_BASE, ApiError, getAccessToken, parseDetail, refreshAccessToken, request } from "./api"
import type { Opportunity } from "./types"

export interface ToolStep {
  kind?: "tool"
  tool: string
  label: string
  ok: boolean
  note: string
}

export interface Commentary {
  kind: "commentary"
  text: string
}

export interface Thought {
  kind: "thought"
  text: string
}

export type TraceEntry = ToolStep | Commentary | Thought

const TOOL_SUMMARY: Record<string, { done: string; tried: string }> = {
  search_catalog: { done: "searched the catalog", tried: "tried to search the catalog" },
  search_web: { done: "searched the web", tried: "tried to search the web" },
  get_opportunity: { done: "checked an opportunity", tried: "tried to check an opportunity" },
  list_applications: { done: "checked your applications", tried: "tried to check your applications" },
  list_todos: { done: "checked your to-dos", tried: "tried to check your to-dos" },
  read_apply_kit: { done: "read your Apply kit", tried: "tried to read your Apply kit" },
  list_scans: { done: "checked your scans", tried: "tried to check your scans" },
  get_scan: { done: "checked a scan", tried: "tried to check a scan" },
  list_sources: { done: "checked your sources", tried: "tried to check your sources" },
  ask_member: { done: "asked you a few questions", tried: "tried to ask you a few questions" },
}

/** A phrase for tools without their own: reads keep their label, changes say what happened. */
function fromStep(step: ToolStep) {
  if (step.label.endsWith(" skipped")) return "held off on a change"
  if (!step.ok) return "tried a step that didn't go through"
  if (/^(Checked|Searched|Asked) /.test(step.label)) {
    const phrase = step.label.replace(/, \d+ match(es)?$/, "")
    return phrase.charAt(0).toLowerCase() + phrase.slice(1)
  }
  return "made a change you approved"
}

export function isToolStep(entry: TraceEntry): entry is ToolStep {
  return entry.kind === undefined || entry.kind === "tool"
}

export function activitySummary(entries: TraceEntry[]): string {
  const phrases: string[] = entries.some((e) => e.kind === "thought") ? ["thought it through"] : []
  for (const entry of entries) {
    if (!isToolStep(entry)) continue
    const summary = TOOL_SUMMARY[entry.tool]
    const phrase = summary ? (entry.ok ? summary.done : summary.tried) : fromStep(entry)
    if (!phrases.includes(phrase)) phrases.push(phrase)
  }
  if (!phrases.length) return ""
  const [first, ...rest] = phrases
  const list = !rest.length
    ? first
    : rest.length === 1
      ? `${first} and ${rest[0]}`
      : `${phrases.slice(0, -1).join(", ")}, and ${phrases.at(-1)}`
  return list[0].toUpperCase() + list.slice(1)
}

type RecordKind =
  | "application" | "todo" | "project" | "document" | "answer" | "web" | "opportunity"
  | "scan" | "find" | "site" | "saved_search" | "profile" | "settings"

export interface AssistantSource {
  key: string
  id: string
  kind: RecordKind
  title: string
  detail: string
  url: string | null
  opportunity: Opportunity | null
  preview?: boolean
}

export interface ContextChip {
  key: string
  label: string
  detail?: string
}

/** What the member has open when they ask, so "this one" can be resolved. */
export interface UiContext {
  page: string
  opportunity_id?: string
  application_id?: string
  todo_id?: string
  project_id?: string
  answer_id?: string
  selection?: string
  chips: ContextChip[]
}

export interface AssistantMessage {
  id: string
  chips?: ContextChip[]
  role: "user" | "assistant"
  content: string
  trace: TraceEntry[]
  sources: AssistantSource[]
  cited_deadlines: boolean
  created_at: string
}

export interface Question {
  id: string
  prompt: string
  type: "single" | "multiple" | "text" | "date"
  options: string[]
  allow_other: boolean
  max_choices: number | null
  required: boolean
}

export type Answers = Record<string, string | string[]>

/** A change waiting for approval, or questions waiting for answers. */
export interface PendingCall {
  id: string
  type: "change" | "questions"
  tool: string
  summary: string
  trace: TraceEntry[]
  note: string
  action: string
  tone: "default" | "danger"
  questions: Question[]
}

export interface AssistantChat {
  id: string
  title: string
  created_at: string
  updated_at: string
  running: boolean
  pending_call: PendingCall | null
}

export interface AssistantThread extends AssistantChat {
  messages: AssistantMessage[]
}

export type AssistantEvent =
  | { type: "status"; message: string }
  | { type: "reasoning"; text: string }
  | { type: "commentary"; text: string }
  | { type: "token"; text: string }
  | { type: "retract" }
  | { type: "tool_start"; tool: string; label: string; turn: number }
  | { type: "tool_result"; step: ToolStep; turn?: number }
  | { type: "user_message" | "message"; message: AssistantMessage }
  | { type: "confirm_required" | "questions_required"; call: PendingCall }
  | { type: "questions_answered"; asked: AssistantMessage; message: AssistantMessage }
  | { type: "error"; message: string }
  | { type: "done" | "stopped" }

const BASE = "/api/app/assistant/conversations"
export const CHAT_PAGE = 30
const pathFor = (id: string) => `${BASE}/${encodeURIComponent(id)}`
export const assistantHref = (id: string) => `/assistant/${encodeURIComponent(id)}`
export const listChats = (offset: number) => request<AssistantChat[]>(`${BASE}?limit=${CHAT_PAGE}&offset=${offset}`)
export const createChat = () => request<AssistantChat>(BASE, { method: "POST" })
export const getChat = (id: string) => request<AssistantThread>(pathFor(id))
export const renameChat = (id: string, title: string) =>
  request<AssistantChat>(pathFor(id), { method: "PATCH", body: JSON.stringify({ title }) })
export const deleteChat = (id: string) => request<void>(pathFor(id), { method: "DELETE" })
export const stopTurn = (id: string) => request<{ stopped: boolean }>(`${pathFor(id)}/stop`, { method: "POST" })

export type TurnRequest =
  | { type: "chat"; content: string; context?: UiContext }
  | { type: "confirm"; call_id: string; approved: boolean }
  | { type: "answer"; call_id: string; answers?: Answers }
  | { type: "live" }
  | { type: "retry" }

export async function streamTurn(
  id: string,
  turn: TurnRequest,
  onEvent: (event: AssistantEvent) => void,
  signal: AbortSignal,
) {
  const { type, ...body } = turn
  const get = type === "live"
  const fetchStream = (token: string | null) => fetch(`${API_BASE}${pathFor(id)}/${type}`, {
    method: get ? "GET" : "POST",
    headers: {
      Accept: "text/event-stream",
      ...(get ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: get ? undefined : JSON.stringify(body),
    signal,
  })

  let response = await fetchStream(getAccessToken())
  if (response.status === 401 && !signal.aborted) {
    const token = await refreshAccessToken()
    if (token) response = await fetchStream(token)
  }
  if (!response.ok) {
    const raw = await response.text()
    const { message, detail } = parseDetail(raw)
    throw new ApiError(response.status, raw, message, detail)
  }
  if (!response.body) throw new Error("Couldn't open the reply stream.")

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let complete = false
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let boundary = buffer.indexOf("\n\n")
      while (boundary >= 0) {
        const lines = buffer.slice(0, boundary).split("\n")
        buffer = buffer.slice(boundary + 2)
        const type = lines.find((line) => line.startsWith("event: "))?.slice(7)
        const data = lines.filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n")
        if (type && data) {
          const event: AssistantEvent = { ...JSON.parse(data), type }
          onEvent(event)
          if (type === "done" || type === "stopped" || type === "error") complete = true
        }
        boundary = buffer.indexOf("\n\n")
      }
    }
    if (!complete) throw new Error("The reply stream was interrupted.")
  } finally {
    reader.releaseLock()
  }
}
