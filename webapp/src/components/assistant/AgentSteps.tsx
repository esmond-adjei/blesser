import { useId, useLayoutEffect, useRef, useState } from "react"
import { Brain, CircleAlert, CircleCheck, ChevronDown, Database, FileText, FolderOpen, Globe, ListChecks, ListPlus, Loader2, MessageSquareText, Pencil, Plus, Trash2, Briefcase, Wrench } from "lucide-react"
import { cn } from "@blesser/ui"
import { activitySummary, type TraceEntry } from "../../lib/assistant"

const TOOL_ICONS: Record<string, typeof Wrench> = {
  search_catalog: Database,
  get_opportunity: FileText,
  list_applications: Briefcase,
  get_application: Briefcase,
  list_todos: ListChecks,
  read_apply_kit: FolderOpen,
  search_web: Globe,
  enable_changes: Pencil,
  track_opportunity: Plus,
  add_todo: ListPlus,
  ...Object.fromEntries(["update_profile", "update_project", "update_answer", "update_document", "update_todo"].map((name) => [name, Pencil])),
  ...Object.fromEntries(["add_project", "add_answer"].map((name) => [name, Plus])),
  ...Object.fromEntries(["delete_project", "delete_answer", "delete_document", "delete_todo", "delete_application"].map((name) => [name, Trash2])),
}

export function AgentSteps({ entries, live, status }: { entries: TraceEntry[]; live: boolean; status?: string }) {
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
  if (entry.kind === "thought") return <Thought text={entry.text} />
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

/** A thought, clamped to four lines. The toggle only appears when the text is actually cut off. */
function Thought({ text }: { text: string }) {
  const [more, setMore] = useState(false)
  const [clamped, setClamped] = useState(false)
  const id = useId()
  const body = useRef<HTMLParagraphElement>(null)
  useLayoutEffect(() => {
    const el = body.current
    if (!el || more) return
    const measure = () => setClamped(el.scrollHeight > el.clientHeight + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [more, text])
  return (
    <li className="relative min-w-0">
      <StepIcon><Brain className="size-3.5" /></StepIcon>
      <p className="text-caption font-medium text-ink-tertiary">Thought</p>
      <p id={id} ref={body} className={cn("mt-0.5 text-footnote whitespace-pre-wrap text-ink-secondary wrap-anywhere", !more && "line-clamp-4")}>{text}</p>
      {clamped ? (
        <button
          type="button"
          aria-expanded={more}
          aria-controls={id}
          onClick={() => setMore((v) => !v)}
          className="mt-0.5 cursor-pointer text-caption font-semibold text-link hover:underline"
        >
          {more ? "Show less" : "Show more"}
        </button>
      ) : null}
    </li>
  )
}
