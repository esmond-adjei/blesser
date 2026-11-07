import { AttachButton, AttachmentChips } from "./ChatAttachments"
import { filesOf, useChatAttach } from "./useChatAttach"
import { ChatControls } from "./ChatControls"
import { friendlyToolData, friendlyToolName, friendlyToolText } from "../../lib/toolActivity"
import * as React from "react"
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  ContactRound,
  Copy,
  FileText,
  FlaskConical,
  Globe,
  GraduationCap,
  ListChecks,
  Loader2,
  Mail,
  Minus,
  PanelRight,
  Pencil,
  PictureInPicture,
  RotateCw,
  ScrollText,
  Search,
  ShieldQuestion,
  Square,
  Expand,
  SquarePen,
  TextSelect,
  Trash2,
  X,
  Zap,
} from "lucide-react"
import { useNavigate } from "react-router-dom"
import { Mascot } from "page-mascot"
import { useGradis } from "./GradisProvider"
import { GradisSavedCards } from "./GradisCards"
import { Markdown, preloadMarkdown } from "../ui/MarkdownLazy"
import { ToolLogs } from "../cards/TaskCard"
import { AgentTrace } from "../cards/AgentTrace"
import { cn } from "../../lib/utils"
import { toastError } from "../../lib/toast"
import { useDismiss } from "../../lib/useDismiss"
import { RenameInput } from "../ui/RenameInput"
import { ChatMenu } from "./ChatMenu"
import { RowOverlay } from "../ui/row-menu"
import { formatAgo, formatDate } from "../../lib/format"
import { ModelDropup } from "../ui/ModelDropup"
import { Skeleton, SkeletonStack } from "../ui/feedback"
import { ModeDropup, MODE_INFO } from "./ModeDropup"
import {
  attachmentSummary,
  listConversations,
  type AgentMode,
  type GradisConversation,
  type GradisMessage,
  type SentContextChip,
} from "../../lib/gradis"
import {
  citationIndex,
  citationsToMarkdown,
  type CitationSource,
} from "../../lib/citations"

/** Composer grows with content to this height, then scrolls (max-h-32). */
const COMPOSER_MAX_H = 128
const SEARCH_DEBOUNCE_MS = 200
/** Keep the jump-to-latest button hidden while this close to the end. */
const LATEST_THRESHOLD_PX = 120
/** Within this of the bottom, the transcript follows new output. */
const STICK_PX = 16

const SUGGESTIONS = [
  { icon: Search, label: "Summarize my latest run" },
  { icon: ScrollText, label: "Find programs for my interests" },
  { icon: CalendarClock, label: "Check upcoming deadlines" },
  { icon: ListChecks, label: "Draft an outreach email" },
  { icon: FileText, label: "Review my CV for a target role" },
]

/** Copy as Markdown, falling back for non-secure contexts (plain-http dev). */
async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const el = document.createElement("textarea")
      el.value = text
      el.style.position = "fixed"
      el.style.opacity = "0"
      document.body.appendChild(el)
      el.select()
      const ok = document.execCommand("copy")
      el.remove()
      return ok
    } catch {
      return false
    }
  }
}

/** Icon-only row action, revealed on hover (always shown on touch widths). */
const rowAction =
  "flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-default disabled:opacity-40"

const ACTION_REVEAL =
  "mt-1 flex items-center gap-0.5 text-muted-foreground transition-opacity md:opacity-0 md:group-hover/msg:opacity-100 md:group-focus-within/msg:opacity-100"

function CopyButton({ text, label: idle = "Copy response as Markdown" }: { text: string; label?: string }) {
  const [copied, setCopied] = React.useState(false)
  const timer = React.useRef<number | null>(null)
  React.useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )
  async function copy() {
    if (!(await writeClipboard(text))) {
      toastError("Couldn't copy that")
      return
    }
    setCopied(true)
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(false), 1500)
  }
  const label = copied ? "Copied" : idle
  return (
    <button
      type="button"
      onClick={() => void copy()}
      data-tooltip={label}
      aria-label={label}
      className={rowAction}
    >
      {copied ? (
        <Check className="size-3.5 text-positive" aria-hidden />
      ) : (
        <Copy className="size-3.5" aria-hidden />
      )}
    </button>
  )
}

// One clock for every timestamp in the transcript: relative times move on
// each minute without a timer per message.
const minuteListeners = new Set<() => void>()
let minuteTimer: number | null = null
let minuteNow = Date.now()
function subscribeMinute(listener: () => void) {
  minuteListeners.add(listener)
  if (minuteTimer === null) {
    minuteTimer = window.setInterval(() => {
      minuteNow = Date.now()
      minuteListeners.forEach((l) => l())
    }, 60_000)
  }
  return () => {
    minuteListeners.delete(listener)
    if (minuteListeners.size === 0 && minuteTimer !== null) {
      window.clearInterval(minuteTimer)
      minuteTimer = null
    }
  }
}

function MessageTime({ at }: { at?: string | null }) {
  const now = React.useSyncExternalStore(subscribeMinute, () => minuteNow)
  if (!at) return null
  // A message stamped after the clock last ticked is "just now".
  const label = formatAgo(at, Math.max(now, Date.now()))
  return (
    <time dateTime={at} data-tooltip={formatDate(at)} className="px-1 text-xs tabular-nums">
      {label}
    </time>
  )
}

