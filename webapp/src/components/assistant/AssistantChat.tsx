import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  ArrowDown, ArrowUp, Check, Copy, MessageCircle, MessagesSquare, Pencil, Plus, RotateCcw, Square, Trash2,
} from "lucide-react"
import { Button, Chip, EmptyState, Field, cn } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../ui/menu"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../ui/shadcn/sheet"
import {
  CHAT_PAGE, assistantHref, createChat, deleteChat, getChat, isToolStep, listChats, renameChat,
  stopTurn, streamTurn,
  type AssistantChat as ChatRow, type AssistantEvent, type AssistantMessage, type AssistantSource, type AssistantThread, type ContextChip, type PendingCall, type TraceEntry,
  type TurnRequest,
} from "../../lib/assistant"
import { ApiError, apiMessage } from "../../lib/api"
import { LINEAR_OK, springEasing } from "../../lib/motion"
import { useShellHeader } from "../layout/shellHeader"
import guideArt from "../../assets/illustrations/guide.webp"
import { ChatSkeleton } from "./ChatSkeleton"
import { AgentSteps } from "./AgentSteps"
import { Markdown } from "./Markdown"
import { ContextChips } from "./ContextChips"
import { usePageContext } from "./pageContextState"
import { PendingCard, QuestionnaireDialog } from "./Questionnaire"
import { RecordCards } from "./RecordCards"
import { useRecordPreview } from "./useRecordPreview"

const STARTERS = ["What opportunities are closing soon?", "Find grants for startups", "What should I work on next?"]
const chatKey = (userId: string, id: string | undefined) => ["assistant", userId, "chat", id]
const chatsKey = (userId: string) => ["assistant", userId, "chats"]
const MORPH_EASE = LINEAR_OK ? springEasing(0.9) : "cubic-bezier(0.2, 0.9, 0.25, 1.05)"


const TOOL_RUNNING: Record<string, string> = {
  search_catalog: "Searching the Blesser catalog",
  get_opportunity: "Checking an opportunity",
  list_applications: "Checking your applications",
  list_todos: "Checking your to-dos",
  read_apply_kit: "Reading your apply kit",
  search_web: "Searching the web",
  list_scans: "Checking your scans",
  get_scan: "Checking a scan",
  list_sources: "Checking your sources",
  ask_member: "Preparing a few questions",
  track_opportunity: "Preparing to track the opportunity",
  add_todo: "Preparing your to-do",
  update_profile: "Preparing a profile change",
  add_project: "Preparing a new project",
  update_project: "Preparing a project change",
  add_answer: "Preparing a saved answer",
  update_answer: "Preparing an answer change",
  update_document: "Preparing a document change",
  update_todo: "Preparing a to-do change",
  delete_project: "Preparing to delete a project",
  delete_answer: "Preparing to delete an answer",
  delete_document: "Preparing to delete a document",
  delete_todo: "Preparing to delete a to-do",
  delete_application: "Preparing to remove an application",
}

type ChatEdit = { type: "rename" | "delete"; chat: ChatRow }

interface LiveReply {
  id: string
  type: TurnRequest["type"]
  status: string
  text: string
  trace: TraceEntry[]
  user: AssistantMessage | null
  answer: AssistantMessage | null
  pending: PendingCall | null
  asked: AssistantMessage | null
}

function updateReply(reply: LiveReply, event: AssistantEvent): LiveReply {
  switch (event.type) {
    case "status": return { ...reply, status: event.message }
    case "reasoning": {
      const last = reply.trace.at(-1)
      return event.text && !(last?.kind === "thought" && last.text === event.text)
        ? { ...reply, trace: [...reply.trace, { kind: "thought", text: event.text }] }
        : reply
    }
    case "commentary": {
      const last = reply.trace.at(-1)
      return event.text && !(last && !isToolStep(last) && last.text === event.text)
        ? { ...reply, trace: [...reply.trace, { kind: "commentary", text: event.text }] }
        : reply
    }
    case "token": return { ...reply, status: "", text: reply.text + event.text }
    case "retract": return { ...reply, text: "" }
    case "tool_start": return { ...reply, status: TOOL_RUNNING[event.tool] ?? event.label }
    case "tool_result": return { ...reply, status: "", trace: [...reply.trace, event.step] }
    case "user_message": return { ...reply, user: event.message }
    case "message": return { ...reply, status: "", answer: event.message }
    case "confirm_required":
    case "questions_required": return { ...reply, status: "", pending: event.call }
    case "questions_answered": return { ...reply, asked: event.asked, user: event.message, trace: [] }
    default: return reply
  }
}

