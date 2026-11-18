import { useCallback, useEffect, useRef, useState } from "react"
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowUp, ArrowUpRight, History, MessageCircle, Pencil, Plus, Square, Trash2 } from "lucide-react"
import { Button, Chip, Countdown, EmptyState, Field, Logo, Textarea, cn, daysUntil } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog"
import {
  CHAT_PAGE, assistantHref, createChat, deleteChat, getChat, listChats, renameChat, stopTurn, streamTurn,
  type AssistantChat, type AssistantEvent, type AssistantMessage, type AssistantSource, type PendingCall, type ToolStep, type TurnRequest,
} from "../lib/assistant"
import { ApiError, apiMessage } from "../lib/api"
import { useAuth } from "../lib/auth"
import { countdownFor, useTrackedOpportunities } from "../lib/opportunities"
import { Art, TrackButton } from "./Opportunities"

const STARTERS = ["What opportunities are closing soon?", "Find grants for startups", "What should I work on next?"]
const FOLLOW_UPS = ["Who can apply?", "What should I prepare?"]
const CHAT_FOLLOW_UPS = ["What's next on my to-do list?", "What are my upcoming deadlines?"]
const chatKey = (userId: string, id: string | undefined) => ["assistant", userId, "chat", id]
const chatsKey = (userId: string) => ["assistant", userId, "chats"]
const RECORD_LINKS = {
  application: "/applications",
  todo: "/todos",
  project: "/kit/projects",
  document: "/kit/documents",
  answer: "/kit/answers",
}

type ChatEdit = { type: "rename" | "delete"; chat: AssistantChat }

interface LiveReply {
  id: string
  type: TurnRequest["type"]
  status: string
  note: string
  text: string
  steps: ToolStep[]
  user: AssistantMessage | null
  answer: AssistantMessage | null
  pending: PendingCall | null
}

