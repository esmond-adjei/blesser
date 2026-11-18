import * as React from "react"
import { Link } from "react-router-dom"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button, cn, daysUntil } from "@blesser/ui"
import { OPEN_STATUSES } from "../../lib/applications"
import { useTodos } from "../../lib/opportunities"
import { Segmented } from "../layout/PageHeader"
import type { Application } from "../../lib/types"

type Entry =
  | { kind: "deadline"; date: string; label: string; app: Application }
  | { kind: "todo"; date: string; label: string; note: string; id: string }

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

function tone(entry: Entry): string {
  if (entry.kind === "todo") return "bg-surface-sunk text-ink-secondary"
  const days = daysUntil(entry.date)
  if (days < 0) return "bg-surface-sunk text-ink-tertiary line-through"
  if (days <= 3) return "bg-bloom-soft text-bloom-ink"
  if (days <= 14) return "bg-sun-soft text-sun-ink"
  return "bg-forest-soft text-link"
}

function dot(entry: Entry): string {
  if (entry.kind === "todo") return "bg-control-border"
  const days = daysUntil(entry.date)
  return days < 0 ? "bg-input-border-hover" : days <= 3 ? "bg-bloom" : days <= 14 ? "bg-sun" : "bg-forest"
}

/** Monday-first weeks covering the whole month. */
function monthDays(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first)
  start.setDate(1 - ((first.getDay() + 6) % 7))
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0)
  const days: Date[] = []
  for (const d = new Date(start); d <= last || days.length % 7; d.setDate(d.getDate() + 1)) days.push(new Date(d))
  return days
}

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

function startOfWeek(d: Date): Date {
  const s = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  s.setDate(s.getDate() - ((s.getDay() + 6) % 7))
  return s
}

function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor)
  return Array.from({ length: 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i))
}

function weekTitle(days: Date[]): string {
  const [a, b] = [days[0], days[6]]
  const day = (d: Date) => d.getDate()
  const mon = (d: Date) => d.toLocaleDateString(undefined, { month: "short" })
  return a.getMonth() === b.getMonth()
    ? `${day(a)} - ${day(b)} ${mon(b)} ${b.getFullYear()}`
    : `${day(a)} ${mon(a)} - ${day(b)} ${mon(b)} ${b.getFullYear()}`
}

type Mode = "month" | "week"

