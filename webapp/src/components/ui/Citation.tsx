import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, ContactRound, FileText, FlaskConical, Globe, Landmark, Mail } from "lucide-react"
import { Link, useNavigate } from "react-router-dom"
import * as api from "../../lib/api"
import { useApplications } from "../../lib/applications"
import { kindLabel, type Citation as CitationData, type CitationSource } from "../../lib/citations"
import { useAuth } from "../../lib/auth"
import { useCandidate, useOutboxDrafts } from "../../lib/queries"
import { cn } from "../../lib/utils"
import { ApplicationCard } from "../cards/ApplicationCards"
import { ApplicationEditMenu } from "../applications/ApplicationEditMenu"
import { ItemCard, ItemCardSkeleton } from "../cards/ItemCard"
import { ProfessorCard } from "../dossier/ProfessorCard"
import { EmailCard, PaperCard } from "../entity/detail"
import { SchoolImage } from "../entity/SchoolImage"
import { SchoolCard } from "../schools/SchoolCard"
import { Avatar } from "./avatar"
import { Popover } from "./popover"
import { ScoreBar } from "./status"

const OPEN_DELAY_MS = 150
/** Long enough to cross from the chip into the card. */
const CLOSE_DELAY_MS = 120

function hostOf(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "")
  } catch {
    return url
  }
}

/** The card's second line: subtitle, or venue and year for a paper. */
function detailOf(source: CitationSource): string | null {
  const paper = [source.venue, source.year].filter(Boolean).join(", ")
  return source.subtitle || paper || (source.url ? hostOf(source.url) : null)
}

/** Follow a source: an in-app route through the router, else a new tab. */
function useFollow() {
  const navigate = useNavigate()
  return React.useCallback(
    (source: CitationSource) => {
      if (source.href) navigate(source.href)
      else if (source.url) window.open(source.url, "_blank", "noopener,noreferrer")
    },
    [navigate],
  )
}

/** The way out of a card or list row: a router link in-app, a new tab outside. */
function SourceLink({
  source,
  className,
  children,
}: {
  source: CitationSource
  className?: string
  children: React.ReactNode
}) {
  if (source.href) {
    return (
      <Link to={source.href} className={className}>
        {children}
      </Link>
    )
  }
  if (source.url) {
    return (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </a>
    )
  }
  return null
}

function CandidateSourceCard({ source, id }: { source: CitationSource; id: string }) {
  const { data, isLoading } = useCandidate(id)
  const follow = useFollow()
  if (isLoading) return <ItemCardSkeleton />
  if (!data) return <GenericSourceCard source={source} />
  return (
    <ProfessorCard
      candidate={data}
      runId={data.run_id}
      isActive={false}
      preview
      onOpen={() => follow(source)}
    />
  )
}

function SchoolSourceCard({ source, id }: { source: CitationSource; id: string }) {
  const { data, isLoading } = useQuery({ queryKey: ["school", id], queryFn: () => api.getSchool(id) })
  const follow = useFollow()
  if (isLoading) return <ItemCardSkeleton />
  if (!data) return <GenericSourceCard source={source} />
  return <SchoolCard school={data} preview onOpen={() => follow(source)} />
}

function ApplicationSourceCard({ source, id }: { source: CitationSource; id: string }) {
  const { apps, isLoading } = useApplications()
  const follow = useFollow()
  if (isLoading) return <ItemCardSkeleton />
  const app = apps.find((item) => item.id === id)
  if (!app) return <GenericSourceCard source={source} />
  return <ApplicationCard app={app} isActive={false} preview menu={<ApplicationEditMenu app={app} />} onOpen={() => follow(source)} />
}

function PaperSourceCard({ source }: { source: CitationSource }) {
  const follow = useFollow()
  const year = typeof source.year === "number" ? source.year : Number(source.year) || null
  return (
    <PaperCard
      paper={{ title: source.title, abstract: source.snippet ?? null, year, url: source.url ?? null }}
      onOpen={source.url ? () => follow(source) : undefined}
    />
  )
}

/** The draft as the Outbox shows it, first lines only. */
function DraftSourceCard({ source, id }: { source: CitationSource; id: string }) {
  const { items, isLoading } = useOutboxDrafts()
  const { user } = useAuth()
  if (isLoading) return <ItemCardSkeleton />
  const draft = items.find((item) => item.draft.id === id)?.draft
  if (!draft) return <GenericSourceCard source={source} />
  return (
    <EmailCard
      from={{ name: user?.display_name || user?.email || "You", email: user?.email, avatarUrl: user?.avatar_url }}
      to={{ name: draft.professor_name, email: draft.professor_email }}
      date={draft.created_at}
      subject={draft.subject}
      body={draft.body}
      clamp
      footer={
        <SourceLink source={source} className="text-sm font-medium text-primary hover:underline">
          Open draft
        </SourceLink>
      }
    />
  )
}

