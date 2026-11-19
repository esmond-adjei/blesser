import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowDown, ArrowUp, ArrowUpRight, Brain, Briefcase, Check, ChevronDown, CircleCheck, Copy, Loader2, MessageSquareText, CircleAlert, Database, FileText, FolderOpen, Globe, ListChecks, ListPlus,
  MessageCircle, MessagesSquare, Pencil, Plus, RotateCcw, Square, Trash2, Wrench,
} from "lucide-react"
import { Button, Chip, EmptyState, Field, cn } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../components/ui/shadcn/sheet"
import {
  CHAT_PAGE, activitySummary, assistantHref, createChat, deleteChat, getChat, isToolStep, listChats, renameChat,
  stopTurn, streamTurn,
  type AssistantChat, type AssistantEvent, type AssistantMessage, type AssistantSource, type AssistantThread, type PendingCall, type TraceEntry,
  type TurnRequest,
} from "../lib/assistant"
import { ApiError, apiMessage } from "../lib/api"
import { useAuth } from "../lib/auth"
import { useShellHeader } from "../components/layout/shellHeader"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import guideArt from "../assets/illustrations/guide.webp"
import { ChatSkeleton } from "../components/assistant/ChatSkeleton"

const STARTERS = ["What opportunities are closing soon?", "Find grants for startups", "What should I work on next?"]
const chatKey = (userId: string, id: string | undefined) => ["assistant", userId, "chat", id]
const chatsKey = (userId: string) => ["assistant", userId, "chats"]

const TOOL_ICONS: Record<string, typeof Wrench> = {
  search_catalog: Database,
  get_opportunity: FileText,
  list_applications: Briefcase,
  list_todos: ListChecks,
  read_apply_kit: FolderOpen,
  search_web: Globe,
  enable_changes: Pencil,
  track_opportunity: Plus,
  add_todo: ListPlus,
}

const TOOL_RUNNING: Record<string, string> = {
  search_catalog: "Searching the Blesser catalog",
  get_opportunity: "Checking an opportunity",
  list_applications: "Checking your applications",
  list_todos: "Checking your to-dos",
  read_apply_kit: "Reading your apply kit",
  search_web: "Searching the web",
  enable_changes: "Preparing a change",
  track_opportunity: "Preparing to track the opportunity",
  add_todo: "Preparing your to-do",
}

type ChatEdit = { type: "rename" | "delete"; chat: AssistantChat }

interface LiveReply {
  id: string
  type: TurnRequest["type"]
  status: string
  text: string
  trace: TraceEntry[]
  user: AssistantMessage | null
  answer: AssistantMessage | null
  pending: PendingCall | null
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
    case "confirm_required": return { ...reply, status: "", pending: event.call }
    default: return reply
  }
}