function useLiveReply(userId: string) {
  const cache = useQueryClient()
  const [reply, setReply] = useState<LiveReply | null>(null)
  const [error, setError] = useState<{ id: string; message: string } | null>(null)
  const connection = useRef<AbortController | null>(null)
  useEffect(() => () => connection.current?.abort(), [])

  const start = useCallback(async (id: string, turn: TurnRequest, trace: TraceEntry[] = []) => {
    connection.current?.abort()
    const controller = new AbortController()
    connection.current = controller
    setError(null)
    setReply({ id, type: turn.type, status: "Opening your reply…", text: "", trace, user: null, answer: null, pending: null, asked: null })
    try {
      await streamTurn(id, turn, (event) => {
        if (controller.signal.aborted) return
        if (event.type === "error") setError({ id, message: event.message })
        setReply((current) => current?.id === id ? updateReply(current, event) : current)
      }, controller.signal)
    } catch (err) {
      if (!controller.signal.aborted && !(turn.type === "live" && err instanceof ApiError && err.status === 404)) {
        setError({ id, message: apiMessage(err) })
      }
    } finally {
      if (!controller.signal.aborted) {
        await Promise.all([
          cache.invalidateQueries({ queryKey: chatKey(userId, id) }),
          cache.invalidateQueries({ queryKey: chatsKey(userId) }),
          ...(turn.type === "confirm" && turn.approved ? [
            cache.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "assistant" }),
          ] : []),
        ])
      }
      if (connection.current === controller) {
        connection.current = null
        setReply(null)
      }
    }
  }, [cache, userId])

  return { reply, error, start }
}

export type ChatVariant = "page" | "embedded"

