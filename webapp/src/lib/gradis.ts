/** Gradis client over SSE. History lives server-side; the browser keeps only display mode and active id. */
import { API_BASE, ApiError, getAccessToken, notifyUpgrade } from "./api"
import type { CitationSource } from "./citations"

/** Where the chat shows: closed, a floating window, or docked. Not to be
 * confused with AgentMode, how much the agent may do. */
export type GradisMode = "closed" | "floating" | "docked"

/** How much the agent may do in a turn; the server owns each mode's tool bundle. */
export type AgentMode = "chat" | "agent"

export const AGENT_MODES: AgentMode[] = ["chat", "agent"]

export const DEFAULT_AGENT_MODE: AgentMode = "agent"

/** One tool call in a turn's log. `ok` is absent while the call runs. */
export interface GradisToolTrace {
  /** Tool events carry no kind; text events do. */
  kind?: undefined
  turn: number
  tool: string
  input: Record<string, unknown>
  result_preview: string
  ok?: boolean
  /** What the result can be cited as, keyed for the conversation. */
  sources?: CitationSource[]
}

/** What the model said in one turn, before its tools ran. */
export interface GradisTurnText {
  kind: "turn"
  turn: number
  note: string
  /** What a thinking model reasoned before it said `note`. */
  thought?: string
}

/** One entry of a turn's ordered log: model text and tool calls, in the
 * order they happened. */
export type GradisSegment = GradisToolTrace | GradisTurnText

export interface GradisMessage {
  id: string
  role: "user" | "assistant"
  content: string
  /** When it was sent or written; UTC, maybe without a zone. */
  created_at?: string | null
  model?: string | null
  /** The turn's tool calls, flat. */
  tools?: GradisToolTrace[]
  /** The turn's ordered log: what the model said and the tools it ran. */
  segments?: GradisSegment[]
  /** The queued prompt this message came from, when it was one. */
  queue_id?: string
  /** The sources the reply cites, in order of first citation. */
  sources?: CitationSource[]
  /** The mode a user turn ran in. */
  mode?: AgentMode | null
  /** What a user turn attached. */
  attachments?: AttachmentSummary[]
  /** The composer's context chips a user turn went out with. */
  context?: SentContextChip[]
}

/** A prompt waiting for the agent to be ready for it. */
export interface GradisQueueItem {
  id: string
  content: string
  /** Urgent: hand it to the running turn instead of waiting for it. */
  urgent: boolean
  created_at?: string
}

export interface GradisConversation {
  id: string
  title: string
  preview: string | null
  message_count: number
  has_pending: boolean
}

export interface PendingCall {
  id: string
  tool: string
  arguments: Record<string, unknown>
  summary: string
  /** The model turn the call came from. */
  turn?: number
  /** The turn's log so far, so a reload keeps the model's words. */
  segments?: GradisSegment[]
}

/** Per-message model pick: a provider id, or "system" for the environment
 * fallback. Null means the active row, else system. */
export interface ChatModelSel {
  provider: string
  effort?: "low" | "medium" | "high" | "xhigh"
}

export type ChatAttachment =
  | { kind: "text"; name: string; text: string }
  | { kind: "image"; name: string; data_url: string; thumb_url?: string }

/** An attachment as a sent message keeps it: what the bubble shows. */
export interface AttachmentSummary {
  kind: "text" | "image"
  name: string
  thumb_url?: string
  /** A document's length once read. */
  chars?: number
}

export function attachmentSummary(items: ChatAttachment[]): AttachmentSummary[] {
  return items.map((item) =>
    item.kind === "image"
      ? { kind: "image", name: item.name, thumb_url: item.thumb_url ?? item.data_url }
      : { kind: "text", name: item.name, chars: item.text.length },
  )
}

/** A composer context chip as a sent prompt keeps it, for display. */
export interface SentContextChip {
  key: string
  label: string
  detail?: string | null
}

export interface GradisUiContext {
  attachments?: ChatAttachment[]
  chips?: SentContextChip[]
  page: string
  run_id?: string | null
  candidate_id?: string | null
  application_id?: string | null
  draft_id?: string | null
  document_id?: string | null
  /** The tailored CV version open on the CV page, if any. */
  cv_version_id?: string | null
  selection?: string | null
}

export type GradisEvent =
  | { type: "context_usage"; input_tokens: number; estimated: boolean; provider: string; model: string }
  | { type: "status"; message: string }
  | { type: "token"; text: string }
  /** A thinking model's reasoning; `reset` drops what it streamed so far
   * (the turn is being asked again). */
  | { type: "reasoning"; text: string; reset?: boolean }
  | { type: "tool_start"; tool: string; input: Record<string, unknown>; turn: number }
  | { type: "tool_result"; tool: string; ok: boolean; preview: string; turn: number }
  /** The sources the call that just finished returned. */
  | { type: "sources"; sources: CitationSource[] }
  | { type: "confirm_required"; call: PendingCall }
  | { type: "user_message"; message: GradisMessage }
  | { type: "message"; message: GradisMessage }
  | { type: "done"; turns: number; usage: Record<string, number> }
  | { type: "error"; message: string }