function updateReply(reply: LiveReply, event: AssistantEvent): LiveReply {
  switch (event.type) {
    case "status": return { ...reply, status: event.message }
    case "reasoning": return { ...reply, note: event.text }
    case "token": return { ...reply, status: "", text: reply.text + event.text }
    case "tool_start": return { ...reply, status: event.label }
    case "tool_result": return { ...reply, status: "", note: "", steps: [...reply.steps, event.step] }
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
    setReply({ id, type: turn.type, status: "Opening your reply…", note: "", text: "", steps: [], user: null, answer: null, pending: null })
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

  useEffect(() => {
    if (followScroll.current) end.current?.scrollIntoView({ block: "nearest" })
  }, [active?.status, active?.text, active?.steps.length, rows.length, pending?.id, chatId])

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
  const last = visibleRows.at(-1)
  const working = !!active || !!thread.data?.running || creating
  const replyError = error?.id === chatId ? error?.message : null
  const disabled = working || !!pending || (!!chatId && thread.isError)

  return (
    <div className="-mb-12 grid h-[calc(100dvh-4.75rem)] min-h-0 min-w-0 gap-5 md:h-[calc(100dvh-5.5rem)] lg:grid-cols-[minmax(12rem,15rem)_minmax(0,1fr)]">
      <aside className="hidden min-h-0 flex-col gap-3 border-r border-separator pr-4 pb-4 lg:flex" aria-label="Saved chats">
        <h2 className="text-headline text-ink">Saved chats</h2>
        {list}
      </aside>

      <section aria-label="Assistant chat" className="mx-auto flex min-h-0 w-full max-w-[760px] min-w-0 flex-col">
        <div className="flex min-w-0 shrink-0 items-center gap-2 pb-3 lg:hidden">
          <Button size="sm" variant="secondary" icon={<History />} onClick={() => setHistoryOpen(true)}>Saved chats</Button>
          {thread.data ? <p className="min-w-0 truncate text-callout text-ink-secondary">{thread.data.title}</p> : null}
        </div>
        <div className="nice-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Messages" onScroll={(event) => {
          const { scrollHeight, scrollTop, clientHeight } = event.currentTarget
          followScroll.current = scrollHeight - scrollTop - clientHeight < 64
        }}>
          {chatId && thread.isPending && !active ? (
            <p className="text-callout text-ink-secondary" role="status">Loading chat…</p>
          ) : chatId && thread.isError ? (
            <EmptyState title="Couldn't open this chat" description={apiMessage(thread.error)} error
              action={<Button variant="secondary" size="sm" onClick={() => selectChat()}>New chat</Button>} />
          ) : !visibleRows.length && !working ? (
            <EmptyState className="mt-8" title="What can I help you with?" description="Find opportunities, check deadlines, or plan your next application."
              action={<Prompts prompts={STARTERS} onPick={(prompt) => void send(prompt)} />} />
          ) : null}

          <div className="space-y-5 pb-4" aria-live="polite">
            {visibleRows.map((message) => message.role === "user" ? (
              <div key={message.id} className="flex justify-end">
                <p className="max-w-[88%] rounded-lg bg-surface-sunk px-4 py-2.5 text-body whitespace-pre-wrap text-ink wrap-anywhere">
                  <span className="sr-only">You said </span>{message.content}
                </p>
              </div>
            ) : <AssistantReply key={message.id} steps={message.trace} message={message} />)}
            {visibleAnswer ? <AssistantReply steps={visibleAnswer.trace} message={visibleAnswer} /> : null}
            {active && !active.answer && !pending ? (
              <AssistantReply steps={active.steps} text={active.text} status={active.status} note={active.note} />
            ) : null}
            {pending ? (
              <AssistantReply steps={pending.trace} note={pending.note}>
                <div className="space-y-3 rounded-lg bg-surface-sunk p-3">
                  <p className="text-callout text-ink wrap-anywhere">{pending.summary}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="primary" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: true })}>Approve</Button>
                    <Button size="sm" variant="quiet" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: false })}>Decline</Button>
                  </div>
                </div>
              </AssistantReply>
            ) : null}
            {last?.role === "assistant" && !disabled ? (
              <div className="pl-10">
                <Prompts prompts={last.sources.some((source) => source.kind === "opportunity") ? FOLLOW_UPS : CHAT_FOLLOW_UPS}
                  onPick={(prompt) => void send(prompt)} />
              </div>
            ) : null}
          </div>
          <div ref={end} />
        </div>

        <form className="shrink-0 space-y-2 border-t border-separator bg-canvas pt-3 pb-3" onSubmit={(event) => { event.preventDefault(); void send(draft) }}>
          {replyError || (problem && !edit) ? <p role="alert" className="text-footnote text-critical">{replyError || problem}</p> : null}
          <div className="flex items-end gap-2">
            <Textarea
              aria-label="Ask the Assistant"
              placeholder="Ask about an opportunity…"
              className="max-h-32 min-h-11 resize-none"
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
              <Button type="button" variant="secondary" iconOnly aria-label="Stop reply" icon={<Square />}
                onClick={() => void stopTurn(chatId).catch((err) => setProblem(apiMessage(err)))} />
            ) : (
              <Button type="submit" variant="primary" disabled={disabled || !draft.trim()} iconOnly aria-label="Send message" icon={<ArrowUp />} />
            )}
          </div>
        </form>
      </section>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        {historyOpen ? (
          <DialogContent className="max-lg:top-auto max-lg:bottom-0 max-lg:w-full max-lg:max-w-none max-lg:rounded-b-none" onClose={() => setHistoryOpen(false)}>
            <DialogHeader><DialogTitle>Saved chats</DialogTitle><DialogDescription>Pick up a conversation or start a new one.</DialogDescription></DialogHeader>
            <DialogBody>{list}</DialogBody>
          </DialogContent>
        ) : null}
      </Dialog>
      <Dialog open={!!edit} onOpenChange={(open) => { if (!open && !editing) setEdit(null) }}>
        {edit ? <EditChat key={edit.chat.id + edit.type} edit={edit} problem={problem} saving={editing} onClose={() => { if (!editing) setEdit(null) }}
          onSave={(title) => void saveEdit(title)} /> : null}
      </Dialog>
    </div>
  )
}

function Prompts({ prompts, onPick }: { prompts: string[]; onPick: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {prompts.map((prompt) => (
        <Chip key={prompt} className="h-auto min-h-8 max-w-full whitespace-normal" onClick={() => onPick(prompt)}>{prompt}</Chip>
      ))}
    </div>
  )
}

