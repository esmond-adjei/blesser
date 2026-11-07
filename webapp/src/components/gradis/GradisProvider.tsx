import { useAutoPageContext } from "../../lib/chatPreferences"
import { SelectionContext } from "./SelectionContext"
import { toolActivity } from "../../lib/toolActivity"
/* eslint-disable react/only-export-components -- provider + hook ship together */
import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useLocation, useParams } from "react-router-dom"
import { ApiError, apiMessage } from "../../lib/api"
import {
  attachmentSummary,
  createConversation,
  deleteConversation as deleteConversationApi,
  getConversation,
  listConversations,
  loadActiveId,
  loadAgentMode,
  loadMode,
  loadModelSel,
  queuePrompt,
  removeQueuedPrompt,
  renameConversation as renameConversationApi,
  storeActiveId,
  storeAgentMode,
  storeMode,
  storeModelSel,
  streamChat,
  streamConfirm,
  streamLive,
  stopTurn,
  updateQueuedPrompt,
  type AgentMode,
  type ChatModelSel,
  type ChatAttachment,
  type GradisEvent,
  type GradisMessage,
  type GradisMode,
  type GradisQueueItem,
  type GradisSegment,
  type GradisTurnText,
  type GradisUiContext,
  type PendingCall,
} from "../../lib/gradis"
import type { GradisConversation } from "../../lib/gradis"
import { usableRunModel, useDefaultModel, useProviderConfigs } from "../../lib/providers"

/** A failed turn, snapshotted so retry replays the same text, context, and model. */
export interface FailedTurn {
  conversationId: string
  text: string
  context: GradisUiContext
  model: ChatModelSel | null
  mode: AgentMode
  attempts: number
  /** Epoch ms before which retry stays disabled (backoff). */
  retryAt: number
  /** The turn died after its call was approved: carry on from there. */
  continueTurn?: boolean
}

/** Free first retry, then back off to avoid a request storm. */
const RETRY_BACKOFF_MS = [0, 4_000, 15_000, 60_000]

function backoffFor(attempts: number): number {
  return RETRY_BACKOFF_MS[Math.min(attempts - 1, RETRY_BACKOFF_MS.length - 1)]
}

type StreamOutcome = "ok" | "failed" | "aborted"

const toShownModel = (value: string) => (value === "system" ? "auto" : value)

export interface ContextChip {
  key: string
  label: string
  detail?: string
  tokens?: number
  /** Sent with the next message; otherwise only suggested. */
  added?: boolean
}

type GradisContextValue = {
  mode: GradisMode
  setMode: (mode: GradisMode) => void
  toggle: () => void
  conversations: GradisConversation[]
  activeId: string | null
  title: string
  messages: GradisMessage[]
  draft: GradisMessage | null
  activity: string | null
  pendingCall: PendingCall | null
  queue: GradisQueueItem[]
  /** Park a prompt until the agent is ready; urgent goes to the running turn. */
  enqueue: (text: string, urgent?: boolean) => Promise<void>
  removeQueued: (id: string) => Promise<void>
  promoteQueued: (id: string) => Promise<void>
  sending: boolean
  loading: boolean
  error: string | null
  notice: string | null
  send: (text: string) => Promise<void>
  /** Open a new agent-mode chat and send it `text`: a page's one-click task. */
  ask: (text: string) => void
  stop: () => void
  confirm: (approved: boolean) => Promise<void>
  select: (id: string) => Promise<"ok" | "gone" | "failed">
  /** Clear to an unsaved new chat; saved on its first prompt. False while streaming. */
  newChat: () => boolean
  remove: (id: string) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  /** More chats past the loaded pages; the sidebar scrolls for them. */
  hasMoreConversations: boolean
  loadingMoreConversations: boolean
  loadMoreConversations: () => Promise<void>
  contextChips: ContextChip[]
  /** The page's chips, added or only suggested. */
  suggestedChips: ContextChip[]
  toggleChip: (key: string) => void
  dismissChip: (key: string) => void
  attachments: ChatAttachment[]
  setAttachments: React.Dispatch<React.SetStateAction<ChatAttachment[]>>
  attachSelection: (text: string) => boolean
  /** Chat model pick: "auto", "system", or a provider id. */
  modelSel: string
  setModelSel: (sel: string) => void
  effort: ChatModelSel["effort"]
  setEffort: (effort: ChatModelSel["effort"]) => void
  contextUsage: Extract<GradisEvent, { type: "context_usage" }> | null
  agentMode: AgentMode
  setAgentMode: (mode: AgentMode) => void
  /** Unsent composer text; lives here to survive dock <-> float remounts. */
  composer: string
  setComposer: (text: string) => void
  /** Replace a sent prompt (same text = regenerate); later turns are dropped. */
  resubmit: (userMessageId: string, text: string) => Promise<void>
  editingId: string | null
  startEdit: (id: string, text: string) => void
  cancelEdit: () => void
  failedTurn: FailedTurn | null
  retry: () => Promise<void>
}

