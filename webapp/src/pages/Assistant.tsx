import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowUp, MessageCircle, MessagesSquare, Pencil, Plus, Square, Trash2 } from "lucide-react"
import { Button, Chip, EmptyState, Field, cn } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../components/ui/shadcn/sheet"
import {
  CHAT_PAGE, assistantHref, createChat, deleteChat, getChat, listChats, renameChat, stopTurn, streamTurn,
  type AssistantChat, type AssistantEvent, type AssistantMessage, type PendingCall, type ToolStep, type TurnRequest,
} from "../lib/assistant"
import { ApiError, apiMessage } from "../lib/api"
import { useAuth } from "../lib/auth"
import { useShellHeader } from "../components/layout/shellHeader"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

const STARTERS = ["What opportunities are closing soon?", "Find grants for startups", "What should I work on next?"]
const FOLLOW_UPS = ["Who can apply?", "What should I prepare?"]
const CHAT_FOLLOW_UPS = ["What's next on my to-do list?", "What are my upcoming deadlines?"]
const chatKey = (userId: string, id: string | undefined) => ["assistant", userId, "chat", id]
const chatsKey = (userId: string) => ["assistant", userId, "chats"]

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

  return (
    <div className="flex min-h-0 flex-1 flex-col">

      <div className="nice-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Messages" onScroll={(event) => {
        const { scrollHeight, scrollTop, clientHeight } = event.currentTarget
        followScroll.current = scrollHeight - scrollTop - clientHeight < 64
      }}>
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-4 py-6 sm:px-6" aria-live="polite">
          {chatId && thread.isPending && !active ? (
            <p className="text-callout text-ink-secondary" role="status">Loading chat</p>
          ) : chatId && thread.isError ? (
            <EmptyState title="Couldn't open this chat" description={apiMessage(thread.error)} error
              action={<Button variant="secondary" size="sm" onClick={() => selectChat()}>New chat</Button>} />
          ) : !visibleRows.length && !working ? (
            <EmptyState className="mt-[8vh]" title="What can I help you with?" description="Find opportunities, check deadlines, or plan your next application."
              action={<Prompts prompts={STARTERS} onPick={(prompt) => void send(prompt)} className="justify-center" />} />
          ) : null}

          {visibleRows.map((message) => message.role === "user"
            ? <UserBubble key={message.id} content={message.content} />
            : <AssistantReply key={message.id} message={message} />)}
          {visibleAnswer ? <AssistantReply message={visibleAnswer} /> : null}
          {active && !active.answer && !pending ? (
            <AssistantReply text={active.text} status={active.status} thinking={active.note} live />
          ) : null}
          {pending ? (
            <AssistantReply>
              <div className="space-y-3 rounded-md border border-separator bg-surface p-4">
                <p className="text-callout text-ink wrap-anywhere">{pending.summary}</p>
                {pending.note ? <p className="text-footnote text-ink-secondary">{pending.note}</p> : null}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="primary" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: true })}>Approve</Button>
                  <Button size="sm" variant="quiet" disabled={working} onClick={() => chatId && void start(chatId, { type: "confirm", call_id: pending.id, approved: false })}>Not now</Button>
                </div>
              </div>
            </AssistantReply>
          ) : null}
          {last?.role === "assistant" && !disabled ? (
            <Prompts className="pl-11" prompts={last.sources.some((source) => source.kind === "opportunity") ? FOLLOW_UPS : CHAT_FOLLOW_UPS}
              onPick={(prompt) => void send(prompt)} />
          ) : null}
          <div ref={end} />
        </div>
      </div>

      <form className="mx-auto w-full max-w-[760px] shrink-0 px-4 pb-4 sm:px-6 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]" onSubmit={(event) => { event.preventDefault(); void send(draft) }}>
        {replyError || (problem && !edit) ? <p role="alert" className="mb-2 text-footnote text-critical">{replyError || problem}</p> : null}
        <div className="flex items-end gap-2 rounded-lg border border-input-border bg-surface py-2.5 pr-2.5 pl-4 shadow-elevation-1 transition-[border-color,box-shadow] duration-150 focus-within:border-focus focus-within:shadow-[0_0_0_3px_var(--focus-soft)]">
          <textarea
            aria-label="Ask the Assistant"
            placeholder="Ask about opportunities, deadlines or your applications"
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-body text-ink outline-none [field-sizing:content] placeholder:text-ink-tertiary"
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

function UserBubble({ content }: { content: string }) {
  return (
    <div className="bl-enter flex justify-end">
      <p className="max-w-[85%] rounded-[20px_20px_6px_20px] bg-surface-sunk px-4 py-2.5 text-body whitespace-pre-wrap text-ink wrap-anywhere sm:max-w-[70%]">
        <span className="sr-only">You said </span>{content}
      </p>
    </div>
  )
}

function AssistantReply({ message, text, status, thinking, live, children }: {
  message?: AssistantMessage
  text?: string
  status?: string
  thinking?: string
  live?: boolean
  children?: React.ReactNode
}) {
  const content = message?.content || text
  return (
    <div className="bl-enter flex min-w-0 gap-3">
      <div className="flex min-w-0 flex-1 flex-col gap-2.5 pt-1">
        <span className="sr-only">Assistant said</span>
        {live && !content ? (
          <div className="flex flex-col gap-1" role="status">
            <span className="self-start text-callout font-medium">
              <span className="bl-shimmer">{status && !status.startsWith("Opening") ? status : "Thinking"}</span>
            </span>
            {thinking ? <p className="line-clamp-3 text-footnote text-ink-tertiary">{thinking}</p> : null}
          </div>
        ) : null}
        {content ? (
          <div className="text-body text-ink wrap-anywhere [&>*+*]:mt-3 [&_h1]:text-title-3 [&_h2]:text-title-3 [&_h3]:text-headline [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6 [&_li+li]:mt-1 [&_li>p+p]:mt-2 [&_a]:text-link [&_a]:underline [&_strong]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-separator [&_blockquote]:pl-4 [&_blockquote]:text-ink-secondary [&_pre]:overflow-x-auto [&_pre]:rounded-sm [&_pre]:bg-surface-sunk [&_pre]:p-3 [&_code]:font-mono [&_code]:text-[0.875em] [&_table]:w-full [&_table]:text-callout [&_th]:border-b [&_th]:border-separator [&_th]:p-2 [&_th]:text-left [&_td]:border-b [&_td]:border-separator [&_td]:p-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
              table: ({ children }) => <div className="overflow-x-auto"><table>{children}</table></div>,
            }}>{content}</ReactMarkdown>
          </div>
        ) : null}
        {children}
      </div>
    </div>
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