export function AssistantChat({ userId, chatId, onChatChange, variant, actions }: {
  userId: string
  chatId?: string
  onChatChange: (id?: string) => void
  variant: ChatVariant
  actions?: React.ReactNode
}) {
  const cache = useQueryClient()
  const preview = useRecordPreview()
  const pageContext = usePageContext()
  const embedded = variant === "embedded"
  const thread = useQuery({
    queryKey: chatKey(userId, chatId),
    queryFn: () => getChat(chatId ?? ""),
    enabled: !!chatId,
    retry: (attempt, err) => !(err instanceof ApiError && err.status === 404) && attempt < 2,
    refetchInterval: (query) => query.state.data?.running ? 3000 : false,
  })
  const chats = useInfiniteQuery({
    queryKey: chatsKey(userId),
    queryFn: ({ pageParam }) => listChats(pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => last.length === CHAT_PAGE ? pages.flat().length : undefined,
  })
  const { reply, error, start } = useLiveReply(userId)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [edit, setEdit] = useState<ChatEdit | null>(null)
  const [draft, setDraft] = useState("")
  const [problem, setProblem] = useState("")
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  const submitLock = useRef(false)
  const followed = useRef<string | undefined>(undefined)
  const followScroll = useRef(true)
  const end = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const [farFromEnd, setFarFromEnd] = useState(false)
  const active = reply?.id === chatId ? reply : null
  const rows = thread.data?.messages ?? []
  const pending = active?.type === "confirm" || active?.type === "answer" ? null : active?.pending ?? thread.data?.pending_call
  const [closedQuestions, setClosedQuestions] = useState<string | null>(null)
  const questionsOpen = pending?.type === "questions" && closedQuestions !== pending.id

  useEffect(() => {
    if (!chatId || !thread.data?.running) {
      followed.current = undefined
      return
    }
    if (active || followed.current === chatId) return
    followed.current = chatId
    void start(chatId, { type: "live" })
  }, [active, chatId, start, thread.data?.running])

  useEffect(() => {
    followScroll.current = true
  }, [chatId])

  const measure = useCallback(() => {
    const el = scroller.current
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    followScroll.current = gap < 64
    setFarFromEnd(gap > Math.max(240, el.clientHeight / 2))
  }, [])

  useEffect(() => {
    if (!followScroll.current) {
      measure()
      return
    }
    end.current?.scrollIntoView({ block: "nearest" })
    // The turn's height settles over a spring; keep the latest line in view while it does.
    const until = performance.now() + 320
    let frame = 0
    const hold = () => {
      if (!followScroll.current || performance.now() > until) return
      end.current?.scrollIntoView({ block: "nearest" })
      frame = requestAnimationFrame(hold)
    }
    frame = requestAnimationFrame(hold)
    return () => cancelAnimationFrame(frame)
  }, [measure, active?.status, active?.text, active?.trace.length, rows.length, pending?.id, chatId])

  function selectChat(id?: string) {
    onChatChange(id)
    setDraft("")
    setProblem("")
    setHistoryOpen(false)
  }

  async function send(value: string) {
    const content = value.trim()
    if (!content || pending || active || thread.data?.running || submitLock.current) return
    submitLock.current = true
    followScroll.current = true
    setProblem("")
    try {
      let id = chatId
      if (!id) {
        setCreating(true)
        id = (await createChat()).id
        selectChat(id)
      }
      setDraft("")
      await start(id, { type: "chat", content, context: pageContext.take() })
    } catch (err) {
      setProblem(apiMessage(err))
      setDraft(content)
    } finally {
      setCreating(false)
      submitLock.current = false
    }
  }

  function retry() {
    if (!chatId || pending || working) return
    followScroll.current = true
    setProblem("")
    cache.setQueryData<AssistantThread>(chatKey(userId, chatId), (data) => {
      if (!data) return data
      const last = data.messages.findLastIndex((row) => row.role === "user")
      return last < 0 ? data : { ...data, messages: data.messages.slice(0, last + 1) }
    })
    void start(chatId, { type: "retry" })
  }

  async function saveEdit(title: string) {
    if (!edit) return
    setEditing(true)
    setProblem("")
    try {
      if (edit.type === "rename") {
        await renameChat(edit.chat.id, title)
        void cache.invalidateQueries({ queryKey: chatKey(userId, edit.chat.id) })
      } else {
        await deleteChat(edit.chat.id)
        if (edit.chat.id === chatId) selectChat()
        cache.removeQueries({ queryKey: chatKey(userId, edit.chat.id) })
      }
      setEdit(null)
      void cache.invalidateQueries({ queryKey: chatsKey(userId) })
    } catch (err) {
      setProblem(apiMessage(err))
    } finally {
      setEditing(false)
    }
  }

  const list = (
    <ChatList
      rows={[...new Map(chats.data?.pages.flat().map((chat) => [chat.id, chat])).values()]}
      activeId={chatId}
      loading={chats.isPending}
      error={chats.isError}
      next={chats.hasNextPage ? () => void chats.fetchNextPage() : undefined}
      fetching={chats.isFetchingNextPage}
      onSelect={selectChat}
      onEdit={(value) => { setProblem(""); setHistoryOpen(false); setEdit(value) }}
      onRetry={() => void chats.refetch()}
    />
  )
  const liveRows = [active?.asked, active?.user].filter((row): row is AssistantMessage => !!row && !rows.some((r) => r.id === row.id))
  const visibleRows = liveRows.length ? [...rows, ...liveRows] : rows
  const visibleAnswer = active?.answer && !visibleRows.some((row) => row.id === active.answer?.id) ? active.answer : null
  const working = !!active || !!thread.data?.running || creating
  const replyError = error?.id === chatId ? error?.message : null
  const disabled = working || !!pending || (!!chatId && thread.isError)

  const title = thread.data?.title || "Assistant"
  const selectRef = useRef(selectChat)
  useEffect(() => { selectRef.current = selectChat })
  const chatButtons = useMemo(() => (
    <>
      <Button size="sm" variant="quiet" icon={<MessagesSquare />} onClick={() => setHistoryOpen((open) => !open)}>
        <span className={embedded ? "sr-only" : "max-sm:sr-only"}>Chats</span>
      </Button>
      {chatId ? <Button size="sm" variant="quiet" icon={<Plus />} onClick={() => selectRef.current()}><span className={embedded ? "sr-only" : "max-sm:sr-only"}>New chat</span></Button> : null}
    </>
  ), [embedded, chatId])
  const header = useMemo(() => (embedded ? null : { title, actions: chatButtons }), [embedded, title, chatButtons])
  useShellHeader(header)

  const empty = !chatId && !visibleRows.length && !working
  const composer = (
      <form className={cn("mx-auto w-full shrink-0 px-4", embedded ? "" : "max-w-[760px] sm:px-6", empty ? "" : "pb-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]")} onSubmit={(event) => { event.preventDefault(); void send(draft) }}>
        {replyError || (problem && !edit) ? (
          <p role="alert" className="mb-2 flex flex-wrap items-center gap-x-2 text-footnote text-critical">
            {replyError || problem}
            {replyError && !working ? <button type="button" onClick={retry} className="cursor-pointer font-semibold text-link hover:underline">Try again</button> : null}
          </p>
        ) : null}
        <ContextChips />
        <div className="flex items-end gap-2 rounded-lg border border-input-border bg-surface py-2.5 pr-2.5 pl-4 shadow-elevation-1 transition-[border-color,box-shadow] duration-150">
          <textarea
            aria-label="Ask the Assistant"
            placeholder={embedded ? "Ask the Assistant" : "Ask about opportunities, deadlines or your applications"}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-body text-ink outline-none [field-sizing:content] placeholder:text-ink-tertiary/60"
            rows={1}
            maxLength={4000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                void send(draft)
              }
            }}
          />
          {working && chatId ? (
            <Button type="button" size="sm" variant="secondary" iconOnly aria-label="Stop reply" icon={<Square />} className="size-9"
              onClick={() => void stopTurn(chatId).catch((err) => setProblem(apiMessage(err)))} />
          ) : (
            <Button type="submit" size="sm" variant="primary" disabled={disabled || !draft.trim()} iconOnly aria-label="Send message" icon={<ArrowUp />} className="size-9" />
          )}
        </div>
      </form>
  )

  return (
    <div className="@container/chat relative flex min-h-0 flex-1 flex-col">
      {embedded ? (
        <header className="flex h-12 shrink-0 items-center gap-1 border-b border-separator px-3">
          <h2 className="min-w-0 flex-1 truncate text-callout font-semibold text-ink">{title}</h2>
          {chatButtons}
          {actions}
        </header>
      ) : null}
      {empty ? (
        <div className="nice-scroll flex min-h-0 flex-1 flex-col items-center justify-center gap-6 overflow-y-auto px-0 py-8">
          <div className="flex flex-col items-center px-4 text-center">
            <img src={guideArt} alt="" width={622} height={480} className={cn("bl-pop mb-5 w-auto", embedded ? "h-24" : "h-28 sm:h-36")} />
            <h2 className={cn("text-ink", embedded ? "text-title-3 font-semibold" : "type-title-1")}>What can I help you with?</h2>
            <p className="mt-1.5 text-callout text-ink-secondary">Find opportunities, check deadlines, or plan your next application.</p>
          </div>
          {composer}
          <Prompts prompts={STARTERS} onPick={(prompt) => void send(prompt)} className="justify-center px-4" />
        </div>
      ) : null}
      <div hidden={empty} className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scroller} className="nice-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Messages" onScroll={measure}>
        <div className={cn("mx-auto flex w-full flex-col gap-5 px-4 py-6", !embedded && "max-w-[760px] sm:px-6")} aria-live="polite">
          {chatId && thread.isPending && !active ? (
            <ChatSkeleton />
          ) : chatId && thread.isError ? (
            <EmptyState title="Couldn't open this chat" description={apiMessage(thread.error)} error
              action={<Button variant="secondary" size="sm" onClick={() => selectChat()}>New chat</Button>} />
          ) : null}

          {visibleRows.map((message, index) => message.role === "user"
            ? <UserBubble key={message.id} content={message.content} chips={message.chips} />
            : <AssistantReply key={message.id} message={message} onOpenRecord={preview.open}
                onRetry={index === visibleRows.length - 1 && !visibleAnswer && !working && !pending ? retry : undefined} />)}
          {visibleAnswer ? <AssistantReply message={visibleAnswer} onOpenRecord={preview.open} /> : null}
          {active && !active.answer && !pending ? (
            <AssistantReply text={active.text} status={active.status} entries={active.trace} live onOpenRecord={preview.open} />
          ) : null}
          {pending ? (
            <AssistantReply entries={pending.trace} onOpenRecord={preview.open}>
              <PendingCard call={pending} working={working}
                onDecide={(approved) => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved }, pending.trace)}
                onOpenQuestions={() => setClosedQuestions(null)} />
            </AssistantReply>
          ) : null}
          <div ref={end} />
        </div>
      </div>
      {farFromEnd ? (
        <button
          type="button"
          aria-label="Jump to latest message"
          onClick={() => {
            followScroll.current = true
            scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" })
          }}
          className="bl-pop absolute bottom-3 left-1/2 grid size-9 -translate-x-1/2 cursor-pointer place-items-center rounded-full border border-separator bg-surface text-ink-secondary shadow-elevation-2 transition-colors hover:text-ink"
        >
          <ArrowDown className="size-4" aria-hidden="true" />
        </button>
      ) : null}
      </div>

      {empty ? null : composer}

      {embedded ? (
        historyOpen ? (
          <div className="bl-appear absolute inset-x-0 top-12 bottom-0 z-10 flex flex-col gap-3 bg-surface p-3">
            <Button size="sm" variant="secondary" icon={<Plus />} className="self-start" onClick={() => selectChat()}>New chat</Button>
            {list}
          </div>
        ) : null
      ) : (
        <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
          <SheetContent side="right" className="w-full gap-0 sm:max-w-sm">
            <SheetHeader className="border-b border-separator p-5 pr-14">
              <SheetTitle>Chats</SheetTitle>
              <SheetDescription>Pick up a conversation or start a new one.</SheetDescription>
            </SheetHeader>
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
              <Button size="sm" variant="secondary" icon={<Plus />} className="self-start" onClick={() => selectChat()}>New chat</Button>
              {list}
            </div>
          </SheetContent>
        </Sheet>
      )}
      {preview.node}
      <Dialog open={questionsOpen} onOpenChange={(open) => { if (!open && pending) setClosedQuestions(pending.id) }}>
        {pending?.type === "questions" ? (
          <QuestionnaireDialog key={pending.id} call={pending} sending={working}
            onClose={() => setClosedQuestions(pending.id)}
            onSkip={() => { setClosedQuestions(pending.id); if (chatId) void start(chatId, { type: "answer", call_id: pending.id }) }}
            onSend={(answers) => { setClosedQuestions(pending.id); if (chatId) void start(chatId, { type: "answer", call_id: pending.id, answers }) }} />
        ) : null}
      </Dialog>
      <Dialog open={!!edit} onOpenChange={(open) => { if (!open && !editing) setEdit(null) }}>
        {edit ? <EditChat key={edit.chat.id + edit.type} edit={edit} problem={problem} saving={editing} onClose={() => { if (!editing) setEdit(null) }}
          onSave={(title) => void saveEdit(title)} /> : null}
      </Dialog>
    </div>
  )
}