const MODE_KEY = "gradis.mode"
const ACTIVE_KEY = "gradis.active"
const MODEL_KEY = "graduator.chat_model"
const AGENT_MODE_KEY = "gradis.agent_mode"

/** Persisted agent mode; Agent for anyone who never picked one. */
export function loadAgentMode(): AgentMode {
  try {
    const raw = localStorage.getItem(AGENT_MODE_KEY)
    if (raw === "chat" || raw === "agent") return raw
    if (raw === "ask" || raw === "assist") {
      const mode = raw === "ask" ? "chat" : "agent"
      storeAgentMode(mode)
      return mode
    }
  } catch {
    /* private mode */
  }
  return DEFAULT_AGENT_MODE
}

export function storeAgentMode(mode: AgentMode) {
  try {
    localStorage.setItem(AGENT_MODE_KEY, mode)
  } catch {
    /* ignore */
  }
}

/** Persisted model pick: "auto" or a provider id ("system" is legacy for
 * "auto"). Null means the account default. */
export function loadModelSel(): string | null {
  try {
    const raw = localStorage.getItem(MODEL_KEY)
    if (raw && raw.trim()) return raw.trim() === "system" ? "auto" : raw.trim()
  } catch {
    /* private mode */
  }
  return null
}

export function storeModelSel(sel: string) {
  try {
    localStorage.setItem(MODEL_KEY, sel)
  } catch {
    /* ignore */
  }
}

export function loadMode(): GradisMode {
  try {
    const raw = localStorage.getItem(MODE_KEY)
    if (raw === "floating" || raw === "docked" || raw === "closed") return raw
  } catch {
    /* private mode */
  }
  return "closed"
}

export function storeMode(mode: GradisMode) {
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    /* ignore */
  }
}

export function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY)
  } catch {
    return null
  }
}

export function storeActiveId(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id)
    else localStorage.removeItem(ACTIVE_KEY)
  } catch {
    /* ignore */
  }
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers ?? {}) },
  })
  const text = await res.text()
  if (!res.ok) {
    let message = text
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (typeof parsed.detail === "string") message = parsed.detail
      else if (parsed.detail && typeof parsed.detail === "object") {
        const m = (parsed.detail as { message?: unknown }).message
        if (typeof m === "string") message = m
        notifyUpgrade(res.status, parsed.detail)
      }
    } catch {
      /* keep raw */
    }
    throw new ApiError(res.status, text, message.slice(0, 500))
  }
  return (text ? JSON.parse(text) : undefined) as T
}

/** Chats newest first: all of them, or one page (a short page is the last). */
export const listConversations = (q?: string, page?: { limit: number; offset: number }) => {
  const params = new URLSearchParams()
  if (q?.trim()) params.set("q", q.trim())
  if (page) {
    params.set("limit", String(page.limit))
    params.set("offset", String(page.offset))
  }
  const query = params.toString()
  return req<GradisConversation[]>(`/api/assistant/conversations${query ? `?${query}` : ""}`)
}

export const createConversation = () =>
  req<GradisConversation>("/api/assistant/conversations", { method: "POST" })

export const getConversation = (id: string) =>
  req<{
    id: string
    title: string
    messages: GradisMessage[]
    pending_call: PendingCall | null
    queue: GradisQueueItem[]
    /** A reply is still being written; follow it with streamLive. */
    running?: boolean
  }>(`/api/assistant/conversations/${id}`)

export const queuePrompt = (conversationId: string, content: string, urgent = false) =>
  req<GradisQueueItem>(`/api/assistant/conversations/${conversationId}/queue`, {
    method: "POST",
    body: JSON.stringify({ content, urgent }),
  })

/** Hand a queued prompt to the running turn, or put it back in line. */
export const updateQueuedPrompt = (
  conversationId: string,
  itemId: string,
  urgent: boolean,
) =>
  req<GradisQueueItem>(`/api/assistant/conversations/${conversationId}/queue/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({ urgent }),
  })

export const removeQueuedPrompt = (conversationId: string, itemId: string) =>
  req<{ status: string }>(`/api/assistant/conversations/${conversationId}/queue/${itemId}`, {
    method: "DELETE",
  })

export const deleteConversation = (id: string) =>
  req<{ status: string }>(`/api/assistant/conversations/${id}`, { method: "DELETE" })

export const renameConversation = (id: string, title: string) =>
  req<{ id: string; title: string }>(`/api/assistant/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  })