/** Every source the conversation has a key for: what replies cited and
 * what tool calls returned. A reply can cite a source an earlier turn
 * looked up, so the keys are shared across messages. */
function conversationSources(messages: GradisMessage[]): Record<string, CitationSource> {
  const out: Record<string, CitationSource> = {}
  for (const m of messages) {
    for (const s of m.sources ?? []) out[s.key] = s
    for (const e of [...(m.segments ?? []), ...(m.tools ?? [])]) {
      if (e.kind === "turn") continue
      for (const s of e.sources ?? []) out[s.key] = s
    }
  }
  return out
}

/** `onRegenerate` re-runs this reply's prompt; omitted while streaming. */
function AssistantRow({
  message,
  sources,
  onRegenerate,
  disabled,
}: {
  message: GradisMessage
  sources: Record<string, CitationSource>
  onRegenerate?: () => void
  disabled?: boolean
}) {
  const segments = message.segments ?? []
  const tools = message.tools ?? []
  const streaming = message.id === "streaming"
  // Numbered by first appearance in this reply, across its turn notes.
  const citations = React.useMemo(
    () => citationIndex(message.content, { ...sources, ...keyed(message.sources) }),
    [message.content, message.sources, sources],
  )
  const cardTools = segments.length > 0 ? segments : tools
  return (
    <div className="group/msg min-w-0 flex-1 space-y-2">
      {segments.length > 0 ? (
        <AgentTrace
          events={segments}
          working={streaming}
          grouped
          citations={citations}
        />
      ) : (
        <>
          {tools.length > 0 && <ToolLogs logs={tools} />}

          <Markdown text={message.content} citations={citations} />

        </>
      )}
      <GradisSavedCards tools={cardTools} />

      {!streaming && (
        <div className={ACTION_REVEAL}>
          <CopyButton text={citationsToMarkdown(message.content, citations)} />
          {onRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={disabled}
              data-tooltip="Regenerate response"
              aria-label="Regenerate response"
              className={rowAction}
            >
              <RotateCw className="size-3.5" aria-hidden />
            </button>
          )}
          {message.model && (
            <span className="truncate px-1 text-xs">
              {message.model}
            </span>
          )}
          <MessageTime at={message.created_at} />
        </div>
      )}
    </div>
  )
}

/** The composer's context chips a prompt went out with: what Gradis
 * was looking at when it answered. */
function SentContext({ chips }: { chips: SentContextChip[] }) {
  if (chips.length === 0) return null
  return (
    <ul aria-label="Sent with context" className="mb-1 flex flex-wrap justify-end gap-1">
      {chips.map((chip) => {
        const Icon = CHIP_ICONS[chip.key as keyof typeof CHIP_ICONS] ?? Globe
        return (
          <li
            key={chip.key}
            data-tooltip={chip.detail ? `${chip.label}: ${chip.detail}` : chip.label}
            className="inline-flex max-w-48 items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 type-caption text-muted-foreground"
          >
            <Icon className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{chip.detail || chip.label}</span>
          </li>
        )
      })}
    </ul>
  )
}

function UserRow({
  message,
  onEdit,
  disabled,
}: {
  message: GradisMessage
  onEdit: () => void
  disabled?: boolean
}) {
  return (
    <div className="group/msg flex justify-end">
      <div className="flex max-w-[85%] flex-col items-end">
        <SentContext chips={message.context ?? []} />
        <AttachmentChips items={message.attachments ?? []} className="mb-1 justify-end" />
        <div className="rounded-xl rounded-br-sm bg-accent px-3 py-2 text-foreground">
          {message.content}
        </div>
        <div className={ACTION_REVEAL}>
          <MessageTime at={message.created_at} />
          <CopyButton text={message.content} label="Copy prompt" />
          <button
            type="button"
            onClick={onEdit}
            disabled={disabled}
            data-tooltip="Edit prompt"
            aria-label="Edit prompt"
            className={rowAction}
          >
            <Pencil className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </div>
  )
}

function useCountdown(until: number) {
  const [now, setNow] = React.useState(() => Date.now())
  React.useEffect(() => {
    if (until <= Date.now()) return
    const t = window.setInterval(() => {
      setNow(Date.now())
      if (Date.now() >= until) window.clearInterval(t)
    }, 1000)
    return () => window.clearInterval(t)
  }, [until])
  return Math.max(0, Math.ceil((until - now) / 1000))
}

/** Failed-turn error with one-tap retry; repeated failures back off visibly. */
function FailedTurnRow() {
  const { failedTurn, retry, sending, error } = useGradis()
  const wait = useCountdown(failedTurn?.retryAt ?? 0)
  if (!failedTurn) return null
  const persistent = failedTurn.attempts >= 3
  return (
    <div role="alert" className="flex items-start gap-2 text-sm">
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-foreground">
          {persistent ? "Gradis is still having trouble." : "Gradis couldn't finish that reply."}
        </p>
        {error && <p className="mt-0.5 type-caption">{error}</p>}
        {persistent && (
          <p className="mt-0.5 type-caption">
            Check your model in settings, or wait a moment before trying again.
          </p>
        )}
        <button
          type="button"
          onClick={() => void retry()}
          disabled={sending || wait > 0}
          className="mt-1.5 inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 text-xs font-medium hover:bg-accent disabled:cursor-default disabled:opacity-50"
        >
          <RotateCw className={cn("size-3.5", sending && "animate-spin")} aria-hidden />
          {wait > 0 ? `Retry in ${wait}s` : "Retry"}
        </button>
      </div>
    </div>
  )
}