const GradisContext = React.createContext<GradisContextValue | null>(null)

export function useGradis() {
  const ctx = React.useContext(GradisContext)
  if (!ctx) throw new Error("useGradis must be used inside GradisProvider")
  return ctx
}

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id
}

/** The live turn: what has happened so far, in order. `text` is the
 * model's text still streaming, `thought` its reasoning before it; `turn`
 * is the model turn they belong to. */
interface LiveTurn {
  events: GradisSegment[]
  text: string
  thought: string
  turn: number
}

const freshTurn = (): LiveTurn => ({ events: [], text: "", thought: "", turn: 1 })

/** The turn's words so far as a segment, or null before there are any. */
function liveText(live: LiveTurn, turn: number): GradisTurnText | null {
  if (!live.text.trim() && !live.thought.trim()) return null
  return { kind: "turn", turn, note: live.text, ...(live.thought ? { thought: live.thought } : {}) }
}

function isTurnText(segment: GradisSegment): segment is GradisTurnText {
  return segment.kind === "turn"
}

function useStreamHandler() {
  const [contextUsage, setContextUsage] = React.useState<Extract<GradisEvent, { type: "context_usage" }> | null>(null)

  const [draft, setDraft] = React.useState<GradisMessage | null>(null)
  const [activity, setActivity] = React.useState<string | null>(null)
  const [pendingCall, setPendingCall] = React.useState<PendingCall | null>(null)
  const liveRef = React.useRef<LiveTurn>(freshTurn())
  // The row of the call waiting for approval: the resumed turn announces
  // it again, so the row is filled in rather than added twice.
  const pendingRowRef = React.useRef<number | null>(null)

  const draftOf = React.useCallback((): GradisMessage | null => {
    const live = liveRef.current
    const words = liveText(live, live.turn)
    const segments: GradisSegment[] = words ? [...live.events, words] : [...live.events]
    if (segments.length === 0) return null
    return {
      id: "streaming",
      role: "assistant",
      content: segments.filter(isTurnText).map((s) => s.note).join("\n\n"),
      segments,
    }
  }, [])

  const reset = React.useCallback(() => {
    setDraft(null)
    setContextUsage(null)
    setActivity(null)
    liveRef.current = freshTurn()
    pendingRowRef.current = null
  }, [])

  /** A turn waiting for approval: the model's words so far and the call
   * it is asking about. A reload finds it on the conversation. */
  const seedPending = React.useCallback(
    (call: PendingCall | null) => {
      if (!call) return
      const events: GradisSegment[] = (call.segments ?? []).map((s) => ({ ...s }))
      events.push({
        turn: call.turn ?? 1,
        tool: call.tool,
        input: call.arguments,
        result_preview: "",
      })
      liveRef.current = { ...freshTurn(), events, turn: (call.turn ?? 1) + 1 }
      pendingRowRef.current = events.length - 1
      setDraft(draftOf())
    },
    [draftOf],
  )

  const handle = React.useCallback(
    (
      event: GradisEvent,
      actions: {
        pushMessage: (m: GradisMessage) => void
        refreshIndex: () => void
        fail: (message: string) => void
        /** A queued prompt was answered: it is not waiting any more. */
        dequeue: (id?: string) => void
      },
    ) => {
      const live = liveRef.current
      switch (event.type) {
        case "context_usage":
          setContextUsage(event)
          break
        case "status":
          setActivity(event.message)
          break
        case "reasoning":
          // The thoughts show as they stream; they say what is happening.
          setActivity(null)
          live.thought = event.reset ? "" : live.thought + event.text
          setDraft(draftOf())
          break
        case "token":
          setActivity(null)
          live.text += event.text
          setDraft(draftOf())
          break
        case "tool_start": {
          const pendingIndex = pendingRowRef.current
          if (pendingIndex !== null && pendingIndex === live.events.length - 1) {
            // The approved call, now running: fill in the row the
            // approval card made instead of adding a second one.
            live.events[pendingIndex] = {
              turn: live.events[pendingIndex].turn,
              tool: event.tool,
              input: event.input,
              result_preview: "",
            }
            pendingRowRef.current = null
          } else {
            // The model's text for this turn ends where its tools start.
            const words = liveText(live, event.turn)
            if (words) live.events.push(words)
            live.text = ""
            live.thought = ""
            live.events.push({
              turn: event.turn,
              tool: event.tool,
              input: event.input,
              result_preview: "",
            })
          }
          live.turn = event.turn + 1
          setActivity(`${toolActivity({ tool: event.tool, input: event.input }).label}…`)
          setDraft(draftOf())
          break
        }
        case "tool_result": {
          // The call that just finished is the running one: the last row
          // without a verdict.
          for (let i = live.events.length - 1; i >= 0; i--) {
            const e = live.events[i]
            if (isTurnText(e)) continue
            if (e.ok === undefined) {
              e.ok = event.ok
              e.result_preview = event.preview
              break
            }
          }
          setActivity(null)
          setDraft(draftOf())
          break
        }
        case "sources": {
          // The call that just finished: the last tool row.
          for (let i = live.events.length - 1; i >= 0; i--) {
            const e = live.events[i]
            if (isTurnText(e)) continue
            e.sources = event.sources
            break
          }
          setDraft(draftOf())
          break
        }
        case "confirm_required": {
          setPendingCall(event.call)
          setActivity(null)
          const turn = event.call.turn ?? live.turn
          // The model's words for this turn end where the request starts.
          const words = liveText(live, turn)
          if (words) live.events.push(words)
          live.text = ""
          live.thought = ""
          // The call waiting for approval gets a row of its own, so the
          // trace says what is being asked.
          live.events.push({
            turn,
            tool: event.call.tool,
            input: event.call.arguments,
            result_preview: "",
          })
          pendingRowRef.current = live.events.length - 1
          live.turn = turn + 1
          setDraft(draftOf())
          break
        }
        case "user_message":
          // A prompt the student sent while the agent worked: it is in the
          // transcript now, so the queue no longer holds it.
          actions.pushMessage(event.message)
          actions.dequeue(event.message.queue_id)
          break
        case "message":
          // The turn is in the transcript now; the live copy steps aside.
          liveRef.current = freshTurn()
          pendingRowRef.current = null
          setDraft(null)
          actions.pushMessage(event.message)
          actions.refreshIndex()
          break
        case "done":
          actions.refreshIndex()
          break
        case "error":
          setActivity(null)
          actions.fail(event.message)
          break
      }
    },
    [draftOf],
  )

  return {
    contextUsage,
    draft,
    activity,
    setActivity,
    pendingCall,
    setPendingCall,
    reset,
    seedPending,
    handle,
  }
}

