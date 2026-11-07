/* eslint-disable react/only-export-components -- the trace pieces ship together */
import * as React from "react"
import { Brain, ChevronRight, Loader2, XCircle } from "lucide-react"
import { cn } from "../../lib/utils"
import { friendlyToolData, toolActivity } from "../../lib/toolActivity"
import type { TaskLogEvent } from "../../lib/types"
import type { CitationIndex } from "../../lib/citations"
import { Markdown } from "../ui/MarkdownLazy"

/** One entry of a turn's ordered log: a run task's `log` and a chat turn's trace share it. */
export type TraceEvent = TaskLogEvent

function keyLabel(key: string) {
  return key.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase())
}

function Value({ value }: { value: unknown }) {
  if (value == null) return <span className="text-muted-foreground">None</span>
  if (Array.isArray(value)) {
    return (
      <ul className="space-y-2">
        {value.map((item, i) => (
          <li key={i} className="border-l border-border pl-3">
            <Value value={item} />
          </li>
        ))}
      </ul>
    )
  }
  if (typeof value === "object") {
    return (
      <dl className="space-y-2">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt className="font-medium text-muted-foreground">{keyLabel(key)}</dt>
            <dd className="mt-0.5 break-words">
              <Value value={item} />
            </dd>
          </div>
        ))}
      </dl>
    )
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>
  return <span className="whitespace-pre-wrap break-words">{String(value)}</span>
}

function ToolResult({ text }: { text?: string }) {
  if (!text) return <p className="text-muted-foreground">No result recorded.</p>
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return <p className="whitespace-pre-wrap break-words leading-relaxed">{text}</p>
  }
  return <Value value={value} />
}

export function ToolRow({ event, expanded, onToggle }: { event: TraceEvent; expanded: boolean; onToggle: () => void }) {
  const id = React.useId()
  const { label, icon: Icon } = toolActivity(event)
  const status = event.ok === false ? "Failed" : event.ok === true ? "Completed" : "Running"
  return (
    <div className="text-sm">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={id}
        className={cn("flex w-full cursor-pointer items-center text-label-tertiary gap-2.5 p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring bg-accent/40", !expanded && "hover:bg-accent/80")}
      >
        {event.ok === false ? (
          <XCircle aria-hidden className="size-4 shrink-0 text-destructive" />
        ) : event.ok === true ? (
          <Icon aria-hidden className="size-4 shrink-0 text-primary" />
        ) : (
          <Loader2 aria-hidden className="size-4 shrink-0 animate-spin text-muted-foreground" />
        )}
        <span className="sr-only">{status}: </span>
        <span className="min-w-0 flex-1 text-xs">
          <span className={cn("block font-medium truncate", event.ok == null && "shimmer-text")}>{label}</span>
        </span>
        <ChevronRight aria-hidden className={cn("size-4 shrink-0 text-label-tertiary transition-transform", expanded && "rotate-90")} />
      </button>
      <div id={id} hidden={!expanded} className="space-y-2 px-3 pb-3 pl-9 text-xs bg-accent/40">
        {expanded && <>
          <p className="font-medium text-muted-foreground">Parameters</p>
          <pre className="nice-scroll overflow-x-auto rounded-lg bg-muted p-2.5 font-mono">{friendlyToolData(event.input ?? {})}</pre>
          <p className="font-medium text-muted-foreground">Result</p>
          <div className="nice-scroll max-h-72 overflow-auto rounded-lg bg-muted/50 p-3"><ToolResult text={event.result_preview} /></div>
        </>}
      </div>
    </div>
  )
}

