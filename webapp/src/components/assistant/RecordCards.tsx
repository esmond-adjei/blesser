import { useState } from "react"
import { Award, Briefcase, FileText, FolderOpen, Globe, ListChecks, MessageSquareText } from "lucide-react"
import { cn, formatDay } from "@blesser/ui"
import type { AssistantSource } from "../../lib/assistant"

const RECORD_ICONS: Record<AssistantSource["kind"], typeof Briefcase> = {
  opportunity: Award,
  application: Briefcase,
  todo: ListChecks,
  project: FolderOpen,
  document: FileText,
  answer: MessageSquareText,
  web: Globe,
}

function recordDetail(source: AssistantSource) {
  const opp = source.opportunity
  if (!opp) return source.detail
  const due = opp.rolling ? "Rolling" : opp.deadline_date ? `Due ${formatDay(opp.deadline_date)}` : ""
  return [opp.organization, due].filter(Boolean).join(", ")
}

const SHOWN_RECORDS = 10

/** Records a turn cited or created; each opens a preview beside the chat, and web results open in a new tab. */
export function RecordCards({ sources, onOpen }: { sources: AssistantSource[]; onOpen: (source: AssistantSource) => void }) {
  const [all, setAll] = useState(false)
  const shown = all ? sources : sources.slice(0, SHOWN_RECORDS)
  return (
    <div className="flex flex-col gap-2">
      <ul className="grid gap-2 @md/chat:grid-cols-2" aria-label="Records">
        {shown.map((source) => <li key={source.key} className="min-w-0"><RecordCard source={source} onOpen={onOpen} /></li>)}
      </ul>
      {sources.length > SHOWN_RECORDS && !all ? (
        <button type="button" onClick={() => setAll(true)} className="cursor-pointer self-start text-footnote font-semibold text-link hover:underline">
          Show {sources.length - SHOWN_RECORDS} more
        </button>
      ) : null}
    </div>
  )
}

function RecordCard({ source, onOpen }: { source: AssistantSource; onOpen: (source: AssistantSource) => void }) {
  const Icon = RECORD_ICONS[source.kind]
  const detail = recordDetail(source)
  const body = (
    <>
      <span className={cn("grid size-10 shrink-0 place-items-center rounded-md", source.kind === "todo" ? "bg-sun-soft text-ink" : "bg-forest-soft/40 text-link")}>
        <Icon className="size-[18px]" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-callout font-semibold text-ink">{source.title}</span>
        {detail ? <span className="block truncate text-footnote text-ink-secondary">{detail}</span> : null}
      </span>
    </>
  )
  const card = "bl-pop flex h-full w-full items-center gap-3 rounded-lg border border-separator bg-surface p-3 text-left shadow-elevation-1 cursor-pointer transition-[box-shadow,border-color] hover:border-input-border-hover hover:shadow-elevation-2 focus-visible:outline-2 focus-visible:outline-focus"
  if (source.kind === "web") {
    return source.url
      ? <a href={source.url} target="_blank" rel="noreferrer noopener" className={card}>{body}</a>
      : <div className={cn(card, "cursor-default")}>{body}</div>
  }
  return <button type="button" onClick={() => onOpen(source)} className={card}>{body}</button>
}