function Prompts({ prompts, onPick, className }: { prompts: string[]; onPick: (prompt: string) => void; className?: string }) {
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {prompts.map((prompt) => (
        <Chip key={prompt} className="h-auto min-h-8 max-w-full whitespace-normal" onClick={() => onPick(prompt)}>{prompt}</Chip>
      ))}
    </div>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(t)
  }, [copied])
  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      onClick={() => void navigator.clipboard.writeText(text).then(() => setCopied(true), () => undefined)}
      className="grid size-7 cursor-pointer place-items-center rounded-sm text-ink-tertiary transition-colors hover:bg-highlight hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
    >
      {copied ? <Check className="size-3.5 text-positive" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
      <span className="sr-only" aria-live="polite">{copied ? "Copied" : ""}</span>
    </button>
  )
}

function TurnAction({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
      className="grid size-7 cursor-pointer place-items-center rounded-sm text-ink-tertiary transition-colors hover:bg-highlight hover:text-ink focus-visible:outline-2 focus-visible:outline-focus">
      {children}
    </button>
  )
}


// Hover reveals turn actions on pointers; touch screens always show them.
const TURN_ACTIONS = "flex opacity-0 transition-opacity duration-150 group-hover/turn:opacity-100 group-focus-within/turn:opacity-100 [@media(hover:none)]:opacity-100"