/** A professor's link names their candidate when they were scored. */
const DOSSIER = /^\/dossier\/([^/?#]+)/

/** Reuse the record's card when the app has one, and the shared card anatomy otherwise. */
function SourceCard({ source }: { source: CitationSource }) {
  if (source.kind === "candidate" && source.id) return <CandidateSourceCard source={source} id={source.id} />
  const scored = source.kind === "professor" ? source.href?.match(DOSSIER)?.[1] : undefined
  if (scored) return <CandidateSourceCard source={source} id={scored} />
  if (source.kind === "paper") return <PaperSourceCard source={source} />
  if (source.kind === "draft" && source.id) return <DraftSourceCard source={source} id={source.id} />
  if (source.kind === "school" && source.id) return <SchoolSourceCard source={source} id={source.id} />
  if (source.kind === "application" && source.id) return <ApplicationSourceCard source={source} id={source.id} />
  return <GenericSourceCard source={source} />
}

function GenericSourceCard({ source }: { source: CitationSource }) {
  const detail = detailOf(source)
  const icons: Record<string, typeof Globe> = { professor: ContactRound, candidate: ContactRound, author: ContactRound, paper: BookOpen, school: Landmark, program: Landmark, run: FlaskConical, draft: Mail, cv: FileText, application: FileText }
  const Icon = icons[source.kind] ?? Globe
  const person = source.kind === "candidate" || source.kind === "professor" || source.kind === "author"
  const schoolImage = source.image_url && (source.kind === "school" || source.kind === "program" || source.kind === "application")
  return (
      <SourceLink source={source}>
        <ItemCard
          media={schoolImage ? <SchoolImage src={source.image_url} name={source.title} variant="card" /> : undefined}
          leading={person
            ? <Avatar name={source.title} src={source.image_url} size="sm" />
            : !schoolImage && <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span>}
          title={source.kind === "application" && source.program ? source.program : source.title}
          subtitle={source.kind === "application" && source.program ? source.title : detail}
          badges={<span className="type-group-label">{kindLabel(source.kind)}</span>}
          description={source.snippet}
          signal={source.kind === "candidate" && typeof source.score === "number" ? <ScoreBar score={source.score} /> : undefined}
          className="shadow-none"
        />
      </SourceLink>
  )
}

/** Hover or focus previews the source; a click or Enter follows it. On touch the first tap previews. */
export function CitationChip({ cite }: { cite: CitationData }) {
  const { n, source } = cite
  const [open, setOpen] = React.useState(false)
  const follow = useFollow()
  const timer = React.useRef<number | null>(null)
  const touch = React.useRef(false)

  const clear = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
  }
  const later = (next: boolean, ms: number) => {
    clear()
    timer.current = window.setTimeout(() => setOpen(next), ms)
  }
  React.useEffect(() => clear, [])

  const hover = {
    onMouseEnter: () => later(true, OPEN_DELAY_MS),
    onMouseLeave: () => later(false, CLOSE_DELAY_MS),
  }

  return (
    <Popover
      label={`Source ${n}`}
      open={open}
      onOpenChange={setOpen}
      initialFocus={false}
      panelProps={{ onMouseEnter: clear, onMouseLeave: hover.onMouseLeave }}
      className="border-none p-0"
      trigger={({ ref, id, "aria-controls": controls }) => (
        <button
          ref={ref}
          id={id}
          type="button"
          aria-describedby={open ? controls : undefined}
          aria-label={`Source ${n}: ${source.title}`}
          data-citation={source.key}
          {...hover}
          onPointerDown={(e) => {
            touch.current = e.pointerType === "touch"
          }}
          onFocus={() => later(true, OPEN_DELAY_MS)}
          onBlur={(e) => {
            // Moving into the card keeps it open.
            const into = e.relatedTarget as Node | null
            if (into && document.getElementById(controls ?? "")?.contains(into)) return
            later(false, CLOSE_DELAY_MS)
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape" && open) {
              e.stopPropagation()
              clear()
              setOpen(false)
            }
          }}
          onClick={() => {
            if (touch.current && !open) {
              clear()
              setOpen(true)
              return
            }
            clear()
            setOpen(false)
            follow(source)
          }}
          className={cn(
            "relative -top-[0.35em] mx-px inline-flex h-[1.35em] min-w-[1.35em] cursor-pointer items-center justify-center rounded-md bg-muted px-1 align-baseline text-[0.7em] font-semibold leading-none text-muted-foreground tabular-nums transition-colors hover:bg-primary/15 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            open && "bg-primary/15 text-primary",
          )}
        >
          {n}
        </button>
      )}
    >
      {() => <SourceCard source={source} />}
    </Popover>
  )
}