function AssistantReply({ steps, message, text, status, note, children }: {
  steps: ToolStep[]
  message?: AssistantMessage
  text?: string
  status?: string
  note?: string
  children?: React.ReactNode
}) {
  const notes = [...new Set([...steps.map((step) => step.note), note].filter(Boolean))]
  return (
    <div className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] items-start gap-2">
      <Logo variant="color" title="Assistant" />
      <div className="min-w-0 space-y-3">
        {steps.length ? (
          <div className="flex flex-wrap gap-1.5" aria-label="Tool steps">
            {steps.map((step, index) => <Chip className="h-auto min-h-6 max-w-full whitespace-normal" key={`${step.tool}-${index}`}>{step.label}</Chip>)}
          </div>
        ) : null}
        {notes.length ? (
          <details className="text-footnote text-ink-secondary">
            <summary className="cursor-pointer">How I checked</summary>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {notes.map((entry) => <li className="wrap-anywhere" key={entry}>{entry}</li>)}
            </ul>
          </details>
        ) : null}
        {status ? <p className="text-footnote text-ink-secondary" role="status">{status}</p> : null}
        {message?.content || text ? <p className="text-body whitespace-pre-wrap text-ink wrap-anywhere">{message?.content || text}</p> : null}
        {message?.sources.length ? <CitedRecords sources={message.sources} /> : null}
        {message && (message.cited_deadlines || message.sources.some(({ opportunity }) =>
          opportunity && (opportunity.deadline_date || opportunity.rolling || opportunity.deadline)
        )) ? (
          <p className="rounded-md bg-forest-soft p-3 text-footnote text-link">Confirm the details on the official page before you apply.</p>
        ) : null}
        {children}
      </div>
    </div>
  )
}

function CitedRecords({ sources }: { sources: AssistantSource[] }) {
  const tracked = useTrackedOpportunities()
  return (
    <ul className="space-y-2" aria-label="Cited records">
      {sources.map((source) => {
        const opp = source.opportunity
        if (opp) {
          const daysLeft = opp.deadline_date ? daysUntil(opp.deadline_date) : opp.days_left
          const countdown = countdownFor({ ...opp, days_left: daysLeft, is_open: !opp.closed && (daysLeft === null || daysLeft >= 0) })
          return (
            <li key={source.key} className="flex flex-wrap items-center gap-2 rounded-lg border border-separator bg-surface p-2.5">
              <Link to={`/opportunities/${encodeURIComponent(opp.slug || opp.id)}`}
                className="flex min-w-0 flex-[1_1_12rem] items-center gap-2 rounded-sm hover:bg-highlight">
                <Art opp={opp} shape="square" className="size-9 shrink-0 rounded-sm" />
                <span className="min-w-0">
                  <span className="block text-callout font-medium text-ink wrap-anywhere">{opp.title}</span>
                  {opp.organization ? <span className="block text-footnote text-ink-secondary wrap-anywhere">{opp.organization}</span> : null}
                </span>
              </Link>
              <Countdown {...countdown} variant="text" className="max-w-full whitespace-normal wrap-anywhere" />
              <TrackButton opp={opp} applicationId={tracked.data?.[opp.id]} />
            </li>
          )
        }
        const className = "flex min-w-0 items-center gap-2 rounded-md bg-surface-sunk px-3 py-2 text-callout text-link wrap-anywhere hover:bg-highlight"
        const content = <><span className="min-w-0 flex-1">{source.title}{source.detail ? <span className="block text-footnote text-ink-secondary">{source.detail}</span> : null}</span><ArrowUpRight className="size-4 shrink-0" aria-hidden="true" /></>
        if (source.kind === "web" && source.url) {
          return <li key={source.key}><a className={className} href={source.url} target="_blank" rel="noopener noreferrer">{content}</a></li>
        }
        if (source.kind === "web" || source.kind === "opportunity") return null
        const href = source.kind === "project" ? `${RECORD_LINKS.project}/${encodeURIComponent(source.id)}` : RECORD_LINKS[source.kind]
        return <li key={source.key}><Link className={className} to={href}>{content}</Link></li>
      })}
    </ul>
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
    <div className="nice-scroll min-h-0 space-y-2 overflow-y-auto">
      <Button size="sm" variant="secondary" icon={<Plus />} onClick={() => onSelect()}>New chat</Button>
      {loading ? <p className="text-footnote text-ink-secondary">Loading chats…</p> : null}
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