/**
 * Keeps an explicit pixel height that follows its content, so a turn settles into
 * its new size as steps, thoughts and previews arrive instead of snapping taller.
 */
function Morph({ className, children }: { className?: string; children: React.ReactNode }) {
  const shell = useRef<HTMLDivElement>(null)
  const body = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const outer = shell.current
    const inner = body.current
    if (!outer || !inner) return
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)")
    let height = inner.offsetHeight
    let width = inner.offsetWidth
    let animation: Animation | null = null
    outer.style.height = `${height}px`
    const sync = () => {
      const next = inner.offsetHeight
      const nextWidth = inner.offsetWidth
      const from = animation ? outer.getBoundingClientRect().height : height
      // A width change reflows every line, so snap instead of springing the whole turn.
      const resized = nextWidth !== width
      height = next
      width = nextWidth
      if (next === from) return
      animation?.cancel()
      animation = null
      if (resized || reduce.matches) {
        outer.style.overflow = ""
        outer.style.height = `${next}px`
        return
      }
      outer.style.height = `${from}px`
      const morph = outer.animate(
        [{ height: `${from}px` }, { height: `${next}px` }],
        { duration: 260, easing: MORPH_EASE },
      )
      animation = morph
      outer.style.overflow = "clip"
      morph.onfinish = () => {
        if (animation !== morph) return
        animation = null
        outer.style.overflow = ""
        outer.style.height = ""
      }
    }
    const observer = new ResizeObserver(sync)
    observer.observe(inner)
    return () => {
      observer.disconnect()
      animation?.cancel()
    }
  }, [])
  return (
    <div ref={shell} className="min-w-0">
      <div ref={body} className={className}>{children}</div>
    </div>
  )
}