function useLiveReply(userId: string) {
  const cache = useQueryClient()
  const [reply, setReply] = useState<LiveReply | null>(null)
  const [error, setError] = useState<{ id: string; message: string } | null>(null)
  const connection = useRef<AbortController | null>(null)
  useEffect(() => () => connection.current?.abort(), [])

  const start = useCallback(async (id: string, turn: TurnRequest) => {
    connection.current?.abort()
    const controller = new AbortController()
    connection.current = controller
    setError(null)
    setReply({ id, type: turn.type, status: "Opening your reply…", text: "", trace: [], user: null, answer: null, pending: null })
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
            cache.invalidateQueries({ queryKey: ["opportunities", "tracked"] }),
            cache.invalidateQueries({ queryKey: ["applications"] }),
            cache.invalidateQueries({ queryKey: ["todos"] }),
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

export function Assistant() {
  const { user } = useAuth()
  return <AssistantWorkspace key={user?.id} userId={user?.id ?? ""} />
}

function AssistantWorkspace({ userId }: { userId: string }) {
  const { chatId } = useParams()
  const navigate = useNavigate()
  const cache = useQueryClient()
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
  const pending = active?.type === "confirm" ? null : active?.pending ?? thread.data?.pending_call

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
    if (followScroll.current) end.current?.scrollIntoView({ block: "nearest" })
    else measure()
  }, [measure, active?.status, active?.text, active?.trace.length, rows.length, pending?.id, chatId])

  function selectChat(id?: string) {
    navigate(id ? assistantHref(id) : "/assistant")
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
      await start(id, { type: "chat", content })
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
  const visibleRows = active?.user && !rows.some((row) => row.id === active.user?.id)
    ? [...rows, active.user]
    : rows
  const visibleAnswer = active?.answer && !visibleRows.some((row) => row.id === active.answer?.id) ? active.answer : null
  const working = !!active || !!thread.data?.running || creating
  const replyError = error?.id === chatId ? error?.message : null
  const disabled = working || !!pending || (!!chatId && thread.isError)

  const title = thread.data?.title || "Assistant"
  const header = useMemo(() => ({
    title,
    actions: (
      <>
        <Button size="sm" variant="quiet" icon={<MessagesSquare />} onClick={() => setHistoryOpen(true)}>Chats</Button>
        {chatId ? <Button size="sm" variant="quiet" icon={<Plus />} onClick={() => navigate("/assistant")}>New chat</Button> : null}
      </>
    ),
  }), [title, chatId, navigate])
  useShellHeader(header)

  const empty = !chatId && !visibleRows.length && !working
  const composer = (
      <form className={cn("mx-auto w-full max-w-[760px] shrink-0 px-4 sm:px-6", empty ? "" : "pb-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]")} onSubmit={(event) => { event.preventDefault(); void send(draft) }}>
        {replyError || (problem && !edit) ? (
          <p role="alert" className="mb-2 flex flex-wrap items-center gap-x-2 text-footnote text-critical">
            {replyError || problem}
            {replyError && !working ? <button type="button" onClick={retry} className="cursor-pointer font-semibold text-link hover:underline">Try again</button> : null}
          </p>
        ) : null}
        <div className="flex items-end gap-2 rounded-lg border border-input-border bg-surface py-2.5 pr-2.5 pl-4 shadow-elevation-1 transition-[border-color,box-shadow] duration-150">
          <textarea
            aria-label="Ask the Assistant"
            placeholder="Ask about opportunities, deadlines or your applications"
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
    <div className="flex min-h-0 flex-1 flex-col">

      {empty ? (
        <div className="nice-scroll flex min-h-0 flex-1 flex-col items-center justify-center gap-6 overflow-y-auto px-0 py-8">
          <div className="flex flex-col items-center px-4 text-center">
            <img src={guideArt} alt="" width={622} height={480} className="bl-pop mb-5 h-28 w-auto sm:h-36" />
            <h2 className="type-title-1 text-ink">What can I help you with?</h2>
            <p className="mt-1.5 text-callout text-ink-secondary">Find opportunities, check deadlines, or plan your next application.</p>
          </div>
          {composer}
          <Prompts prompts={STARTERS} onPick={(prompt) => void send(prompt)} className="justify-center px-4" />
        </div>
      ) : null}
      <div hidden={empty} className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scroller} className="nice-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Messages" onScroll={measure}>
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-4 py-6 sm:px-6" aria-live="polite">
          {chatId && thread.isPending && !active ? (
            <ChatSkeleton />
          ) : chatId && thread.isError ? (
            <EmptyState title="Couldn't open this chat" description={apiMessage(thread.error)} error
              action={<Button variant="secondary" size="sm" onClick={() => selectChat()}>New chat</Button>} />
          ) : null}

          {visibleRows.map((message, index) => message.role === "user"
            ? <UserBubble key={message.id} content={message.content} />
            : <AssistantReply key={message.id} message={message}
                onRetry={index === visibleRows.length - 1 && !visibleAnswer && !working && !pending ? retry : undefined} />)}
          {visibleAnswer ? <AssistantReply message={visibleAnswer} /> : null}
          {active && !active.answer && !pending ? (
            <AssistantReply text={active.text} status={active.status} entries={active.trace} live />
          ) : null}
          {pending ? (
            <AssistantReply entries={pending.trace}>
              <div className="space-y-3 rounded-md border border-separator bg-surface p-4">
                <p className="text-callout text-ink wrap-anywhere">{pending.summary}</p>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="primary" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: true })}>Approve</Button>
                  <Button size="sm" variant="quiet" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: false })}>Not now</Button>
                </div>
              </div>
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