async function readStream(res: Response, onEvent: (e: GradisEvent) => void) {
  const reader = res.body?.getReader()
  if (!reader) throw new Error("Streaming is not supported in this browser.")
  const decoder = new TextDecoder()
  let buffer = ""
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index: number
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      let name = ""
      let data = ""
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim()
        else if (line.startsWith("data:")) data = line.slice(5).trim()
      }
      if (name && data) onEvent({ type: name, ...JSON.parse(data) } as GradisEvent)
    }
  }
}

async function streamPost(
  path: string,
  body: unknown,
  onEvent: (e: GradisEvent) => void,
  signal?: AbortSignal,
) {
  const res = await fetch(`${API_BASE}${path}`, {
    // No body: a GET that follows a running turn.
    method: body === undefined ? "GET" : "POST",
    headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    const text = await res.text()
    let message = text
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (typeof parsed.detail === "string") message = parsed.detail
    } catch {
      /* keep raw */
    }
    throw new ApiError(res.status, text, message.slice(0, 500))
  }
  await readStream(res, onEvent)
}

export function streamChat(
  conversationId: string,
  content: string,
  context: GradisUiContext,
  onEvent: (e: GradisEvent) => void,
  signal?: AbortSignal,
  model?: ChatModelSel | null,
  opts?: {
    /** Re-run a failed turn from its prompt. */
    retry?: boolean
    /** Replace an earlier prompt and drop everything after it. */
    replaceMessageId?: string | null
    /** Pick up a turn that died after its call was approved. */
    continueTurn?: boolean
    mode?: AgentMode
  },
) {
  return streamPost(
    `/api/assistant/conversations/${conversationId}/chat`,
    {
      content,
      context,
      mode: opts?.mode ?? DEFAULT_AGENT_MODE,
      ...(model ? { model } : {}),
      ...(opts?.retry ? { retry: true } : {}),
      ...(opts?.replaceMessageId ? { replace_message_id: opts.replaceMessageId } : {}),
      ...(opts?.continueTurn ? { continue_turn: true } : {}),
    },
    onEvent,
    signal,
  )
}

/** Follow the chat's running turn, from its first event: after a reload,
 * the reply so far, then the rest as it is written. */
export function streamLive(
  conversationId: string,
  onEvent: (e: GradisEvent) => void,
  signal?: AbortSignal,
) {
  return streamPost(`/api/assistant/conversations/${conversationId}/live`, undefined, onEvent, signal)
}

/** Aborting the stream doesn't stop the turn; this does. */
export const stopTurn = (conversationId: string) =>
  req<{ stopped: boolean }>(`/api/assistant/conversations/${conversationId}/stop`, { method: "POST" })

export function streamConfirm(
  conversationId: string,
  callId: string,
  approved: boolean,
  context: GradisUiContext,
  onEvent: (e: GradisEvent) => void,
  signal?: AbortSignal,
  model?: ChatModelSel | null,
  mode: AgentMode = DEFAULT_AGENT_MODE,
) {
  return streamPost(
    `/api/assistant/conversations/${conversationId}/confirm`,
    { call_id: callId, approved, context, mode, ...(model ? { model } : {}) },
    onEvent,
    signal,
  )
}

export interface ChatModelInfo { provider: string; model: string; input_tokens: number; estimated: boolean; context_window: number | null; effort_levels: ("low" | "medium" | "high" | "xhigh")[] }
export const getChatModelInfo = (provider: string, conversationId: string | null) => req<ChatModelInfo>(`/api/assistant/model-info?provider=${encodeURIComponent(provider === "auto" ? "system" : provider)}${conversationId ? `&conversation_id=${encodeURIComponent(conversationId)}` : ""}`)

export async function uploadChatAttachment(file: File): Promise<ChatAttachment> {
  const body = new FormData()
  body.append("file", file)
  const res = await fetch(`${API_BASE}/api/assistant/attachments`, { method: "POST", headers: authHeaders(), body })
  if (!res.ok) {
    let detail = "Couldn't attach that file"
    try {
      const error: unknown = await res.json()
      if (error && typeof error === "object" && "detail" in error && typeof error.detail === "string") detail = error.detail
    } catch { /* proxy errors may not be JSON */ }
    throw new Error(detail)
  }
  const result: unknown = await res.json()
  if (result && typeof result === "object" && "name" in result && typeof result.name === "string" && "kind" in result) {
    if (result.kind === "text" && "text" in result && typeof result.text === "string") return { kind: "text", name: result.name, text: result.text }
    if (result.kind === "image" && "data_url" in result && typeof result.data_url === "string") return { kind: "image", name: result.name, data_url: result.data_url }
  }
  throw new Error("Couldn't read the attachment response")
}
