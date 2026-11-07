import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, ContactRound, FileStack, Library, FileText, FlaskConical, Landmark, Mail, MessageCircle, Search } from "lucide-react"
import * as api from "../../lib/api"
import { Dialog, DialogBody, DialogContent, DialogTitle } from "../ui/dialog"
import { PeekCard, PeekSummary } from "../ui/PeekCard"
import type { PreviewRef } from "../../lib/previewRoutes"
import { artifactPreview } from "../gradis/GradisArtifactPreview"
import { cn } from "../../lib/utils"

const GROUPS = [
  { kind: "run", label: "Runs", icon: FlaskConical },
  { kind: "school", label: "Schools", icon: Landmark },
  { kind: "program", label: "Programmes", icon: BookOpen },
  { kind: "professor", label: "Professors", icon: ContactRound },
  { kind: "candidate", label: "Matches", icon: ContactRound },
  { kind: "application", label: "Applications", icon: FileText },
  { kind: "draft", label: "Drafts", icon: Mail },
  { kind: "document", label: "Documents", icon: FileStack },
  { kind: "paper", label: "Papers", icon: Library },
  { kind: "chat", label: "Chats", icon: MessageCircle },
]

/** Lets the pointer cross the gap between the result list and the card. */
const PEEK_HIDE_MS = 300

export function GlobalSearch() {
  const [open, setOpen] = React.useState(false)
  // Not in the URL: the search box lives in the shell, so a query would follow every page.
  const [query, setQuery] = React.useState("")
  const [scope, setScope] = React.useState("all")
  const [term, setTerm] = React.useState("")
  const [active, setActive] = React.useState(0)
  const navigate = useNavigate()
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setTerm(query.trim())
    }, 200)
    return () => window.clearTimeout(timer)
  }, [query])
  React.useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(o => !o) }
    }
    document.addEventListener("keydown", key)
    return () => document.removeEventListener("keydown", key)
  }, [])
  const { data, isFetching, isError } = useQuery({
    queryKey: ["global-search", term], queryFn: () => api.globalSearch(term),
    enabled: open && term.length >= 2,
  })
  const groups = GROUPS.filter(g => scope === "all" || scope === g.kind)
    .map(g => ({ ...g, hits: (data?.items ?? []).filter(h => h.kind === g.kind && h.href) }))
  const hits = groups.flatMap(g => g.hits)
  React.useEffect(() => { setActive(0) }, [term, scope, open])
  const scroll = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => { scroll.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" }) }, [active])
  // The hover card waits a moment so sweeping down the list doesn't load every preview.
  const [peek, setPeek] = React.useState(false)
  const hidePeekTimer = React.useRef<number | null>(null)
  const cancelPeekHide = React.useCallback(() => {
    if (hidePeekTimer.current !== null) {
      window.clearTimeout(hidePeekTimer.current)
      hidePeekTimer.current = null
    }
  }, [])
  const showPeek = React.useCallback(() => {
    cancelPeekHide()
    setPeek(true)
  }, [cancelPeekHide])
  const hidePeekSoon = React.useCallback(() => {
    cancelPeekHide()
    hidePeekTimer.current = window.setTimeout(() => {
      hidePeekTimer.current = null
      setPeek(false)
    }, PEEK_HIDE_MS)
  }, [cancelPeekHide])
  const activeHit = peek ? hits[active] ?? null : null
  const [previewHit, setPreviewHit] = React.useState<api.SearchHit | null>(null)
  const activeKey = activeHit ? `${activeHit.kind}:${activeHit.id}` : ""
  React.useEffect(() => {
    const timer = window.setTimeout(() => setPreviewHit(activeHit), activeHit ? 250 : 100)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on identity, not the object
  }, [activeKey])
  React.useEffect(() => {
    if (!open) {
      cancelPeekHide()
      setPeek(false)
    }
  }, [open, term, cancelPeekHide])
  React.useEffect(() => () => cancelPeekHide(), [cancelPeekHide])
  function go(href: string) { setOpen(false); navigate(href) }
  return <>
    <button type="button" onClick={() => setOpen(true)} className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-sidebar-accent">
      <Search className="size-4" />Search<kbd className="g-kbd ml-auto">Ctrl K</kbd>
    </button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent onClose={() => setOpen(false)} className="flex h-[min(80dvh,640px)] max-w-xl flex-col overflow-hidden p-0">
        <DialogTitle className="sr-only">Search your workspace</DialogTitle>
        <div className="flex min-h-0 flex-1" onKeyDown={e => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); showPeek(); setActive(i => (i + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % Math.max(1, hits.length)) }
          if (e.key === "Enter" && hits[active]?.href) go(hits[active].href)
        }}>
          <div className="flex min-h-0 w-full flex-col">
            <input autoFocus aria-label="Search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search your workspace" className="bg-transparent py-4 pl-4 pr-12 text-base outline-none" />
            <div className="flex flex-wrap gap-1 border-y border-separator px-3 py-2">
              {[{ kind: "all", label: "All" }, ...GROUPS].map(g => <button key={g.kind} onClick={() => setScope(g.kind)} aria-pressed={scope === g.kind} className={cn("cursor-pointer rounded-md px-2 py-1 text-xs", scope === g.kind ? "bg-fill text-label" : "text-label-secondary hover:text-label")}>{g.label}</button>)}
            </div>
            <DialogBody ref={scroll} className="min-h-40 space-y-4 px-3 py-3" aria-busy={isFetching} onMouseEnter={cancelPeekHide} onMouseLeave={hidePeekSoon}>
              {term.length < 2 ? <p className="py-6 text-center type-caption">Search schools, faculty, programmes, runs, applications, drafts, documents, papers and chats.</p>
                : isFetching ? <p className="py-6 text-center type-caption">Searching…</p>
                : isError ? <p role="alert" className="py-6 text-center text-sm text-critical">Couldn't search. Try again.</p>
                : hits.length === 0 ? <p className="py-6 text-center type-caption">Nothing found.</p>
                : groups.filter(g => g.hits.length).map(g => <ResultGroup key={g.kind} label={g.label}>{g.hits.map(h => {
                  const index = hits.indexOf(h)
                  return <ResultRow key={`${h.kind}:${h.id}`} icon={<g.icon className="size-4 text-label-tertiary" />} title={h.title} sub={h.subtitle || ""} highlighted={index === active} onHover={() => { setActive(index); showPeek() }} onClick={() => h.href && go(h.href)} />
                })}</ResultGroup>)}
            </DialogBody>
          </div>
          {previewHit && <HoverCard hit={previewHit} list={scroll} onEnter={cancelPeekHide} onLeave={hidePeekSoon} />}
        </div>
      </DialogContent>
    </Dialog>
  </>
}

function ResultGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-1.5 px-1 type-group-label">
        {label}
      </h3>
      <ul className="min-w-0 space-y-1">{children}</ul>
    </section>
  )
}

function ResultRow({
  icon,
  title,
  sub,
  badge,
  highlighted,
  onHover,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  sub: string
  badge?: React.ReactNode
  highlighted?: boolean
  onHover: () => void
  onClick: () => void
}) {
  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={onHover}
        onFocus={onHover}
        data-active={highlighted || undefined}
        className={cn(
          "flex w-full min-w-0 max-w-full cursor-pointer items-center gap-2.5 overflow-hidden rounded-lg px-3 py-2 text-left transition-colors",
          highlighted && "bg-fill-quiet",
        )}
      >
        <span className="flex shrink-0 items-center">{icon}</span>
        <span className="min-w-0 flex-1 overflow-hidden">
          <span className="block truncate text-sm font-medium">{title}</span>
          <span className="block truncate type-caption">{sub}</span>
        </span>
        {badge ? (
          <span className="min-w-0 max-w-[45%] shrink-0 overflow-hidden *:max-w-full *:truncate">
            {badge}
          </span>
        ) : null}
      </button>
    </li>
  )
}

function HoverCard({
  hit,
  list,
  onEnter,
  onLeave,
}: {
  hit: api.SearchHit
  list: React.RefObject<HTMLDivElement | null>
  onEnter: () => void
  onLeave: () => void
}) {
  const icon = GROUPS.find(g => g.kind === hit.kind)?.icon ?? Search
  return (
    <PeekCard id={`${hit.kind}:${hit.id}`} list={list} label={hit.title} onEnter={onEnter} onLeave={onLeave}>
      <SearchPreview hit={hit} icon={icon} />
    </PeekCard>
  )
}

function SearchPreview({ hit, icon: Icon }: { hit: api.SearchHit; icon: React.ComponentType<{ className?: string }> }) {
  const ref = previewRefFor(hit)
  const preview = ref ? artifactPreview(ref) : null
  if (preview) return <>{preview.node}</>
  return <PeekSummary icon={Icon} title={hit.title} meta={hit.subtitle} text={hit.snippet} />
}

function previewRefFor(hit: api.SearchHit): PreviewRef | null {
  switch (hit.kind) {
    case "candidate":
    case "professor":
    case "application":
    case "draft":
    case "school":
      return { kind: hit.kind, id: hit.id }
    case "program": {
      const runId = hit.href?.match(/^\/runs\/([^/]+)\/programmes\//)?.[1]
      return runId ? { kind: "program", id: hit.id, runId } : null
    }
    default:
      return null
  }
}