const PREVIEW_LINKS: Partial<Record<AssistantSource["kind"], (id: string) => string>> = {
  application: (id) => `/applications/${encodeURIComponent(id)}`,
  todo: (id) => `/calendar?todo=${encodeURIComponent(id)}`,
}

/** A record the turn created, opening its detail page. */
function RecordPreview({ source }: { source: AssistantSource }) {
  const href = PREVIEW_LINKS[source.kind]?.(source.id)
  const Icon = source.kind === "todo" ? ListChecks : Briefcase
  const body = (
    <>
      <span className={cn("grid size-10 shrink-0 place-items-center rounded-md", source.kind === "todo" ? "bg-sun-soft text-ink" : "bg-forest-soft/40 text-link")}>
        <Icon className="size-[18px]" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-callout font-semibold text-ink">{source.title}</span>
        {source.detail ? <span className="block truncate text-footnote text-ink-secondary">{source.detail}</span> : null}
      </span>
      {href ? <ArrowUpRight className="size-4 shrink-0 text-ink-tertiary transition-transform group-hover/preview:translate-x-0.5 group-hover/preview:-translate-y-0.5 group-hover/preview:text-ink" aria-hidden="true" /> : null}
    </>
  )
  const card = "group/preview bl-pop flex max-w-md items-center gap-3 rounded-lg border border-separator bg-surface p-3 shadow-elevation-1"
  return href ? (
    <Link to={href} className={cn(card, "transition-[box-shadow,border-color] hover:border-input-border-hover hover:shadow-elevation-2 focus-visible:outline-2 focus-visible:outline-focus")}>{body}</Link>
  ) : <div className={card}>{body}</div>
}

// Hover reveals turn actions on pointers; touch screens always show them.
const TURN_ACTIONS = "flex opacity-0 transition-opacity duration-150 group-hover/turn:opacity-100 group-focus-within/turn:opacity-100 [@media(hover:none)]:opacity-100"

function UserBubble({ content }: { content: string }) {
  return (
    <div className="group/turn bl-enter flex flex-col items-end gap-1">
      <p className="max-w-[85%] rounded-[20px_20px_6px_20px] bg-surface-sunk px-4 py-2.5 text-body whitespace-pre-wrap text-ink wrap-anywhere sm:max-w-[70%]">
        <span className="sr-only">You said </span>{content}
      </p>
      <div className={TURN_ACTIONS}><CopyButton text={content} label="Copy message" /></div>
    </div>
  )
}

function AssistantReply({ message, text, status, entries = [], live, onRetry, children }: {
  message?: AssistantMessage
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
  const previews = message?.sources.filter((source) => source.preview) ?? []
  return (
    <div className="group/turn bl-enter flex min-w-0 flex-col gap-3">
      <span className="sr-only">Assistant said</span>
      {trace.length || working ? <AgentSteps entries={trace} live={!!working} status={status} /> : null}
      {content ? (
        <div className={cn(live && "bl-stream", "text-body text-ink wrap-anywhere [&>*+*]:mt-3 [&_h1]:text-title-3 [&_h2]:text-title-3 [&_h3]:text-headline [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6 [&_li+li]:mt-1 [&_li>p+p]:mt-2 [&_a]:text-link [&_a]:underline [&_strong]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-separator [&_blockquote]:pl-4 [&_blockquote]:text-ink-secondary [&_pre]:overflow-x-auto [&_pre]:rounded-sm [&_pre]:bg-surface-sunk [&_pre]:p-3 [&_code]:font-mono [&_code]:text-[0.875em] [&_table]:w-full [&_table]:text-callout [&_th]:border-b [&_th]:border-separator [&_th]:p-2 [&_th]:text-left [&_td]:border-b [&_td]:border-separator [&_td]:p-2")}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
            table: ({ children }) => <div className="overflow-x-auto"><table>{children}</table></div>,
          }}>{content}</ReactMarkdown>
        </div>
      ) : null}
      {previews.length ? <div className="flex flex-col gap-2">{previews.map((source) => <RecordPreview key={source.key} source={source} />)}</div> : null}
      {children}
      {content && !live ? (
        <div className={cn(TURN_ACTIONS, "-ml-1.5 -mt-1")}>
          <CopyButton text={content} label="Copy reply" />
          {onRetry ? <TurnAction label="Retry" onClick={onRetry}><RotateCcw className="size-3.5" aria-hidden="true" /></TurnAction> : null}
        </div>
      ) : null}
    </div>
  )
}

