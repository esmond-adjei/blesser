import * as React from "react"
import { CalendarDays, GraduationCap } from "lucide-react"
import { daysUntil, type Application, type ApplicationStatus } from "../../lib/applications"
import { initials } from "../../lib/initials"
import { cn } from "../../lib/utils"
import { useFillViewport, useScrollFade } from "../../lib/useScrollFade"
import { ApplicationStatusBadge } from "../ui/status"
import { SchoolImage } from "../entity/SchoolImage"
import { Cover, CoverCard } from "../cards/CoverCard"
import { ApplicationSchoolLink } from "./ApplicationSchoolLink"

/** `menu` sits on top of each card's open button so it stays its own control. */

const MONTH = new Intl.DateTimeFormat(undefined, { month: "short" })
const MONTH_YEAR = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" })
const SHORT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" })
const SHORT_YEAR = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" })
/** "Dec 1", with the year when it isn't this one. */
const short = (d: Date) => (d.getFullYear() === new Date().getFullYear() ? SHORT : SHORT_YEAR).format(d)

function deadlineDate(deadline: string): Date | null {
  if (!deadline) return null
  const d = new Date(`${deadline}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** The deadline as a calendar leaf; its month turns caution inside a week. */
function DateLeaf({ deadline }: { deadline: string }) {
  const date = deadlineDate(deadline)
  const days = daysUntil(deadline)
  if (!date) {
    return (
      <span className="g-date text-label-tertiary" aria-label="No deadline">
        <CalendarDays className="size-5" strokeWidth={1.75} />
      </span>
    )
  }
  return (
    <span className="g-date" data-soon={days !== null && days >= 0 && days < 7 ? "" : undefined} aria-label={`Due ${short(date)}`}>
      <span className="g-date__m">{MONTH.format(date)}</span>
      <span className="g-date__d">{date.getDate()}</span>
    </span>
  )
}

/** Inside a week, a caution pill with the days left; past it, "Closed". */
function UrgencyPill({ deadline }: { deadline: string }) {
  const days = daysUntil(deadline)
  if (days === null || days >= 7) return null
  if (days < 0) return <span className="g-pill">Closed</span>
  return <span className="g-pill g-pill--caution">{days === 0 ? "Due today" : `${days} day${days === 1 ? "" : "s"} left`}</span>
}

/** "Due Dec 1, in 5 days" for tiles and rows. */
function dueText(deadline: string): string {
  const date = deadlineDate(deadline)
  if (!date) return deadline ? `Due ${deadline}` : "No deadline"
  const days = daysUntil(deadline)
  const when = short(date)
  if (days === null || days < 0) return `Closed ${when}`
  if (days === 0) return `Due ${when}, today`
  if (days < 31) return `Due ${when}, in ${days} day${days === 1 ? "" : "s"}`
  return `Due ${when}`
}

function Requirements({ app, long = false }: { app: Application; long?: boolean }) {
  const total = app.requirements.length
  if (total === 0) return <span className="g-segments__label text-label-tertiary">No requirements listed</span>
  const done = app.requirements.filter((r) => r.done).length
  const label = long ? (done === total ? "All requirements" : `${done} of ${total} requirements`) : `${done} of ${total}`
  return (
    <span className="flex items-center gap-2">
      <span className="g-segments" aria-hidden>
        {app.requirements.map((r, i) => (
          <span key={i} data-on={r.done ? "" : undefined} />
        ))}
      </span>
      <span className="g-segments__label">{label}</span>
    </span>
  )
}

function ProfessorStack({ app }: { app: Application }) {
  if (app.professors.length === 0) return null
  const shown = app.professors.slice(0, 3)
  const more = app.professors.length - shown.length
  return (
    <span className="g-avatars ml-auto" data-tooltip={app.professors.map((p) => p.name).join(", ")}>
      {shown.map((p, i) => (
        <span key={`${p.name}-${i}`} className="g-avatar g-avatar--sm">
          {initials(p.name)}
        </span>
      ))}
      {more > 0 && <span className="g-avatars__more">+{more}</span>}
    </span>
  )
}

function Place({ app }: { app: Application }) {
  return <><ApplicationSchoolLink name={app.school} />{app.school && app.location ? ", " : ""}{app.location}</>
}

const degreeTag = (app: Application) => (app.degreeType === "Either" ? "PhD or Master's" : app.degreeType === "Masters" ? "Master's" : app.degreeType)

interface CardProps {
  app: Application
  active?: boolean
  onOpen: () => void
  menu?: React.ReactNode
}

/** The column says the status, so the card doesn't. */
function ApplicationBoardCard({
  app,
  active,
  onOpen,
  menu,
  dragging,
  onDragStart,
  onDragEnd,
}: CardProps & { dragging?: boolean; onDragStart?: (e: React.DragEvent) => void; onDragEnd?: () => void }) {
  const days = daysUntil(app.deadline)
  return (
    <CoverCard
      label={`Open ${app.program || app.school}`}
      onOpen={onOpen}
      active={active}
      className={cn("g-ecard--board", dragging && "opacity-50")}
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <div className="pointer-events-none relative g-ecard__head">
        <DateLeaf deadline={app.deadline} />
        <div className="min-w-0 flex-1 pr-6">
          <h3 className="g-ecard__title g-clamp-1">{app.program || "Programme not set"}</h3>
          <p className="g-ecard__meta g-clamp-1"><Place app={app} /></p>
        </div>
      </div>
      {app.offer && <p className="pointer-events-none relative g-ecard__meta g-clamp-1 text-[13px] leading-[18px]">Funding: {app.offer}</p>}
      <div className="pointer-events-none relative">
        <Requirements app={app} />
      </div>
      <div className="pointer-events-none relative g-ecard__signal pt-0.5">
        {/* Inside a week the days left replace the degree. */}
        {days !== null && days < 7 ? <UrgencyPill deadline={app.deadline} /> : <span className="g-tag">{degreeTag(app)}</span>}
        {app.feeWaiver && <span className="g-tag">Fee waiver</span>}
        <ProfessorStack app={app} />
      </div>
      {menu && <div className="absolute top-2 right-2 z-10">{menu}</div>}
    </CoverCard>
  )
}

export function ApplicationTile({ app, active, onOpen, menu }: CardProps) {
  return (
    <CoverCard label={`Open ${app.program || app.school}`} onOpen={onOpen} active={active} className="h-full">
      <div className="pointer-events-none relative g-ecard__media">
        <SchoolImage src={app.schoolImageUrl} name={app.school} variant="card" className="h-full rounded-none" />
      </div>
      <span className="pointer-events-none relative g-ecard__kind">
        <GraduationCap className="size-3.5" /> Application
      </span>
      <h3 className="pointer-events-none relative g-ecard__title line-clamp-2">{app.program || "Programme not set"}</h3>
      <p className="pointer-events-none relative g-ecard__meta g-clamp-1"><Place app={app} /></p>
      <div className="pointer-events-none relative">
        <Requirements app={app} long />
      </div>
      <div className="pointer-events-none relative g-ecard__signal">
        <ApplicationStatusBadge status={app.status} />
        <span className="g-push tabular-nums text-[13px] text-label-tertiary">
          {app.status === "offer" && app.offer ? app.offer : dueText(app.deadline)}
        </span>
      </div>
      {menu && <div className="absolute top-1 right-1 z-10">{menu}</div>}
    </CoverCard>
  )
}

function ApplicationDateRow({ app, active, onOpen, menu, compact }: CardProps & { compact?: boolean }) {
  return (
    <li className="group relative flex items-center gap-3 px-4 py-3 transition-colors hover:bg-fill-quiet/50 aria-selected:bg-tint-soft/50" aria-selected={active || undefined}>
      <Cover label={`Open ${app.program || app.school}`} onOpen={onOpen} />
      <span className="pointer-events-none relative">
        <DateLeaf deadline={app.deadline} />
      </span>
      <span className="pointer-events-none relative min-w-0 flex-1">
        <span className="block truncate text-[15px] font-semibold">{app.program || "Programme not set"}</span>
        <span className="block truncate type-meta"><Place app={app} /></span>
      </span>
      {!compact && (
        <span className="pointer-events-none relative hidden w-40 sm:block">
          <Requirements app={app} />
        </span>
      )}
      <span className="pointer-events-none relative flex shrink-0 items-center gap-2">
        <UrgencyPill deadline={app.deadline} />
        <ApplicationStatusBadge status={app.status} />
      </span>
      {menu && <span className="absolute top-1 right-1 z-10">{menu}</span>}
    </li>
  )
}

/** Upcoming deadlines by month, then closed ones, then undated ones. */
export function ApplicationAgenda({
  apps,
  isActive,
  onOpen,
  menuFor,
  compact,
}: {
  apps: Application[]
  isActive: (app: Application) => boolean
  onOpen: (app: Application) => void
  menuFor: (app: Application) => React.ReactNode
  compact?: boolean
}) {
  const groups = React.useMemo(() => {
    const upcoming = new Map<string, Application[]>()
    const closed: Application[] = []
    const undated: Application[] = []
    const byDate = [...apps].sort((a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999"))
    for (const app of byDate) {
      const date = deadlineDate(app.deadline)
      const days = daysUntil(app.deadline)
      if (!date) undated.push(app)
      else if (days !== null && days < 0) closed.push(app)
      else {
        const key = MONTH_YEAR.format(date)
        upcoming.set(key, [...(upcoming.get(key) ?? []), app])
      }
    }
    return [
      ...[...upcoming].map(([label, items]) => ({ label, items })),
      { label: "Closed", items: closed.reverse() },
      { label: "No deadline", items: undated },
    ].filter((g) => g.items.length > 0)
  }, [apps])
  return (
    <div className="space-y-6">
      {groups.map((g) => (
        <section key={g.label}>
          <h2 className="g-list-title">
            {g.label} <span className="font-medium text-label-tertiary tabular-nums">{g.items.length}</span>
          </h2>
          <ul className="g-list">
            {g.items.map((app) => (
              <ApplicationDateRow key={app.id} app={app} active={isActive(app)} onOpen={() => onOpen(app)} menu={menuFor(app)} compact={compact} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

/** Dragging a card to another column moves it; the card menu does the same without a pointer. */
export function ApplicationBoard({
  apps,
  statuses,
  isActive,
  onOpen,
  menuFor,
  onMove,
}: {
  apps: Application[]
  statuses: ApplicationStatus[]
  isActive: (app: Application) => boolean
  onOpen: (app: Application) => void
  menuFor: (app: Application) => React.ReactNode
  onMove: (app: Application, status: ApplicationStatus) => void
}) {
  const [dragId, setDragId] = React.useState<string | null>(null)
  const [over, setOver] = React.useState<ApplicationStatus | null>(null)
  const byDeadline = (a: Application, b: Application) => (a.deadline || "9999").localeCompare(b.deadline || "9999")
  // The board fills the screen below the toolbar; columns scroll, not the page.
  const fit = useFillViewport<HTMLDivElement>()
  const row = useScrollFade<HTMLDivElement>("x", [statuses.length])
  return (
    <div ref={fit} className="-mx-1 min-h-0">
      <div ref={row} className="nice-scroll scroll-fade-x flex h-full gap-4 overflow-x-auto px-1 pb-2">
        {statuses.map((status) => (
          <BoardColumn
            key={status}
            status={status}
            items={apps.filter((a) => a.status === status).sort(byDeadline)}
            over={over === status}
            dragId={dragId}
            onDragOver={(e) => {
              if (!dragId) return
              e.preventDefault()
              e.dataTransfer.dropEffect = "move"
              setOver(status)
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null)
            }}
            onDrop={(e) => {
              e.preventDefault()
              const app = apps.find((a) => a.id === e.dataTransfer.getData("text/plain"))
              setOver(null)
              setDragId(null)
              if (app && app.status !== status) onMove(app, status)
            }}
            renderCard={(app) => (
              <ApplicationBoardCard
                key={app.id}
                app={app}
                active={isActive(app)}
                onOpen={() => onOpen(app)}
                menu={menuFor(app)}
                dragging={dragId === app.id}
                onDragStart={(e) => {
                  e.dataTransfer.setData("text/plain", app.id)
                  e.dataTransfer.effectAllowed = "move"
                  setDragId(app.id)
                }}
                onDragEnd={() => {
                  setDragId(null)
                  setOver(null)
                }}
              />
            )}
          />
        ))}
      </div>
    </div>
  )
}

function BoardColumn({
  status,
  items,
  over,
  dragId,
  onDragOver,
  onDragLeave,
  onDrop,
  renderCard,
}: {
  status: ApplicationStatus
  items: Application[]
  over: boolean
  dragId: string | null
  onDragOver: (e: React.DragEvent<HTMLElement>) => void
  onDragLeave: (e: React.DragEvent<HTMLElement>) => void
  onDrop: (e: React.DragEvent<HTMLElement>) => void
  renderCard: (app: Application) => React.ReactNode
}) {
  const list = useScrollFade<HTMLDivElement>("y", [items.length])
  return (
    <section
      aria-label={status}
      className={cn("flex h-full w-[272px] shrink-0 flex-col rounded-lg transition-colors", over && "bg-tint-soft")}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <header className="flex items-center gap-2 px-2 pt-1 pb-2">
        <ApplicationStatusBadge status={status} />
        <span className="text-sm font-medium text-label-tertiary tabular-nums">{items.length}</span>
      </header>
      {/* Padding inside the scroller keeps the card shadows unclipped. */}
      <div ref={list} className="nice-scroll scroll-fade-y flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-1 pb-3">
        {items.map(renderCard)}
        {items.length === 0 && (
          <p className="rounded-md px-3 py-6 text-center type-caption ring-1 ring-separator ring-inset">
            {dragId ? "Drop here" : "Nothing here"}
          </p>
        )}
      </div>
    </section>
  )
}
