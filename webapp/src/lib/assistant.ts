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
  read_apply_kit: { done: "read your apply kit", tried: "tried to read your apply kit" },
  enable_changes: { done: "prepared a change", tried: "tried to prepare a change" },
  track_opportunity: { done: "prepared to track an opportunity", tried: "tried to prepare tracking an opportunity" },
  add_todo: { done: "prepared a to-do", tried: "tried to prepare a to-do" },
}

export function isToolStep(entry: TraceEntry): entry is ToolStep {
  return entry.kind === undefined || entry.kind === "tool"
}

export function activitySummary(entries: TraceEntry[]): string {
  const phrases: string[] = entries.some((e) => e.kind === "thought") ? ["thought it through"] : []
  for (const entry of entries) {
    if (!isToolStep(entry)) continue
    const summary = TOOL_SUMMARY[entry.tool] ?? { done: "used a tool", tried: "tried a tool" }
    const phrase = entry.ok ? summary.done : summary.tried
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

type RecordKind = "application" | "todo" | "project" | "document" | "answer" | "web" | "opportunity"

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

export interface AssistantMessage {
  id: string
  role: "user" | "assistant"
  content: string
  trace: TraceEntry[]
  sources: AssistantSource[]
  cited_deadlines: boolean
  created_at: string
}

export interface PendingCall {
  id: string
  tool?: string
  summary: string
  trace: TraceEntry[]
  note: string
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
  | { type: "confirm_required"; call: PendingCall }
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
  | { type: "chat"; content: string }
  | { type: "confirm"; call_id: string; approved: boolean }
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