const CHAT_PAGE = 30

/** The unsaved chat's title; the server names it from the first prompt. */
const NEW_CHAT_TITLE = "New Gradis chat"

/** Tools whose results are new suggestions on a document (api/assistant/modes.py). */
const SUGGEST_TOOLS = new Set(["cv_suggest_changes", "suggest_changes"])
const PROFESSOR_TOOLS = new Set(["update_professor", "save_professor_papers"])

export function GradisProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = React.useState<GradisMode>(() => loadMode())
  const [conversations, setConversations] = React.useState<GradisConversation[]>([])
  const [hasMoreConversations, setHasMoreConversations] = React.useState(false)
  // A chat opened while its reply is still being written (after a
  // reload, or from another tab): the effect below follows it.
  const [followId, setFollowId] = React.useState<string | null>(null)
  const [loadingMoreConversations, setLoadingMoreConversations] = React.useState(false)
  // How many chats are loaded, so a refresh re-reads that window, not page 1.
  const loadedRef = React.useRef(0)
  loadedRef.current = conversations.length
  const [activeId, setActiveId] = React.useState<string | null>(() => loadActiveId())
  const [title, setTitle] = React.useState(NEW_CHAT_TITLE)
  const [messages, setMessages] = React.useState<GradisMessage[]>([])
  const [sending, setSending] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [notice, setNotice] = React.useState<string | null>(null)
  // Auto-detected chips the user removed, plus an attached text selection.
  const [autoContext] = useAutoPageContext()
  // A chip the user added, took back out, or dismissed on this page.
  const [chipState, setChipState] = React.useState<Record<string, "added" | "off" | "dismissed">>({})
  const [attachments, setAttachments] = React.useState<ChatAttachment[]>([])
  const [attachedSelection, setAttachedSelection] = React.useState<string | null>(null)
  const [pickedModel, setModelSelState] = React.useState<string | null>(() => loadModelSel())
  const [agentMode, setAgentModeState] = React.useState<AgentMode>(() => loadAgentMode())
  // Fall back to the account default so a send never names a model that is gone.
  const defaultModel = useDefaultModel()
  const providerConfigs = useProviderConfigs()
  const requested = pickedModel == null ? "default" : pickedModel === "auto" ? "system" : pickedModel
  const modelSel = toShownModel(
    usableRunModel(
      requested,
      providerConfigs.configs,
      !providerConfigs.isLoading && !providerConfigs.isError,
      defaultModel,
    ),
  )
  const [effort, setEffort] = React.useState<ChatModelSel["effort"]>()
  const [composer, setComposer] = React.useState("")
  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [failedTurn, setFailedTurn] = React.useState<FailedTurn | null>(null)
  const [queue, setQueue] = React.useState<GradisQueueItem[]>([])
  const stream = useStreamHandler()
  const queryClient = useQueryClient()
  const location = useLocation()
  const params = useParams()
  const busyRef = React.useRef(false)
  // Set once anything picks a chat, so mount-time resume cannot switch away late.
  const pickedRef = React.useRef(false)
  const abortRef = React.useRef<AbortController | null>(null)
  // The prompt of the turn in flight, so a turn that dies after its
  // approval can be picked up with the same text.
  const lastPromptRef = React.useRef("")
  // A chat deleted mid-stream: the id to land on once the reply finishes
  // ("new" starts a fresh chat), instead of leaving the page on a gone id.
  const pendingSwitchRef = React.useRef<string | "new" | null>(null)

  const setMode = React.useCallback((next: GradisMode) => {
    setModeState(next)
    storeMode(next)
  }, [])

  const setAgentMode = React.useCallback((next: AgentMode) => {
    setAgentModeState(next)
    storeAgentMode(next)
  }, [])

  const toggle = React.useCallback(() => {
    setModeState((prev) => {
      const next: GradisMode = prev === "closed" ? "floating" : "closed"
      storeMode(next)
      return next
    })
  }, [])

  const refreshIndex = React.useCallback(async () => {
    try {
      const size = Math.max(CHAT_PAGE, loadedRef.current)
      const index = await listConversations(undefined, { limit: size, offset: 0 })
      setConversations(index)
      setHasMoreConversations(index.length === size)
    } catch {
      /* index refresh is best-effort during a stream */
    }
  }, [])

  const loadingMoreRef = React.useRef(false)
  const loadMoreConversations = React.useCallback(async () => {
    if (loadingMoreRef.current) return
    loadingMoreRef.current = true
    setLoadingMoreConversations(true)
    try {
      const page = await listConversations(undefined, { limit: CHAT_PAGE, offset: loadedRef.current })
      // A chat that moved up since the last page can show up again: keep one.
      setConversations((prev) => {
        const seen = new Set(prev.map((c) => c.id))
        return [...prev, ...page.filter((c) => !seen.has(c.id))]
      })
      setHasMoreConversations(page.length === CHAT_PAGE)
    } catch (err) {
      setError(apiMessage(err))
    } finally {
      loadingMoreRef.current = false
      setLoadingMoreConversations(false)
    }
  }, [])

  // Following a turn after a reload replays it from the top: what the
  // transcript already holds is not added twice.
  const pushMessage = React.useCallback((m: GradisMessage) => {
    setMessages((prev) => (prev.some((p) => p.id === m.id) ? prev : [...prev, m]))
  }, [])

  const dequeue = React.useCallback((id?: string) => {
    if (!id) return
    setQueue((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const enqueue = React.useCallback(
    async (text: string, urgent = false) => {
      const trimmed = text.trim()
      if (!trimmed || !activeId) return
      try {
        const item = await queuePrompt(activeId, trimmed, urgent)
        setQueue((prev) => [...prev, item])
      } catch (err) {
        setError(apiMessage(err))
      }
    },
    [activeId],
  )

  const removeQueued = React.useCallback(
    async (id: string) => {
      if (!activeId) return
      setQueue((prev) => prev.filter((item) => item.id !== id))
      try {
        await removeQueuedPrompt(activeId, id)
      } catch (err) {
        setError(apiMessage(err))
      }
    },
    [activeId],
  )

  const fail = React.useCallback((message: string) => {
    setError(message)
  }, [])

  const select = React.useCallback(
    async (id: string): Promise<"ok" | "gone" | "failed"> => {
      if (busyRef.current) return "failed"
      pickedRef.current = true
      setLoading(true)
      setError(null)
      setFailedTurn(null)
      setEditingId(null)
      stream.reset()
      try {
        const conv = await getConversation(id)
        setActiveId(id)
        storeActiveId(id)
        setTitle(conv.title)
        setMessages(conv.messages)
        stream.setPendingCall(conv.pending_call)
        stream.seedPending(conv.pending_call)
        setQueue(conv.queue ?? [])
        if (conv.running) setFollowId(id)
        return "ok"
      } catch (err) {
        setError(apiMessage(err))
        return err instanceof ApiError && err.status === 404 ? "gone" : "failed"
      } finally {
        setLoading(false)
      }
    },
    [stream],
  )

  const ensureConversation = React.useCallback(async (): Promise<string | null> => {
    if (activeId) return activeId
    try {
      const conv = await createConversation()
      setActiveId(conv.id)
      storeActiveId(conv.id)
      setTitle(conv.title)
      setMessages([])
      await refreshIndex()
      return conv.id
    } catch (err) {
      setError(apiMessage(err))
      return null
    }
  }, [activeId, refreshIndex])

  React.useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        const index = await listConversations(undefined, { limit: CHAT_PAGE, offset: 0 })
        if (cancelled) return
        setConversations(index)
        setHasMoreConversations(index.length === CHAT_PAGE)
        if (pickedRef.current) return
        const stored = loadActiveId()
        // The last open chat may be older than the first page: ask for it
        // directly, and fall back to the newest when it is gone.
        const remembered = stored
          ? await getConversation(stored).catch(() => null)
          : null
        if (stored && remembered) {
          const conv = remembered
          if (cancelled || pickedRef.current) return
          setActiveId(stored)
          setTitle(conv.title)
          setMessages(conv.messages)
          stream.setPendingCall(conv.pending_call)
          stream.seedPending(conv.pending_call)
          setQueue(conv.queue ?? [])
          if (conv.running) setFollowId(stored)
        } else if (index.length > 0) {
          const conv = await getConversation(index[0].id)
          if (cancelled || pickedRef.current) return
          setActiveId(index[0].id)
          storeActiveId(index[0].id)
          setTitle(conv.title)
          setMessages(conv.messages)
          stream.setPendingCall(conv.pending_call)
          stream.seedPending(conv.pending_call)
          setQueue(conv.queue ?? [])
          if (conv.running) setFollowId(index[0].id)
        } else {
          setActiveId(null)
          storeActiveId(null)
        }
      } catch (err) {
        if (!cancelled) setError(apiMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void init()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only bootstrap
  }, [])

  // Fresh page, fresh context: re-enable auto chips on navigation.
  const pageKey = `${location.pathname}${location.search}${params.runId ?? ""}${params.candidateId ?? ""}${(params as Record<string, string | undefined>).appId ?? ""}${(params as Record<string, string | undefined>).draftId ?? ""}${(params as Record<string, string | undefined>).documentId ?? ""}`
  React.useEffect(() => {
    setChipState({})
    setAttachedSelection(null)
  }, [pageKey])

  const suggestedChips = React.useMemo<ContextChip[]>(() => {
    // The chat page itself says nothing about what the user is asking.
    const chips: ContextChip[] = location.pathname.startsWith("/chat")
      ? []
      : [{ key: "page", label: "Page", detail: location.pathname }]
    if (params.runId)
      chips.push({ key: "run", label: "Run", detail: shortId(params.runId) })
    if (params.candidateId)
      chips.push({
        key: "candidate",
        label: "Candidate",
        detail: shortId(params.candidateId),
      })
    const appId = (params as Record<string, string | undefined>).appId
    if (appId) chips.push({ key: "application", label: "Application", detail: shortId(appId) })
    const draftId = (params as Record<string, string | undefined>).draftId
    if (draftId)
      chips.push({ key: "draft", label: "Draft", detail: shortId(draftId) })
    const documentId = (params as Record<string, string | undefined>).documentId
    // An unsaved CV variant isn't on the server for Gradis to read:
    // no CV context until it's saved, so nothing lands on the base CV.
    // Nor a new one that isn't saved yet (/documents/new).
    if (documentId && documentId !== "new" && !new URLSearchParams(location.search).get("draft"))
      chips.push({
        key: "cv",
        label: new URLSearchParams(location.search).get("version") ? "Document version" : "Document",
        detail: shortId(documentId),
      })
    if (attachedSelection)
      chips.push({
        key: "selection",
        label: "Selection",
        tokens: Math.ceil(attachedSelection.length / 4),
        detail:
          attachedSelection.length > 60
            ? `${attachedSelection.slice(0, 60)}…`
            : attachedSelection,
      })
    return chips
      .filter((c) => chipState[c.key] !== "dismissed")
      .map((c) => ({ ...c, added: chipState[c.key] ? chipState[c.key] === "added" : autoContext || c.key === "selection" }))
  }, [location.pathname, location.search, params, attachedSelection, chipState, autoContext])
  const contextChips = React.useMemo(() => suggestedChips.filter((c) => c.added), [suggestedChips])

  const setModelSel = React.useCallback((sel: string) => {
    setModelSelState(sel)
    setEffort(undefined)
    storeModelSel(sel)
  }, [])

  const toModelOverride = React.useCallback((sel: string): ChatModelSel => {
    // Auto is the system environment model; a provider id uses that row.
    return { provider: sel === "auto" || sel === "system" ? "system" : sel, effort }
  }, [effort])

  const toggleChip = React.useCallback((key: string) => {
    setChipState((prev) => ({ ...prev, [key]: suggestedChips.find((c) => c.key === key)?.added ? "off" : "added" }))
  }, [suggestedChips])
  const dismissChip = React.useCallback((key: string) => {
    setChipState((prev) => ({ ...prev, [key]: "dismissed" }))
  }, [])

  const attachSelection = React.useCallback((text: string) => {
    if (!text) return false
    setAttachedSelection(text.slice(0, 5000))
    setChipState((prev) => ({ ...prev, selection: "added" }))
    return true
  }, [])

  const buildContext = React.useCallback((): GradisUiContext => {
    const keys = new Set(contextChips.map((c) => c.key))
    return {
      page: keys.has("page") ? location.pathname + location.search : "",
      run_id: keys.has("run") ? (params.runId ?? null) : null,
      candidate_id: keys.has("candidate") ? (params.candidateId ?? null) : null,
      application_id: keys.has("application")
        ? ((params as Record<string, string | undefined>).appId ?? null)
        : null,
      draft_id: keys.has("draft")
        ? ((params as Record<string, string | undefined>).draftId ?? null)
        : null,
      document_id: keys.has("cv")
        ? ((params as Record<string, string | undefined>).documentId ?? null)
        : null,
      cv_version_id: keys.has("cv") ? new URLSearchParams(location.search).get("version") : null,
      selection: keys.has("selection") ? attachedSelection : null,
      attachments,
      chips: contextChips.map(({ key, label, detail }) => ({ key, label, ...(detail ? { detail } : {}) })),
    }
  }, [contextChips, location.pathname, location.search, params, attachedSelection, attachments])

  // The chat whose turn is on screen, so Stop reaches the right one.
  const streamingIdRef = React.useRef<string | null>(null)
  const runStream = React.useCallback(
    async (
      conversationId: string,
      fn: (onEvent: (e: GradisEvent) => void, signal: AbortSignal) => Promise<void>,
      opts?: { continueTurn?: boolean },
    ): Promise<StreamOutcome> => {
      if (busyRef.current) return "aborted"
      busyRef.current = true
      streamingIdRef.current = conversationId
      let outcome: StreamOutcome = "ok"
      const controller = new AbortController()
      abortRef.current = controller
      setSending(true)
      setError(null)
      setNotice(null)
      // A resumed turn continues the one on screen; a new turn starts
      // from an empty log.
      if (!opts?.continueTurn) stream.reset()
      try {
        await fn(
          (event) => {
            if (event.type === "error") outcome = "failed"
            // Changes Gradis suggests show up in an open editor's Review list at once.
            if (event.type === "tool_result" && event.ok && SUGGEST_TOOLS.has(event.tool))
              void queryClient.invalidateQueries({ queryKey: ["document-suggestions"] })
            // A professor's new papers show on their open page.
            if (event.type === "tool_result" && event.ok && PROFESSOR_TOOLS.has(event.tool))
              for (const key of ["professor", "candidate", "faculty"]) void queryClient.invalidateQueries({ queryKey: [key] })
            stream.handle(event, { pushMessage, refreshIndex, fail, dequeue })
          },
          controller.signal,
        )
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setNotice("Stream stopped.")
          outcome = "aborted"
        } else {
          setError(apiMessage(err))
          outcome = "failed"
        }
      } finally {
        busyRef.current = false
        abortRef.current = null
        streamingIdRef.current = null
        setSending(false)
        stream.setActivity(null)
        // The live log is not cleared here: a turn that paused for
        // approval keeps the model's words on screen until the user
        // answers, and a failed turn keeps what it had produced.
      }
      return outcome
    },
    [fail, pushMessage, refreshIndex, stream, dequeue, queryClient],
  )

  // The turn runs on the server whether or not anyone reads it (a reload
  // must not lose the reply), so stopping asks the server, then hangs up.
  const stop = React.useCallback(() => {
    const id = streamingIdRef.current
    if (id) void stopTurn(id).catch(() => undefined)
    abortRef.current?.abort()
  }, [])

  const reconcile = React.useCallback(
    async (id: string) => {
      try {
        const conv = await getConversation(id)
        setMessages(conv.messages)
        setTitle(conv.title)
        // A failed stream can leave a confirmation pending on the server;
        // resurface its card rather than stranding it.
        stream.setPendingCall(conv.pending_call)
        // The queue moves with the turn: what was answered is gone from it.
        setQueue(conv.queue ?? [])
      } catch {
        /* best-effort transcript refresh */
      }
    },
    [stream],
  )

  // Pick up a reply still being written: replay it from the top, then
  // follow it live. Ended in between (404), the transcript has it.
  React.useEffect(() => {
    if (!followId) return
    setFollowId(null)
    if (busyRef.current) return
    const id = followId
    void (async () => {
      await runStream(id, async (onEvent, signal) => {
        try {
          await streamLive(id, onEvent, signal)
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 404)) throw err
        }
      })
      await reconcile(id)
      await refreshIndex()
    })()
  }, [followId, runStream, reconcile, refreshIndex])

  const send = React.useCallback(
    async (text: string) => {
      const context = buildContext()
      const attached = context.attachments ?? []
      // A message needs words: an attachment sent on its own gets a few.
      const trimmed = text.trim() || (attached.length ? "See attached." : "")
      if (!trimmed || busyRef.current) return
      setEditingId(null)
      const id = await ensureConversation()
      if (!id) return
      setAttachments([])
      const model = toModelOverride(modelSel)
      setFailedTurn(null)
      lastPromptRef.current = trimmed
      const mode = agentMode
      pushMessage({ id: `local-${Date.now()}`, role: "user", created_at: new Date().toISOString(), content: trimmed, mode, attachments: attachmentSummary(attached), context: context.chips })
      const outcome = await runStream(id, (onEvent, signal) =>
        streamChat(id, trimmed, context, onEvent, signal, model, { mode }),
      )
      if (outcome === "failed") {
        setFailedTurn({
          conversationId: id,
          text: trimmed,
          context,
          model,
          mode,
          attempts: 1,
          retryAt: Date.now() + backoffFor(1),
        })
      }
      await reconcile(id)
      // Refresh the list so the first prompt's server-assigned title appears.
      await refreshIndex()
    },
    [buildContext, ensureConversation, pushMessage, runStream, reconcile, refreshIndex, modelSel, toModelOverride, agentMode],
  )

  /** Hand a queued prompt to the running turn; with nothing running, it
   * goes out as an ordinary prompt. */
  const promoteQueued = React.useCallback(
    async (id: string) => {
      if (!activeId) return
      const item = queue.find((q) => q.id === id)
      if (!item) return
      // A turn in flight — or one waiting for an approval — takes the
      // prompt; a second turn would be refused while it holds the chat.
      if (busyRef.current || stream.pendingCall) {
        try {
          const updated = await updateQueuedPrompt(activeId, id, true)
          setQueue((prev) => prev.map((q) => (q.id === id ? updated : q)))
        } catch (err) {
          setError(apiMessage(err))
        }
        return
      }
      // Nothing is running: send it now, in its own turn.
      await removeQueued(id)
      await send(item.content)
    },
    [activeId, queue, removeQueued, send, stream.pendingCall],
  )

  const resubmit = React.useCallback(
    async (userMessageId: string, text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !activeId || busyRef.current) return
      const context = buildContext()
      const model = toModelOverride(modelSel)
      setEditingId(null)
      setFailedTurn(null)
      lastPromptRef.current = trimmed
      // The server drops this prompt and everything after it before running
      // the replacement. Mirror that locally so nothing flickers.
      setMessages((prev) => {
        const index = prev.findIndex((m) => m.id === userMessageId)
        if (index < 0)
          return [...prev, { id: `local-${Date.now()}`, role: "user", created_at: new Date().toISOString(), content: trimmed }]
        const next = prev.slice(0, index + 1)
        next[index] = { ...next[index], content: trimmed }
        return next
      })
      const mode = agentMode
      const outcome = await runStream(activeId, (onEvent, signal) =>
        streamChat(activeId, trimmed, context, onEvent, signal, model, {
          replaceMessageId: userMessageId,
          mode,
        }),
      )
      if (outcome === "failed") {
        setFailedTurn({
          conversationId: activeId,
          text: trimmed,
          context,
          model,
          mode,
          attempts: 1,
          retryAt: Date.now() + backoffFor(1),
        })
      }
      await reconcile(activeId)
      await refreshIndex()
    },
    [activeId, buildContext, modelSel, toModelOverride, agentMode, runStream, reconcile, refreshIndex],
  )

  const startEdit = React.useCallback((id: string, text: string) => {
    setEditingId(id)
    setComposer(text)
  }, [])

  const cancelEdit = React.useCallback(() => {
    setEditingId(null)
    setComposer("")
  }, [])

  const retry = React.useCallback(async () => {
    const turn = failedTurn
    if (!turn || busyRef.current || Date.now() < turn.retryAt) return
    if (turn.conversationId !== activeId) return
    // The server reuses the persisted message; restore the local bubble
    // if the failed attempt never added one.
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      return last?.role === "user" && last.content === turn.text
        ? prev
        : [...prev, { id: `local-${Date.now()}`, role: "user", created_at: new Date().toISOString(), content: turn.text, mode: turn.mode }]
    })
    const outcome = await runStream(
      turn.conversationId,
      (onEvent, signal) =>
        streamChat(turn.conversationId, turn.text, turn.context, onEvent, signal, turn.model, {
          ...(turn.continueTurn ? { continueTurn: true } : { retry: true }),
          mode: turn.mode,
        }),
      // A continued turn keeps the output it already produced.
      { continueTurn: turn.continueTurn },
    )
    if (outcome === "failed") {
      const attempts = turn.attempts + 1
      setFailedTurn({ ...turn, attempts, retryAt: Date.now() + backoffFor(attempts) })
    } else {
      setFailedTurn(null)
    }
    await reconcile(turn.conversationId)
  }, [failedTurn, activeId, runStream, reconcile])

  const confirm = React.useCallback(
    async (approved: boolean) => {
      if (!activeId || !stream.pendingCall || busyRef.current) return
      const callId = stream.pendingCall.id
      stream.setPendingCall(null)
      const context = buildContext()
      const model = toModelOverride(modelSel)
      const mode = agentMode
      const outcome = await runStream(
        activeId,
        (onEvent, signal) =>
          streamConfirm(activeId, callId, approved, context, onEvent, signal, model, mode),
        // The approval continues the turn on screen: its words stay put.
        { continueTurn: true },
      )
      if (outcome === "failed") {
        // The turn died after the approval. It can be picked up where it
        // stopped, without asking again and without running the call twice.
        setFailedTurn({
          conversationId: activeId,
          text: lastPromptRef.current,
          context,
          model,
          mode,
          attempts: 1,
          retryAt: Date.now() + backoffFor(1),
          continueTurn: true,
        })
      }
      await reconcile(activeId)
    },
    [activeId, buildContext, runStream, stream, reconcile, modelSel, toModelOverride, agentMode],
  )

  const newChat = React.useCallback((): boolean => {
    if (busyRef.current) return false
    pickedRef.current = true
    setError(null)
    setFailedTurn(null)
    setEditingId(null)
    stream.reset()
    setActiveId(null)
    setAttachments([])
    setAttachedSelection(null)
    storeActiveId(null)
    setTitle(NEW_CHAT_TITLE)
    setMessages([])
    setQueue([])
    stream.setPendingCall(null)
    return true
  }, [stream])

  // ask() starts a fresh chat; the prompt goes once send sees no chat open.
  const [asking, setAsking] = React.useState<string | null>(null)
  const ask = React.useCallback(
    (text: string) => {
      if (!newChat()) return
      setAgentMode("agent")
      setModeState((prev) => (prev === "closed" ? "floating" : prev))
      setAsking(text)
    },
    [newChat, setAgentMode],
  )
  React.useEffect(() => {
    if (asking === null || activeId !== null) return
    setAsking(null)
    void send(asking)
  }, [asking, activeId, send])

  const remove = React.useCallback(
    async (id: string) => {
      try {
        await deleteConversationApi(id)
        const next = conversations.filter((c) => c.id !== id)
        setConversations(next)
        if (id !== activeId) return
        if (busyRef.current) {
          // The reply outlives the deleted chat; move on when it finishes.
          pendingSwitchRef.current = next[0]?.id ?? "new"
          return
        }
        if (next.length > 0) await select(next[0].id)
        else newChat()
      } catch (err) {
        setError(apiMessage(err))
      }
    },
    [activeId, conversations, newChat, select],
  )

  // Flush the mid-stream delete switch once the reply ends.
  React.useEffect(() => {
    if (sending || pendingSwitchRef.current === null) return
    const pending = pendingSwitchRef.current
    pendingSwitchRef.current = null
    if (pending === "new") newChat()
    else void select(pending)
  }, [sending, newChat, select])

  const rename = React.useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim()
      if (!trimmed) return
      try {
        const updated = await renameConversationApi(id, trimmed)
        setConversations((prev) =>
          prev.map((c) => (c.id === id ? { ...c, title: updated.title } : c)),
        )
        if (id === activeId) setTitle(updated.title)
      } catch (err) {
        setError(apiMessage(err))
      }
    },
    [activeId],
  )

  const value = React.useMemo(
    () => ({
      mode,
      setMode,
      toggle,
      conversations,
      activeId,
      title,
      messages,
      draft: stream.draft,
      activity: stream.activity,
      pendingCall: stream.pendingCall,
      queue,
      enqueue,
      removeQueued,
      promoteQueued,
      sending,
      loading,
      error,
      notice,
      send,
      ask,
      stop,
      confirm,
      select,
      newChat,
      remove,
      rename,
      hasMoreConversations,
      loadingMoreConversations,
      loadMoreConversations,
      contextChips,
      suggestedChips,
      toggleChip,
      dismissChip,
      attachSelection,
      attachments,
      setAttachments,
      contextUsage: stream.contextUsage,
      modelSel,
      setModelSel,
      effort,
      setEffort,
      agentMode,
      setAgentMode,
      composer,
      setComposer,
      resubmit,
      editingId,
      startEdit,
      cancelEdit,
      failedTurn: failedTurn && failedTurn.conversationId === activeId ? failedTurn : null,
      retry,
    }),
    [
      mode,
      setMode,
      toggle,
      conversations,
      activeId,
      title,
      messages,
      stream.draft,
      stream.contextUsage,
      stream.activity,
      stream.pendingCall,
      queue,
      enqueue,
      removeQueued,
      promoteQueued,
      sending,
      loading,
      error,
      notice,
      send,
      ask,
      stop,
      confirm,
      select,
      newChat,
      remove,
      rename,
      hasMoreConversations,
      loadingMoreConversations,
      loadMoreConversations,
      contextChips,
      suggestedChips,
      toggleChip,
      dismissChip,
      attachSelection,
      attachments,
      setAttachments,
      modelSel,
      setModelSel,
      effort,
      setEffort,
      agentMode,
      setAgentMode,
      composer,
      resubmit,
      editingId,
      startEdit,
      cancelEdit,
      failedTurn,
      retry,
    ],
  )
  return <GradisContext.Provider value={value}>{children}<SelectionContext /></GradisContext.Provider>
}
