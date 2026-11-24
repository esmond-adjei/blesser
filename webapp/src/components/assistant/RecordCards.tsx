import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { utcMs } from "../../lib/format"
import { Award, Bookmark, Clock, Briefcase, FileText, FolderOpen, Globe, Link2, ListChecks, MessageSquareText, Radar, Settings2, UserRound } from "lucide-react"
import { cn, formatDay } from "@blesser/ui"
import { useQuery } from "@tanstack/react-query"
import * as api from "../../lib/api"
import type { AssistantSource } from "../../lib/assistant"

const RECORD_ICONS: Record<AssistantSource["kind"], typeof Briefcase> = {
  opportunity: Award,
  application: Briefcase,
  todo: ListChecks,
  project: FolderOpen,
  document: FileText,
  answer: MessageSquareText,
  web: Globe,
  scan: Radar,
  find: Award,
  site: Link2,
  saved_search: Bookmark,
  profile: UserRound,
  settings: Settings2,
  scan_limit: Clock,
}

function recordDetail(source: AssistantSource) {
  const opp = source.opportunity
  if (!opp) return source.detail
  const due = opp.rolling ? "Rolling" : opp.deadline_date ? `Due ${formatDay(opp.deadline_date)}` : ""
  return [opp.organization, due].filter(Boolean).join(", ")
}

const SHOWN_RECORDS = 10
const MAX_SINGLE_COLUMN = 3

function groupByKind(sources: AssistantSource[]) {
  const groups = new Map<AssistantSource["kind"], AssistantSource[]>()
  for (const source of sources) groups.set(source.kind, [...(groups.get(source.kind) ?? []), source])
  return [...groups.values()]
}

/** Records a turn cited or created; each opens a preview beside the chat, and web results open in a new tab. */
export function RecordCards({ sources: given, onOpen }: { sources: AssistantSource[]; onOpen: (source: AssistantSource) => void }) {
  const [all, setAll] = useState(false)
  const notices = given.filter((s) => s.kind === "scan_limit")
  const sources = given.filter((s) => s.kind !== "scan_limit")
  const shown = all ? sources : sources.slice(0, SHOWN_RECORDS)
  return (
    <div className="flex flex-col gap-2">
      {notices.map((notice) => <ScanLimitCard key={notice.key} notice={notice} />)}
      {groupByKind(shown).map((group) => (
        <ul key={group[0].kind} className={cn("grid gap-2", group.length > MAX_SINGLE_COLUMN && "@md/chat:grid-cols-2")} aria-label="Records">
          {group.map((source) => <li key={source.key} className="min-w-0"><RecordCard source={source} onOpen={onOpen} /></li>)}
        </ul>
      ))}
      {sources.length > SHOWN_RECORDS && !all ? (
        <button type="button" onClick={() => setAll(true)} className="cursor-pointer self-start text-footnote font-semibold text-link hover:underline">
          Show {sources.length - SHOWN_RECORDS} more
        </button>
      ) : null}
    </div>
  )
}

const SCAN_STATUS: Record<string, string> = {
  running: "Running", pending: "Queued", done: "Finished", error: "Stopped early", cancelled: "Stopped",
}

/** A scan's status as it is now, since the card was written when the scan started. */
function useScanDetail(source: AssistantSource) {
  const live = useQuery({
    queryKey: ["scan", source.id],
    queryFn: () => api.getScan(source.id),
    enabled: source.kind === "scan",
    refetchInterval: ({ state: { data } }) => (data && data.status !== "running" ? false : 5000),
  })
  if (!live.data) return source.detail
  const found = live.data.opportunities_found ?? live.data.opportunities_added
  const status = SCAN_STATUS[live.data.status] ?? source.detail
  return live.data.status === "running" || !found ? status : `${status}, ${found} found`
}

function RecordCard({ source, onOpen }: { source: AssistantSource; onOpen: (source: AssistantSource) => void }) {
  const Icon = RECORD_ICONS[source.kind]
  const scanDetail = useScanDetail(source)
  const detail = source.kind === "scan" ? scanDetail : recordDetail(source)
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

/** Out of scans: when the next one frees up, counting down live. */
function ScanLimitCard({ notice }: { notice: AssistantSource }) {
  const at = utcMs(notice.available_at)
  const [now, setNow] = useState(() => Date.now())
  const waiting = !Number.isNaN(at) && at > now
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(timer)
  }, [waiting])
  const minutes = Math.max(1, Math.ceil((at - now) / 60_000))
  const wait = minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ""}`
  const time = new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  const today = new Date(at).toDateString() === new Date(now).toDateString()
  return (
    <div role="status" className="flex min-w-0 items-start gap-3 rounded-lg border border-separator bg-surface p-3.5">
      <span className={cn("grid size-10 shrink-0 place-items-center rounded-md", waiting ? "bg-sun-soft text-ink" : "bg-forest-soft/40 text-link")}>
        <Clock className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-callout font-semibold text-ink">{waiting ? notice.title : "You can scan again"}</p>
        <p className="text-footnote text-ink-secondary">
          {waiting
            ? `Your next scan frees up ${today ? "" : "tomorrow "}at ${time}, in ${wait}.`
            : "You have room for another scan now."}
        </p>
        <p className="mt-0.5 text-caption text-ink-tertiary">{notice.detail}</p>
      </div>
      <Link to="/scans" className="shrink-0 self-center rounded-full px-3 py-1.5 text-footnote font-semibold text-link hover:bg-highlight focus-visible:outline-2 focus-visible:outline-focus">
        {waiting ? "View scans" : "Start a scan"}
      </Link>
    </div>
  )
}