function keyed(sources: CitationSource[] | undefined): Record<string, CitationSource> {
  return Object.fromEntries((sources ?? []).map((s) => [s.key, s]))
}

/** Where to start in the document editor: about the open document. */
const DOCUMENT_STARTERS = [
  "Tighten this whole document without losing any facts",
  "Check it for grammar, spelling and consistency",
  "What are its weakest parts, and how would you fix them?",
  "Make the verbs stronger and more specific",
]

function ChatWelcome({
  onPick,
  column,
  mode,
  embedded,
}: {
  onPick: (text: string) => void
  column?: string
  mode: AgentMode
  embedded?: boolean
}) {
  if (embedded)
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-4 text-center">
        <Mascot
          directions="/mascots/gradis-directions.webp"
          reactions="/mascots/gradis-reactions.webp"
          size={80}
          label="Gradis"
        />
        <h2 className="mt-3 text-base font-semibold">How can I help with this document?</h2>
        <p className="mt-1 type-caption">
          {MODE_INFO[mode].label} mode, {MODE_INFO[mode].hint}
        </p>
        <ul className="mt-4 w-full space-y-1.5 text-left">
          {DOCUMENT_STARTERS.map((text) => (
            <li key={text}>
              <button
                type="button"
                onClick={() => onPick(text)}
                className="w-full cursor-pointer rounded-lg border border-border bg-background px-3 py-2 text-left text-xs leading-snug text-label-secondary transition-colors duration-150 hover:border-ring/50 hover:text-foreground"
              >
                {text}
              </button>
            </li>
          ))}
        </ul>
      </div>
    )
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <Mascot
        directions="/mascots/gradis-directions.webp"
        reactions="/mascots/gradis-reactions.webp"
        size={120}
        label="Gradis"
      />
      <h2 className="mt-4 text-lg font-semibold">How can I help you today?</h2>
      <p className="mt-1 type-caption">
        {MODE_INFO[mode].label} mode, {MODE_INFO[mode].hint}
      </p>
      <SuggestionCarousel onPick={onPick} column={column} />
    </div>
  )
}

/** One swipeable suggestion row: native scroll with snap, arrow buttons, and edge fades. */
function SuggestionCarousel({ onPick, column }: { onPick: (text: string) => void; column?: string }) {
  const rowRef = React.useRef<HTMLUListElement>(null)
  const [edges, setEdges] = React.useState({ start: false, end: false })

  const measure = React.useCallback(() => {
    const el = rowRef.current
    if (!el) return
    setEdges({ start: el.scrollLeft > 4, end: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 })
  }, [])

  React.useLayoutEffect(() => {
    measure()
    const el = rowRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [measure])

  function page(direction: 1 | -1) {
    const el = rowRef.current
    if (!el) return
    el.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: "smooth" })
  }

  const fade = `linear-gradient(to right, ${edges.start ? "transparent" : "#000"}, #000 2rem, #000 calc(100% - 2rem), ${edges.end ? "transparent" : "#000"})`
  const arrow =
    "absolute top-1/2 z-10 flex size-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:text-foreground"

  return (
    <div className={cn("relative mt-5 w-full", column && cn(column, "mb-4 px-3"))}>
      <ul
        ref={rowRef}
        onScroll={measure}
        aria-label="Suggestions"
        className="scrollbar-hide flex snap-x snap-mandatory gap-2 overflow-x-auto scroll-smooth text-left"
        style={{ maskImage: fade, WebkitMaskImage: fade }}
      >
        {SUGGESTIONS.map((s) => (
          <li key={s.label} className={cn("flex shrink-0 snap-start", column ? "w-48" : "w-40")}>
            <button
              type="button"
              onClick={() => onPick(s.label)}
              className={cn(
                "flex w-full cursor-pointer flex-col items-start gap-2 rounded-lg border border-border bg-card p-3 text-left text-muted-foreground transition-colors hover:border-ring/40 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                column ? "text-sm" : "text-xs",
              )}
            >
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-label-secondary">
                <s.icon className="size-4" />
              </span>
              <span className="leading-snug">{s.label}</span>
            </button>
          </li>
        ))}
      </ul>
      {edges.start && (
        <button type="button" onClick={() => page(-1)} aria-label="Previous suggestions" className={cn(arrow, column ? "left-0" : "-left-3")}>
          <ChevronLeft className="size-4" />
        </button>
      )}
      {edges.end && (
        <button type="button" onClick={() => page(1)} aria-label="More suggestions" className={cn(arrow, column ? "right-0" : "-right-3")}>
          <ChevronRight className="size-4" />
        </button>
      )}
    </div>
  )
}