export function DeadlineCalendar({ apps, onOpen }: { apps: Application[]; onOpen: (app: Application) => void }) {
  const todos = useTodos("open")
  const [mode, setMode] = React.useState<Mode>("month")
  const [anchor, setAnchor] = React.useState(() => new Date())
  const today = iso(new Date())

  const entries = React.useMemo(() => {
    const list: Entry[] = []
    for (const app of apps)
      if (app.deadline_date && (OPEN_STATUSES.includes(app.status) || app.status === "submitted"))
        list.push({ kind: "deadline", date: app.deadline_date, label: app.title, app })
    for (const t of todos.data ?? [])
      if (t.due_date) list.push({ kind: "todo", date: t.due_date, label: t.title, note: t.opportunity_title || t.application_label || "", id: t.id })
    return list.sort((a, b) => a.date.localeCompare(b.date) || (a.kind === "deadline" ? -1 : 1))
  }, [apps, todos.data])

  const byDay = React.useMemo(() => {
    const map = new Map<string, Entry[]>()
    for (const e of entries) map.set(e.date, [...(map.get(e.date) ?? []), e])
    return map
  }, [entries])

  const weekEnd = new Date()
  weekEnd.setDate(weekEnd.getDate() + 7)
  const agenda = entries.filter((e) => e.date >= today && e.date <= iso(weekEnd))
  const week = weekDays(anchor)
  const title = mode === "month" ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" }) : weekTitle(week)
  const shift = (n: number) =>
    setAnchor((a) => (mode === "month" ? new Date(a.getFullYear(), a.getMonth() + n, 1) : new Date(a.getFullYear(), a.getMonth(), a.getDate() + 7 * n)))

  const pill = (e: Entry, wrap = false) => {
    const cls = cn(
      "block w-full rounded-[3px] px-1.5 py-0.5 text-left text-caption font-medium transition-[filter] hover:brightness-95",
      wrap ? "line-clamp-2" : "truncate",
      tone(e),
    )
    return e.kind === "deadline" ? (
      <button key={`d-${e.app.id}`} type="button" onClick={() => onOpen(e.app)} className={cn(cls, "cursor-pointer")} title={wrap ? undefined : e.label}>
        {e.label}
      </button>
    ) : (
      <Link key={`t-${e.id}`} to="/todos" className={cls} title={wrap ? undefined : e.label}>
        {e.label}
      </Link>
    )
  }

  const dayNumber = (d: Date, muted: boolean) => (
    <span
      className={cn(
        "inline-grid h-5 min-w-5 place-items-center rounded-[3px] px-1 text-caption tabular-nums",
        iso(d) === today ? "bg-sun font-semibold text-on-sun" : muted ? "text-ink-tertiary/60" : "text-ink-secondary",
      )}
    >
      {d.getDate()}
    </span>
  )

  return (
    <div className={cn("bl-enter grid gap-5", mode === "month" && "lg:grid-cols-[minmax(0,1fr)_17rem]")}>
      <section aria-label={title} className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center gap-1">
          <Button size="sm" variant="quiet" iconOnly aria-label={mode === "month" ? "Previous month" : "Previous week"} onClick={() => shift(-1)} icon={<ChevronLeft />} />
          <h2 className="min-w-36 text-center font-display text-headline text-ink" aria-live="polite">
            {title}
          </h2>
          <Button size="sm" variant="quiet" iconOnly aria-label={mode === "month" ? "Next month" : "Next week"} onClick={() => shift(1)} icon={<ChevronRight />} />
          <Button size="sm" variant="quiet" className="ml-1" onClick={() => setAnchor(new Date())}>
            Today
          </Button>
          <Segmented
            label="Calendar range"
            value={mode}
            onChange={setMode}
            className="ml-auto"
            options={[
              { value: "month", label: "Month" },
              { value: "week", label: "Week" },
            ]}
          />
        </div>

        {mode === "month" ? (
          <div key={title} className="bl-enter overflow-hidden rounded-md border border-separator bg-surface">
            <div className="grid grid-cols-7 border-b border-separator bg-surface-sunk text-caption font-semibold text-ink-tertiary">
              {DOW.map((d) => (
                <span key={d} className="px-2 py-1.5">
                  <span className="sm:hidden">{d[0]}</span>
                  <span className="max-sm:hidden">{d}</span>
                </span>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {monthDays(anchor).map((d) => {
                const key = iso(d)
                const items = byDay.get(key) ?? []
                const outside = d.getMonth() !== anchor.getMonth()
                return (
                  <div
                    key={key}
                    className={cn("min-h-14 border-r border-b border-separator p-1 [&:nth-child(7n)]:border-r-0 sm:min-h-24 sm:p-1.5", outside && "bg-surface-sunk/40")}
                  >
                    <div className="mb-1">{dayNumber(d, outside)}</div>
                    <div className="hidden space-y-1 sm:block">
                      {items.slice(0, 3).map((e) => pill(e))}
                      {items.length > 3 ? (
                        <button
                          type="button"
                          onClick={() => {
                            setAnchor(d)
                            setMode("week")
                          }}
                          className="block cursor-pointer px-1.5 text-caption text-ink-tertiary hover:text-ink"
                        >
                          {items.length - 3} more
                        </button>
                      ) : null}
                    </div>
                    {items.length ? (
                      <span className="flex gap-0.5 sm:hidden" aria-label={`${items.length} due`}>
                        {items.slice(0, 3).map((e, i) => (
                          <span key={i} className={cn("size-1.5 rounded-full", dot(e))} />
                        ))}
                      </span>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div key={title} className="bl-enter overflow-hidden rounded-md border border-separator bg-surface sm:grid sm:grid-cols-7">
            {week.map((d, i) => {
              const key = iso(d)
              const items = byDay.get(key) ?? []
              return (
                <div
                  key={key}
                  className={cn(
                    "flex min-w-0 gap-3 border-b border-separator p-2 last:border-b-0 sm:min-h-72 sm:flex-col sm:gap-1.5 sm:border-r sm:border-b-0 sm:last:border-r-0",
                    key === today && "bg-sun-soft/40",
                  )}
                >
                  <div className="flex w-12 shrink-0 items-center gap-1.5 sm:w-auto">
                    <span className="text-caption font-semibold text-ink-tertiary">{DOW[i]}</span>
                    {dayNumber(d, false)}
                  </div>
                  <div className="min-w-0 flex-1 space-y-1">
                    {items.length ? items.map((e) => pill(e, true)) : <span className="block py-0.5 text-caption text-ink-tertiary/70 sm:hidden">Nothing due</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="mt-2 hidden items-center gap-3 text-caption text-ink-tertiary md:flex" aria-hidden="true">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-bloom" />3 days or less</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-sun" />Within 2 weeks</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-forest" />Later</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-control-border" />To-do</span>
        </div>
      </section>
      {mode === "month" ? (
      <aside aria-label="Next 7 days" className="min-w-0">
        <h2 className="mb-3 font-display text-headline text-ink lg:pt-1.5">Next 7 days</h2>
        {agenda.length === 0 ? (
          <p className="rounded-md border border-dashed border-input-border px-4 py-6 text-center text-footnote text-ink-tertiary">Nothing due in the next 7 days.</p>
        ) : (
          <ul className="space-y-2">
            {agenda.map((e, i) => {
              const d = new Date(`${e.date}T00:00:00`)
              const body = (
                <>
                  <span className="w-9 shrink-0 text-center">
                    <span className="block text-caption text-ink-tertiary uppercase">{d.toLocaleDateString(undefined, { weekday: "short" })}</span>
                    <span className="block font-display text-title-3 leading-none text-ink">{d.getDate()}</span>
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-callout font-semibold text-ink">{e.label}</span>
                    <span className="block truncate text-footnote text-ink-tertiary">
                      {e.kind === "deadline" ? "Deadline" : e.note ? `To-do for ${e.note}` : "To-do"}
                    </span>
                  </span>
                </>
              )
              const cls = "bl-enter flex w-full items-center gap-3 rounded-sm border border-separator bg-surface px-3 py-2.5 text-left transition-colors hover:bg-highlight"
              return (
                <li key={`${e.kind}-${e.kind === "deadline" ? e.app.id : e.id}`} style={{ "--i": i } as React.CSSProperties}>
                  {e.kind === "deadline" ? (
                    <button type="button" onClick={() => onOpen(e.app)} className={cn(cls, "cursor-pointer")}>
                      {body}
                    </button>
                  ) : (
                    <Link to="/todos" className={cls}>
                      {body}
                    </Link>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </aside>
      ) : null}
    </div>
  )
}