function UserBubble({ content, chips }: { content: string; chips?: ContextChip[] }) {
  return (
    <div className="group/turn bl-enter flex flex-col items-end gap-1">
      <p className="max-w-[85%] rounded-[20px_20px_6px_20px] bg-surface-sunk px-4 py-2.5 text-body whitespace-pre-wrap text-ink wrap-anywhere sm:max-w-[70%]">
        <span className="sr-only">You said </span>{content}
      </p>
      {chips?.length ? (
        <p className="max-w-[85%] truncate text-caption text-ink-tertiary sm:max-w-[70%]">
          <span className="sr-only">With context: </span>{chips.map((chip) => chip.detail ?? chip.label).join(", ")}
        </p>
      ) : null}
      <div className={TURN_ACTIONS}><CopyButton text={content} label="Copy message" /></div>
    </div>
  )
}

function AssistantReply({ message, text, status, entries = [], live, onRetry, onOpenRecord, children }: {
  message?: AssistantMessage
  onOpenRecord: (source: AssistantSource) => void
  onRetry?: () => void
  text?: string
  status?: string
  entries?: TraceEntry[]
  live?: boolean
  children?: React.ReactNode
}) {
  const content = message?.content || text
  const trace = message?.trace ?? entries
  const working = live && !content
  const records = message?.sources ?? []
  return (
    <div className="group/turn bl-enter min-w-0">
      <Morph className="flex min-w-0 flex-col gap-3">
        <span className="sr-only">Assistant said</span>
        {trace.length || working ? <AgentSteps entries={trace} live={!!working} status={status} /> : null}
        {content ? (
          <Markdown text={content} className={cn(live && "bl-stream")} />
        ) : null}
        {records.length ? <RecordCards sources={records} onOpen={onOpenRecord} /> : null}
        {children}
        {content && !live ? (
          <div className="-ml-1.5 -mt-1 flex">
            <CopyButton text={content} label="Copy reply" />
            {onRetry ? <TurnAction label="Retry" onClick={onRetry}><RotateCcw className="size-3.5" aria-hidden="true" /></TurnAction> : null}
          </div>
        ) : null}
      </Morph>
    </div>
  )
}