function ConfirmCard() {
  const { pendingCall, confirm, sending } = useGradis()
  const [showArgs, setShowArgs] = React.useState(false)
  if (!pendingCall) return null
  return (
    <div className="mx-4 mb-2 flex-none rounded-xl border border-ring/40 bg-muted/60 p-3">
      <p className="flex items-center gap-1.5 text-sm font-semibold">
        <ShieldQuestion className="size-4 text-ring" />
        Approval needed
      </p>
      <p className="mt-1 text-sm">{friendlyToolText(pendingCall.summary)}</p>
      <button
        type="button"
        onClick={() => setShowArgs((v) => !v)}
        className="mt-1 flex cursor-pointer items-center gap-1 type-caption hover:text-foreground"
      >
        {friendlyToolName(pendingCall.tool)}
        {showArgs ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button>
      {showArgs && (
        <pre className="nice-scroll mt-1 max-h-32 overflow-auto rounded-md bg-background p-2 text-xs leading-relaxed">
          {friendlyToolData(pendingCall.arguments)}
        </pre>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={sending}
          onClick={() => void confirm(true)}
          className="flex flex-1 cursor-pointer items-center justify-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <Check className="size-4" /> Approve
        </button>
        <button
          type="button"
          disabled={sending}
          onClick={() => void confirm(false)}
          className="flex flex-1 cursor-pointer items-center justify-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          <X className="size-4" /> Deny
        </button>
      </div>
    </div>
  )
}

function useConversationSearch(query: string) {
  const [hits, setHits] = React.useState<{ term: string; rows: GradisConversation[] } | null>(null)
  const [searching, setSearching] = React.useState(false)
  const term = query.trim()
  React.useEffect(() => {
    if (!term) return
    let cancelled = false
    const t = window.setTimeout(() => {
      setSearching(true)
      listConversations(term)
        .then((rows) => !cancelled && setHits({ term, rows }))
        .catch(() => !cancelled && setHits(null))
        .finally(() => !cancelled && setSearching(false))
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [term])
  // Only trust hits for the term on screen; older results never leak in.
  return {
    hits: term && hits?.term === term ? hits.rows : null,
    searching: term ? searching : false,
  }
}

function ConversationMenu({ onDone }: { onDone: () => void }) {
  const { conversations, activeId, select, newChat, remove, rename, error } = useGradis()
  const [query, setQuery] = React.useState("")
  const [editingId, setEditingId] = React.useState<string | null>(null)
  const { hits, searching } = useConversationSearch(query)
  // Typing filters titles; the debounced server search also matches message bodies.
  const q = query.trim().toLowerCase()
  const rows = !q
    ? conversations
    : (hits ?? conversations.filter((c) => c.title.toLowerCase().includes(q)))

  return (
    <div className="absolute left-0 top-full z-20 mt-1.5 w-72 overflow-hidden rounded-lg border border-border bg-popover shadow-lg">
      <div className="border-b border-border p-1.5">
        <div className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1.5">
          {searching ? (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
          ) : (
            <Search className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search titles and messages"
            aria-label="Search chats"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
      </div>
      <div className="nice-scroll max-h-72 space-y-0.5 overflow-y-auto p-1">
        {rows.length === 0 && (
          <p className="px-2 py-3 text-center type-caption">
            {searching ? "Searching…" : "No chats match."}
          </p>
        )}
        {rows.map((c) => {
          const active = c.id === activeId
          const failed = active && !!error
          return (
            <div
              key={c.id}
              className={cn(
                "relative group flex h-8 items-center rounded-md  hover:bg-accent",
                active && "bg-accent",
              )}
            >
              {editingId === c.id ? (
                <RenameInput
                  value={c.title}
                  label="Rename chat"
                  maxLength={80}
                  onDone={(next) => {
                    if (next?.trim()) void rename(c.id, next)
                    setEditingId(null)
                  }}
                  className="mx-1 h-7 w-full rounded border border-ring bg-background px-2 text-sm outline-none"
                />
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      void select(c.id)
                      onDone()
                    }}
                    data-tooltip={c.title}
                    aria-current={active || undefined}
                    className="relative flex h-full min-w-0 flex-1 cursor-pointer items-center gap-2 px-2 text-left text-sm"
                  >
                    <span className={cn("text-fade min-w-0 flex-1", active && "font-medium")}>
                      {c.title}
                    </span>
                    {failed ? (
                      <span
                        role="img"
                        aria-label="Last message failed"
                        data-tooltip="Last message failed"
                        className="absolute right-0 size-1.5 shrink-0 rounded-full bg-destructive"
                      />
                    ) : (
                      c.has_pending && (
                        <span
                          role="img"
                          aria-label="Waiting for your approval"
                          data-tooltip="Waiting for your approval"
                          className="size-1.5 shrink-0 rounded-full bg-ring"
                        />
                      )
                    )}
                  </button>
                  <RowOverlay className="rounded bg-background/90 shadow-xs">
                    <button
                      type="button"
                      data-tooltip="Rename chat"
                      aria-label={`Rename ${c.title}`}
                      onClick={() => setEditingId(c.id)}
                      className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      data-tooltip="Delete conversation"
                      aria-label={`Delete ${c.title}`}
                      onClick={() => void remove(c.id)}
                      className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </RowOverlay>
                </>
              )}
            </div>
          )
        })}
      </div>
      <button
        type="button"
        onClick={() => {
          void newChat()
          onDone()
        }}
        className="flex w-full cursor-pointer items-center gap-2 border-t border-border px-3 py-2 text-sm font-medium hover:bg-accent"
      >
        <SquarePen className="size-4" /> New chat
      </button>
    </div>
  )
}

/** Chat title; the dropdown lists chats, except on the full chat page. */
export function GradisTitleMenu({ className, isPage }: { className?: string; isPage?: boolean }) {
  const { title, activeId, rename } = useGradis()
  const [open, setOpen] = React.useState(false)
  const [renaming, setRenaming] = React.useState(false)
  const ref = React.useRef<HTMLDivElement>(null)

  useDismiss(open, ref, () => setOpen(false))

  const titleClass = cn(
    "flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 text-sm font-semibold",
    !isPage && "cursor-pointer hover:bg-accent",
    className,
  )

  if (renaming) {
    return (
      <RenameInput
        value={title}
        label="Rename chat"
        maxLength={80}
        onDone={(next) => {
          setRenaming(false)
          if (activeId && next?.trim() && next.trim() !== title) void rename(activeId, next)
        }}
        fitContent
        className="h-8 max-w-full rounded-md border border-ring bg-background px-2 text-sm outline-none"
      />
    )
  }

  return (
    <div ref={ref} className="relative flex min-w-0 items-center gap-0.5">
      {isPage ? (
        <div className={titleClass} data-tooltip={title}>
          <span className="truncate">{title}</span>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-haspopup="menu"
          aria-expanded={open}
          className={titleClass}
          data-tooltip="Gradis chats"
        >
          <span className="truncate">{title}</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        </button>
      )}
      {/* Only a saved chat has an id to rename or delete; it may be older
          than the loaded pages of the list, so it isn't looked up there. */}
      {activeId !== null && <ChatMenu variant="header" chat={{ id: activeId, title }} onRename={() => setRenaming(true)} />}
      {open && <ConversationMenu onDone={() => setOpen(false)} />}
    </div>
  )
}

export function GradisNewChatButton() {
  const { newChat } = useGradis()
  return (
    <button
      type="button"
      onClick={() => void newChat()}
      data-tooltip="Start a new chat"
      aria-label="Start a new chat"
      className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <SquarePen className="size-4" />
    </button>
  )
}

const CHIP_ICONS = {
  page: Globe,
  run: FlaskConical,
  candidate: ContactRound,
  application: GraduationCap,
  draft: Mail,
  cv: FileText,
  selection: TextSelect,
} as const

/** "Send now" hands a prompt to the running turn; the cross drops it. */
function QueueChips() {
  const { queue, removeQueued, promoteQueued } = useGradis()
  if (queue.length === 0) return null
  return (
    <div
      aria-label="Queued prompts"
      className="scrollbar-hide flex gap-1 overflow-x-auto px-3 pt-2"
    >
      {queue.map((item) => (
        <span
          key={item.id}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-background py-0.5 pl-2 pr-1 text-xs text-muted-foreground"
        >
          {item.urgent ? (
            <Zap className="size-3 shrink-0 text-ring" aria-hidden />
          ) : (
            <Clock className="size-3 shrink-0" aria-hidden />
          )}
          <span className="max-w-40 truncate">{item.content}</span>
          <button
            type="button"
            onClick={() => void promoteQueued(item.id)}
            data-tooltip="Send to the running turn"
            aria-label="Send to the running turn"
            className="cursor-pointer rounded p-0.5 hover:bg-accent hover:text-foreground"
          >
            <ArrowUp className="size-3" />
          </button>
          <button
            type="button"
            onClick={() => void removeQueued(item.id)}
            data-tooltip="Remove from the queue"
            aria-label="Remove from the queue"
            className="cursor-pointer rounded p-0.5 hover:bg-accent hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
    </div>
  )
}

/** The page's context as chips: a suggestion until clicked, then sent
 * with the message. The × drops a suggestion for this page. */
function ContextChips() {
  const { suggestedChips, toggleChip, dismissChip } = useGradis()
  if (suggestedChips.length === 0) return null
  return (
    <div aria-label="Message context" className="scrollbar-hide flex gap-1 overflow-x-auto px-3 pt-2">
      {suggestedChips.map((chip) => {
        const Icon = CHIP_ICONS[chip.key as keyof typeof CHIP_ICONS] ?? Globe
        const name = `${chip.label}${chip.detail ? ` ${chip.detail}` : ""}`
        return (
          <span
            key={chip.key}
            className={cn(
              "inline-flex shrink-0 items-center rounded-full border type-caption",
              chip.added ? "border-tint/40 bg-tint-soft text-foreground" : "border-dashed border-border bg-background",
            )}
          >
            <button
              type="button"
              onClick={() => toggleChip(chip.key)}
              aria-pressed={chip.added}
              data-tooltip={chip.added ? `${name}. In context; click to take it out` : `${name}. Click to add to context`}
              className="inline-flex cursor-pointer items-center gap-1 rounded-l-full py-0.5 pl-2 pr-1 hover:text-foreground"
            >
              {chip.added ? <Check className="size-3 shrink-0" aria-hidden /> : <Icon className="size-3 shrink-0" aria-hidden />}
              <span className="max-w-32 truncate">{chip.detail ?? chip.label}</span>
            </button>
            <button
              type="button"
              onClick={() => dismissChip(chip.key)}
              aria-label={`Dismiss ${chip.label}`}
              className="cursor-pointer rounded-r-full py-0.5 pr-1.5 pl-0.5 hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </span>
        )
      })}
    </div>
  )
}

/** Shared conversation UI; `panel` is the floating/docked window, `page` the full chat page. */
export function GradisChat({
  onMinimize,
  cornerGrip,
  variant = "panel",
}: {
  onMinimize?: () => void
  cornerGrip?: boolean
  /** "embedded": inside another surface's panel (the document editor's
   * side panel), which owns closing it: no minimize or dock controls. */
  variant?: "panel" | "page" | "embedded"
}) {
  const {
    activeId,
    messages,
    draft,
    activity,
    sending,
    loading,
    error,
    notice,
    send,
    stop,
    mode,
    setMode,
    composer,
    setComposer,
    resubmit,
    editingId,
    startEdit,
    cancelEdit,
    pendingCall,
    failedTurn,
    modelSel,
    setModelSel,
    agentMode,
    setAgentMode,
    enqueue,
  } = useGradis()
  const navigate = useNavigate()
  const { attach, uploading: attaching, attachments, setAttachments } = useChatAttach()
  const [dropping, setDropping] = React.useState(false)
  const page = variant === "page"
  const embedded = variant === "embedded"
  // The agent is busy: the composer queues instead of sending.
  const busy = sending || pendingCall !== null
  const canAttach = !busy && !editingId
  const column = page ? "mx-auto w-full max-w-3xl" : ""
  const centered = page && !loading && messages.length === 0 && !draft
  const actionsDisabled = sending || loading || pendingCall !== null
  React.useEffect(preloadMarkdown, [])
  const sources = React.useMemo(
    () => conversationSources(draft ? [...messages, draft] : messages),
    [messages, draft],
  )
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const endRef = React.useRef<HTMLDivElement>(null)
  const composerRef = React.useRef<HTMLTextAreaElement>(null)
  const [showJumpToLatest, setShowJumpToLatest] = React.useState(false)

  const fitComposer = React.useCallback(() => {
    const el = composerRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, embedded ? 240 : COMPOSER_MAX_H)}px`
  }, [embedded])

  React.useLayoutEffect(fitComposer, [composer, fitComposer])

  // Refit when width changes: dock/float remounts mid-transition, and panels
  // are drag-resizable. Ignore height-only changes, which are our own writes.
  React.useLayoutEffect(() => {
    const el = composerRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    let lastWidth = el.clientWidth
    const ro = new ResizeObserver(() => {
      if (el.clientWidth === lastWidth) return
      lastWidth = el.clientWidth
      fitComposer()
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [fitComposer])

  // The transcript follows the latest message while the reader is at it:
  // content that grows (a streaming reply, Markdown that renders late, a
  // panel narrowing) keeps it pinned. Scrolling up lets go; sending a
  // prompt or opening a conversation pins it again.
  const stickRef = React.useRef(true)
  const [transcript, setTranscript] = React.useState<HTMLDivElement | null>(null)
  const pinToLatest = React.useCallback(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [])
  React.useLayoutEffect(() => {
    if (!transcript || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver(pinToLatest)
    ro.observe(transcript)
    return () => ro.disconnect()
  }, [transcript, pinToLatest])
  // A conversation opens at its latest message.
  React.useLayoutEffect(() => {
    stickRef.current = true
    pinToLatest()
  }, [activeId, pinToLatest])
  const lastMessage = messages.at(-1)
  React.useLayoutEffect(() => {
    if (lastMessage?.role === "user") stickRef.current = true
    pinToLatest()
  }, [lastMessage, draft, activity, pinToLatest])

  // Only the reader lets go, never a scroll the browser makes. Any upward move lets go at
  // once, even within STICK_PX: re-pinning on a smooth scroll's first frames snaps back down.
  const readerAt = React.useRef(0)
  const lastTop = React.useRef(0)
  const touchY = React.useRef(0)
  const reading = () => {
    readerAt.current = performance.now()
  }
  function followScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget
    const up = el.scrollTop < lastTop.current
    lastTop.current = el.scrollTop
    const byReader = performance.now() - readerAt.current < 1000
    if (byReader && up) stickRef.current = false
    else if (el.scrollHeight - el.scrollTop - el.clientHeight <= STICK_PX) stickRef.current = true
    else if (byReader) stickRef.current = false
  }

  // A sentinel at the end of the transcript says whether the reader is near
  // the latest message. IntersectionObserver also catches content growth and
  // panel resizes, without a scroll handler firing on every frame.
  React.useEffect(() => {
    const root = scrollRef.current
    const end = endRef.current
    if (!root || !end || typeof IntersectionObserver === "undefined") return
    const observer = new IntersectionObserver(
      ([entry]) => setShowJumpToLatest(!entry.isIntersecting),
      { root, rootMargin: `0px 0px ${LATEST_THRESHOLD_PX}px 0px` },
    )
    observer.observe(end)
    return () => observer.disconnect()
  }, [])

  function submit(text: string, urgent = false) {
    if ((!text.trim() && attachments.length === 0) || attaching) return
    const edit = editingId
    // Editing a prompt replaces its turn: it cannot wait in a queue.
    if (edit) {
      if (sending) return
      setComposer("")
      void resubmit(edit, text)
      return
    }
    // The agent is working (or waiting for an approval): the prompt waits
    // its turn instead of starting a second one.
    if (sending || pendingCall) {
      setComposer("")
      void enqueue(text, urgent)
      return
    }
    setComposer("")
    void send(text)
  }

  // Suggestion cards prefill the composer; only the user sends.
  function pickSuggestion(text: string) {
    if (editingId) cancelEdit()
    setComposer(text)
    composerRef.current?.focus()
  }

  // Regenerate re-sends the prompt that produced this reply, dropping it
  // and every later turn; the server replays the same text.
  function regenerate(index: number) {
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role !== "user") continue
      void resubmit(messages[i].id, messages[i].content)
      return
    }
  }

  function beginEdit(message: GradisMessage) {
    startEdit(message.id, message.content)
    composerRef.current?.focus()
  }

  function jumpToLatest() {
    const el = scrollRef.current
    if (!el) return
    // Follow from here on: content that streams in during the smooth
    // scroll would otherwise leave it short of the bottom.
    stickRef.current = true
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    el.scrollTo({ top: el.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" })
  }

  const sendButton = sending ? (
    <button
      type="button"
      onClick={stop}
      aria-label="Stop generating"
      data-tooltip="Stop the current response"
      className={cn("flex size-7 cursor-pointer items-center justify-center rounded-full bg-destructive text-destructive-foreground", !embedded && "ml-2")}
    >
      <Square className="size-3.5 fill-current" />
    </button>
  ) : (
    <button
      type="button"
      onClick={() => submit(composer)}
      disabled={(!composer.trim() && attachments.length === 0) || pendingCall !== null || attaching}
      aria-label="Send"
      data-tooltip={pendingCall ? "Answer the approval first" : "Send your message to Gradis"}
      className={cn("flex size-7 cursor-pointer items-center justify-center rounded-full bg-primary text-primary-foreground disabled:cursor-default disabled:opacity-40", !embedded && "ml-2")}
    >
      <ArrowUp className="size-4" />
    </button>
  )

  return (
    <div className={cn("flex h-full min-h-0 flex-col", centered && "justify-center")}>
      {!page && (
      <div
        className={cn(
          "relative flex flex-none items-center gap-0.5 border-b border-border",
          embedded ? "h-10 pl-2 pr-2" : "h-12 pr-3",
          !embedded && (cornerGrip ? "pl-6" : "pl-3"),
        )}
      >
        <GradisTitleMenu className="max-w-44" isPage={page} />
        <GradisNewChatButton />

        <span className="ml-auto flex items-center">
          {!embedded && (<>
          <button
            type="button"
            onClick={onMinimize}
            data-tooltip="Minimize Gradis"
            aria-label="Minimize Gradis"
            className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Minus className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => setMode(mode === "docked" ? "floating" : "docked")}
            data-tooltip={mode === "docked" ? "Show as floating window" : "Dock to sidebar"}
            aria-label={mode === "docked" ? "Show as floating window" : "Dock to sidebar"}
            className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            {
              mode === "floating" ? <PanelRight className="size-4" /> : <PictureInPicture className="size-4" />
            }
          </button>
          </>)}

          <button
            type="button"
            onClick={() => {
              setMode("closed")
              navigate(activeId ? `/chat/${activeId}` : "/chat")
            }}
            data-tooltip="Open as a full page"
            aria-label="Open as a full page"
            className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Expand className="size-4" />
          </button>
        </span>
      </div>
      )}

      <div
        ref={scrollRef}
        onScroll={followScroll}
        onWheel={(e) => {
          reading()
          if (e.deltaY < 0) stickRef.current = false
        }}
        onTouchStart={(e) => {
          touchY.current = e.touches[0].clientY
        }}
        // A finger dragging down scrolls up: let go before the scroll lands,
        // so a token arriving mid-gesture cannot pull the transcript back.
        onTouchMove={(e) => {
          reading()
          const y = e.touches[0].clientY
          if (y > touchY.current) stickRef.current = false
          touchY.current = y
        }}
        onKeyDown={reading}
        // The scrollbar is the container itself under the pointer.
        onPointerDown={(e) => {
          if (e.target === e.currentTarget) reading()
        }}
        className={cn("nice-scroll scroll-fade-y flex min-h-0 flex-col overflow-y-auto", centered ? "flex-initial" : "flex-1")}
      >
        {loading ? (
          <div aria-label="Loading chats" aria-busy="true" className={cn("w-full space-y-5 px-4 py-6", column)}>
            <Skeleton className="ml-auto h-12 w-2/3 rounded-xl" />
            <SkeletonStack className="space-y-2" blocks={["h-4 w-3/4", "h-4 w-full", "h-4 w-2/3"]} />
            <Skeleton className="ml-auto h-12 w-1/2 rounded-xl" />
          </div>
        ) : messages.length === 0 && !draft ? (
          <ChatWelcome onPick={pickSuggestion} column={column} mode={agentMode} embedded={embedded} />
        ) : (
          <div
            ref={setTranscript}
            // Full screen reads at the base size; the dock, floating panel
            // and embedded chat are narrower, so a step down.
            className={cn("space-y-4 py-4", embedded ? "px-3" : "px-4", page ? "text-base" : "text-sm", column)}
          >
            {messages.map((m, index) =>
              m.role === "user" ? (
                <UserRow
                  key={m.id}
                  message={m}
                  disabled={actionsDisabled}
                  onEdit={() => beginEdit(m)}
                />
              ) : (
                <AssistantRow
                  key={m.id}
                  message={m}
                  sources={sources}
                  disabled={actionsDisabled}
                  onRegenerate={() => regenerate(index)}
                />
              ),
            )}
            {!sending && <FailedTurnRow />}
            {draft && <AssistantRow message={draft} sources={sources} />}
            {activity && (
              <span aria-hidden className="flex items-center gap-0.5">
                <span className="typing-dot size-1 rounded-full bg-current" />
                <span className="typing-dot size-1 rounded-full bg-current" />
                <span className="typing-dot size-1 rounded-full bg-current" />
              </span>
            )}
          </div>
        )}
        <div ref={endRef} aria-hidden className="h-px shrink-0" />
      </div>

      <div className={cn("pointer-events-none relative z-10 flex-none", column)}>
        {showJumpToLatest && !centered && !loading && (
          <button
            type="button"
            onClick={jumpToLatest}
            aria-label={sending ? "Gradis is writing. Scroll to latest message" : "Scroll to latest message"}
            data-tooltip="Scroll to latest"
            className="pointer-events-auto absolute bottom-2 left-1/2 flex size-8 -translate-x-1/2 cursor-pointer items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-md transition-colors hover:bg-accent hover:text-foreground"
          >
            {sending ? (
              // Still writing below: dots in turn instead of the arrow.
              <span aria-hidden className="flex items-center gap-0.5">
                <span className="typing-dot size-1 rounded-full bg-current" />
                <span className="typing-dot size-1 rounded-full bg-current" />
                <span className="typing-dot size-1 rounded-full bg-current" />
              </span>
            ) : (
              <ArrowDown className="size-4" aria-hidden />
            )}
          </button>
        )}
      </div>

      <div className={cn("flex-none", column)}>
        <ConfirmCard />
      </div>

      {error && !failedTurn && (
        <p role="alert" className={cn("flex-none px-4 pb-1 text-xs text-destructive", column)}>
          {error}
        </p>
      )}
      {notice && !error && (
        <p className={cn("flex-none px-4 pb-1 type-caption", column)}>{notice}</p>
      )}

      <div className={cn("flex-none p-3 pt-1", column, page && "pb-5")}>
        <div
          data-gradis-composer
          onDragOver={(e) => {
            if (!canAttach || !e.dataTransfer.types.includes("Files")) return
            e.preventDefault()
            setDropping(true)
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropping(false)
          }}
          onDrop={(e) => {
            setDropping(false)
            const files = filesOf(e.dataTransfer)
            if (!canAttach || files.length === 0) return
            e.preventDefault()
            void attach(files)
          }}
          className={cn(
            // A query container: in a narrow composer the controls under the
            // text drop their labels and keep their icons (`/composer`).
            "@container/composer rounded-lg border border-border bg-muted/60 focus-within:border-ring",
            dropping && "border-dashed border-primary bg-primary/5",
          )}
        >
          {editingId && (
            <div className="flex items-center gap-1.5 border-b border-border/60 px-3 py-1.5 type-caption">
              <Pencil className="size-3 shrink-0" aria-hidden />
              <span>Editing a sent prompt</span>
              <span className="hidden sm:inline">
               , later replies will be removed
              </span>
              <button
                type="button"
                onClick={cancelEdit}
                data-tooltip="Cancel edit"
                aria-label="Cancel edit"
                className="ml-auto cursor-pointer rounded p-0.5 hover:bg-accent hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}
          <ContextChips />
          <QueueChips />
          <AttachmentChips
            items={attachmentSummary(attachments)}
            disabled={attaching}
            onRemove={(i) => setAttachments((previous) => previous.filter((_, index) => index !== i))}
            className="px-3 pt-2"
          />
          <textarea
            ref={composerRef}
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onPaste={(e) => {
              // A pasted file or screenshot attaches; pasted text stays text.
              const files = filesOf(e.clipboardData)
              if (!canAttach || files.length === 0) return
              e.preventDefault()
              void attach(files)
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                // Ctrl/⌘-Enter hands the prompt to the running turn; a
                // plain Enter lets it wait its turn.
                submit(composer, e.metaKey || e.ctrlKey)
              } else if (e.key === "Escape" && editingId) {
                e.preventDefault()
                cancelEdit()
              }
            }}
            rows={embedded ? 3 : 2}
            placeholder={busy ? "Add a prompt for after this one" : embedded ? "Ask Gradis about this document" : "Ask Gradis"}
            aria-label="Ask Gradis"
            className={cn(
              "nice-scroll w-full resize-none bg-transparent px-3 pt-2.5 text-sm outline-none placeholder:text-muted-foreground",
              embedded ? "max-h-60 min-h-19 leading-relaxed" : "max-h-32",
            )}
          />
          {/* One row. In a narrow composer (the editor's panel) the menus
              show only their icons, the label in their tooltip; narrower
              still, the right side wraps, still in the box. */}
          <div className="flex flex-wrap items-center gap-x-1 gap-y-1.5 px-2 pb-2 @max-[24rem]/composer:gap-x-0.5">
            <AttachButton disabled={!canAttach} uploading={attaching} count={attachments.length} onFiles={(files) => void attach(files)} />
            <ModeDropup value={agentMode} onChange={setAgentMode} />
            <span className="ml-auto flex items-center gap-1.5 @max-[24rem]/composer:gap-0.5">
              <ChatControls />
              <ModelDropup value={modelSel} onChange={setModelSel} />
              {sendButton}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