/** The agent's work for one turn: thoughts, notes and tool calls in the order they happened. */
function AgentSteps({ entries, live, status }: { entries: TraceEntry[]; live: boolean; status?: string }) {
  const [open, setOpen] = useState(live)
  const expanded = live || open
  const id = useId()
  const summary = activitySummary(entries) || "Worked on it"
  const now = status && !status.startsWith("Opening") ? status : "Thinking"
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={id}
        disabled={live}
        onClick={() => setOpen((v) => !v)}
        className="flex w-fit max-w-full cursor-pointer items-center gap-2 rounded-sm text-left text-callout font-medium text-ink-secondary transition-colors duration-150 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default disabled:hover:text-ink-secondary"
      >
        {live ? <Loader2 className="size-4 shrink-0 text-link motion-safe:animate-spin" aria-hidden="true" /> : <CircleCheck className="size-4 shrink-0 text-ink-tertiary" aria-hidden="true" />}
        <span className="min-w-0" role={live ? "status" : undefined}>{live ? <span className="bl-shimmer">{now}</span> : summary}</span>
        {live ? null : <ChevronDown aria-hidden="true" className={cn("size-4 shrink-0 transition-transform duration-150", !expanded && "-rotate-90")} />}
      </button>
      {expanded && entries.length ? (
        <ol id={id} aria-label="Steps" className="ml-2 flex flex-col gap-3 border-l border-separator py-1 pl-5">
          {entries.map((entry, index) => <AgentStep key={`${entry.kind ?? "tool"}-${index}`} entry={entry} />)}
        </ol>
      ) : null}
    </div>
  )
}

function StepIcon({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span aria-hidden="true" className={cn("absolute top-0 -left-[31px] grid size-5 place-items-center rounded-full bg-canvas text-ink-tertiary ring-4 ring-canvas", tone)}>
      {children}
    </span>
  )
}

function AgentStep({ entry }: { entry: TraceEntry }) {
  const [more, setMore] = useState(false)
  if (entry.kind === "thought") {
    const long = entry.text.length > 320
    return (
      <li className="relative min-w-0">
        <StepIcon><Brain className="size-3.5" /></StepIcon>
        <p className="text-caption font-medium text-ink-tertiary">Thought</p>
        <p className={cn("mt-0.5 text-footnote whitespace-pre-wrap text-ink-secondary wrap-anywhere", long && !more && "line-clamp-4")}>{entry.text}</p>
        {long ? (
          <button type="button" onClick={() => setMore((v) => !v)} className="mt-0.5 cursor-pointer text-caption font-semibold text-link hover:underline">
            {more ? "Show less" : "Show more"}
          </button>
        ) : null}
      </li>
    )
  }
  if (entry.kind === "commentary") {
    return (
      <li className="relative min-w-0">
        <StepIcon><MessageSquareText className="size-3.5" /></StepIcon>
        <p className="text-callout text-ink wrap-anywhere">{entry.text}</p>
      </li>
    )
  }
  const Icon = entry.ok ? TOOL_ICONS[entry.tool] ?? Wrench : CircleAlert
  return (
    <li className="relative min-w-0">
      <StepIcon tone={entry.ok ? undefined : "text-critical"}><Icon className="size-3.5" /></StepIcon>
      <p className={cn("text-callout wrap-anywhere", entry.ok ? "text-ink-secondary" : "text-critical")}>{entry.label}</p>
    </li>
  )
}

function ChatList({ rows, activeId, loading, error, next, fetching, onSelect, onEdit, onRetry }: {
  rows: AssistantChat[]
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