export function ToolGroup({ events, defaultOpen }: { events: TraceEvent[]; defaultOpen: boolean }) {
  // Null until the user picks. A live group opens once it holds more than
  // one call: with one, the header already says what it is doing.
  const [choice, setChoice] = React.useState<boolean | null>(null)
  const open = choice ?? (defaultOpen && events.length > 1)
  const [view, setView] = React.useState<number | null>(null)
  const failed = events.filter((e) => e.ok === false).length
  // The call still running: the header says what is happening right now.
  const running = [...events].reverse().find((e) => e.ok == null)
  // A finished group folds itself away; the user can open it again.
  const summary = toolActivity(running ?? events.at(-1) ?? {})
  const SummaryIcon = summary.icon
  const wasRunning = React.useRef(running !== undefined)
  React.useEffect(() => {
    if (wasRunning.current && !running) setChoice(false)
    wasRunning.current = running !== undefined
  }, [running])
  return (
    <div className="overflow-hidden space-y-2">
      <button
        type="button"
        onClick={() => setChoice(!open)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-2 text-left type-meta text-label-tertiary hover:text-label-tertiary"
      >
        {running ? (
          <Loader2 aria-hidden className="size-4 shrink-0 animate-spin" />
        ) : failed > 0 ? (
          <XCircle aria-hidden className="size-4 shrink-0 text-destructive" />
        ) : (
          <SummaryIcon aria-hidden className="size-4 shrink-0" />
        )}
        <span className={cn("block min-w-0 flex-1 font-medium truncate", running && "shimmer-text")}>{summary.label}</span>
        {events.length > 1 && <span className="shrink-0 text-xs">{events.length} actions</span>}
        {failed > 0 && <span className="shrink-0 text-xs text-critical">{failed} failed</span>}
        <ChevronRight className={cn("ml-2 size-4 shrink-0 transition-transform", open && "rotate-90")} />
      </button>
      {/* `relative` keeps rows' absolutely positioned `sr-only` status inside the scroller, or they stretch the document. */}
      {open && (
        <div className="nice-scroll relative rounded-xl bg-card max-h-80 divide-y divide-border/30 overflow-y-auto border-t border-border">
          {events.map((e, i) => (
            <ToolRow key={`${e.turn}-${e.tool}-${i}`} event={e} expanded={view === i} onToggle={() => setView(view === i ? null : i)} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Streams the latest lines while live; folds away once the model answers. */
function Thought({ text, live }: { text: string; live: boolean }) {
  const id = React.useId()
  // Null until the user picks: open while live, folded after.
  const [choice, setChoice] = React.useState<boolean | null>(null)
  const open = choice ?? live
  const body = React.useRef<HTMLDivElement>(null)
  React.useLayoutEffect(() => {
    if (live && body.current) body.current.scrollTop = body.current.scrollHeight
  }, [text, live])
  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => setChoice(!open)}
        aria-expanded={open}
        aria-controls={id}
        className="flex cursor-pointer items-center gap-2 text-left type-meta text-label-tertiary hover:text-label-tertiary"
      >
        <Brain aria-hidden className="size-4 shrink-0" />
        <span className={cn("font-medium", live && "shimmer-text")}>{live ? "Thinking" : "Thoughts"}</span>
        <ChevronRight aria-hidden className={cn("size-4 shrink-0 transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <div
          id={id}
          ref={body}
          className={cn(
            "ml-2 border-l-2 border-border pl-3.5 text-xs leading-relaxed whitespace-pre-wrap break-words text-muted-foreground",
            live
              ? "max-h-24 overflow-hidden [mask-image:linear-gradient(to_bottom,transparent,black_2.5rem)]"
              : "nice-scroll max-h-80 overflow-y-auto",
          )}
        >
          <Markdown className="opacity-50" text={text.trim()} />
        </div>
      )}
    </div>
  )
}

export type TraceSegment =
  | { kind: "thought"; event: TraceEvent }
  | { kind: "note"; event: TraceEvent }
  | { kind: "tools"; events: TraceEvent[] }

export function traceSegments(logs: TraceEvent[]): TraceSegment[] {
  const out: TraceSegment[] = []
  for (const e of logs) {
    if (e.kind === "turn") {
      if (e.thought?.trim()) out.push({ kind: "thought", event: e })
      if (e.note?.trim()) out.push({ kind: "note", event: e })
      continue
    }
    const tail = out.at(-1)
    if (tail?.kind === "tools") tail.events.push(e)
    else out.push({ kind: "tools", events: [e] })
  }
  return out
}

/** Work (thoughts, interim text, calls) vs the answer (text after the last call); with no calls it's all answer. */
export function splitAnswer(events: TraceEvent[]): { work: TraceEvent[]; answer: string } {
  let lastTool = -1
  events.forEach((e, i) => {
    if (e.kind !== "turn") lastTool = i
  })
  const work = events.slice(0, lastTool + 1)
  const answer: string[] = []
  for (const e of events.slice(lastTool + 1)) {
    // A final turn's reasoning is still work; only what it says is the answer.
    if (e.thought?.trim()) work.push({ ...e, note: "" })
    if (e.note?.trim()) answer.push(e.note.trim())
  }
  return { work, answer: answer.join("\n\n") }
}

/** Open while the model is still working; folded once it answers. */
function WorkGroup({
  events,
  working,
  answering,
  textClassName,
  citations,
}: {
  events: TraceEvent[]
  working: boolean
  answering: boolean
  textClassName?: string
  citations?: CitationIndex
}) {
  const id = React.useId()
  // Null until the user picks.
  const [choice, setChoice] = React.useState<boolean | null>(null)
  const live = working && !answering
  const open = choice ?? live
  const tools = events.filter((e) => e.kind !== "turn")
  const thought = events.some((e) => e.kind === "turn" && e.thought?.trim())
  const failed = tools.filter((e) => e.ok === false).length
  const running = [...tools].reverse().find((e) => e.ok == null)
  const last = events.at(-1)
  const current = running ? toolActivity(running) : null
  const label = live
    ? current?.label ?? (last?.kind === "turn" && last.thought?.trim() && !last.note?.trim() ? "Thinking" : "Working")
    : [thought && "Thought", tools.length > 0 && `${tools.length} ${tools.length === 1 ? "action" : "actions"}`]
        .filter(Boolean)
        .join(", ") || "Worked"
  const Icon = live ? Loader2 : failed > 0 ? XCircle : tools.length > 0 ? toolActivity(tools.at(-1) ?? {}).icon : Brain
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setChoice(!open)}
        aria-expanded={open}
        aria-controls={id}
        className="flex w-full cursor-pointer items-center gap-2 text-left type-meta text-label-tertiary"
      >
        <Icon aria-hidden className={cn("size-4 shrink-0", live && "animate-spin", !live && failed > 0 && "text-destructive")} />
        <span className={cn("block min-w-0 flex-1 truncate font-medium", live && "shimmer-text")}>{label}</span>
        {failed > 0 && <span className="shrink-0 text-xs text-critical">{failed} failed</span>}
        <ChevronRight aria-hidden className={cn("ml-2 size-4 shrink-0 transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <div id={id} className="ml-2 border-l-2 border-border pl-3.5">
          <AgentTrace
            events={events}
            working={live}
            textClassName={cn("text-muted-foreground", textClassName)}
            citations={citations}
          />
        </div>
      )}
    </div>
  )
}

/** `grouped` (the chat) puts the work in one disclosure and the answer under it. */
export function AgentTrace({
  events,
  working = false,
  grouped = false,
  className,
  textClassName,
  afterTools,
  citations,
}: {
  events: TraceEvent[]
  /** The group still running stays open, so the live calls are in view. */
  working?: boolean
  /** One disclosure for thoughts and calls, then the answer; runs keep them interleaved. */
  grouped?: boolean
  className?: string
  textClassName?: string
  /** Extra content under a tool group (e.g. the records it saved). */
  afterTools?: (tools: TraceEvent[]) => React.ReactNode
  citations?: CitationIndex
}) {
  if (grouped) {
    const { work, answer } = splitAnswer(events)
    return (
      <div className={cn("space-y-3", className)}>
        {work.length > 0 && (
          <WorkGroup
            events={work}
            working={working}
            answering={answer !== ""}
            textClassName={textClassName}
            citations={citations}
          />
        )}
        {answer && <Markdown text={answer} className={textClassName} citations={citations} />}
      </div>
    )
  }
  const parts = traceSegments(events)
  return (
    <div className={cn("space-y-2", className)}>
      {parts.map((part, i) =>
        part.kind === "thought" ? (
          <Thought key={`t-${i}-${part.event.turn}`} text={part.event.thought || ""} live={working && i === parts.length - 1} />
        ) : part.kind === "note" ? (
          <Markdown
            key={`n-${i}-${part.event.turn}`}
            text={part.event.note || ""}
            className={textClassName}
            citations={citations}
          />
        ) : (
          <div className="my-4" key={`g-${i}-${part.events[0]?.turn}`}>
            <ToolGroup events={part.events} defaultOpen={working && i === parts.length - 1} />
            {afterTools?.(part.events)}
          </div>
        ),
      )}
    </div>
  )
}