function ChatList({ rows, activeId, loading, error, next, fetching, onSelect, onEdit, onRetry }: {
  rows: ChatRow[]
  activeId?: string
  loading: boolean
  error: boolean
  next?: () => void
  fetching: boolean
  onSelect: (id?: string) => void
  onEdit: (value: ChatEdit) => void
  onRetry: () => void
}) {
  return (
    <div className="nice-scroll min-h-0 flex-1 space-y-2 overflow-y-auto">
      {loading ? <p className="text-footnote text-ink-secondary">Loading chats</p> : null}
      {error ? <p role="alert" className="text-footnote text-critical">Couldn't load chats. <button type="button" className="cursor-pointer underline" onClick={onRetry}>Try again</button></p> : null}
      {!loading && !error && !rows.length ? <p className="text-footnote text-ink-secondary">No saved chats yet.</p> : null}
      <ul className="space-y-1">
        {rows.map((chat) => {
          const actions: MenuAction[] = [
            { label: "Rename", icon: <Pencil />, onSelect: () => onEdit({ type: "rename", chat }) },
            { label: "Delete", icon: <Trash2 />, danger: true, disabled: chat.running, onSelect: () => onEdit({ type: "delete", chat }) },
          ]
          return (
            <ActionContextMenu key={chat.id} actions={actions}>
              <li className={cn("flex min-w-0 items-center rounded-md hover:bg-highlight", chat.id === activeId && "bg-forest-soft text-link")}>
                <Link to={assistantHref(chat.id)} aria-current={chat.id === activeId ? "page" : undefined}
                  onClick={(event) => {
                    if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
                      event.preventDefault()
                      onSelect(chat.id)
                    }
                  }}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-callout"
                  title={chat.title}>
                  <MessageCircle className="size-4 shrink-0" aria-hidden="true" />
                  <span className="truncate">{chat.title}</span>
                  {chat.pending_call ? <span className="size-1.5 shrink-0 rounded-full bg-sun" role="img" aria-label="Waiting for approval" /> : null}
                </Link>
                <ActionMenuButton actions={actions} label={`Actions for ${chat.title}`} className="shrink-0" />
              </li>
            </ActionContextMenu>
          )
        })}
      </ul>
      {next ? <Button size="sm" variant="quiet" disabled={fetching} onClick={next}>More chats</Button> : null}
    </div>
  )
}

function EditChat({ edit, problem, saving, onClose, onSave }: {
  edit: ChatEdit
  problem: string
  saving: boolean
  onClose: () => void
  onSave: (title: string) => void
}) {
  const [title, setTitle] = useState(edit.chat.title)
  const rename = edit.type === "rename"
  return (
    <DialogContent onClose={onClose}>
      <form onSubmit={(event) => { event.preventDefault(); onSave(title.trim()) }}>
        <DialogHeader>
          <DialogTitle>{rename ? "Rename chat" : "Delete chat?"}</DialogTitle>
          <DialogDescription>{rename ? "Give this conversation a name you’ll recognize." : "This will remove the conversation and all its messages."}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          {rename ? <Field label="Chat name" maxLength={80} required value={title} onChange={(event) => setTitle(event.target.value)} /> : null}
          {problem ? <p role="alert" className="text-footnote text-critical">{problem}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="quiet" type="button" disabled={saving} onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={rename ? "primary" : "danger"} disabled={saving || (rename && !title.trim())}>{rename ? "Save name" : "Delete chat"}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
