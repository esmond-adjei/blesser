import * as React from "react"
import { CalendarClock, ChevronLeft, ChevronRight, Circle, CircleCheck } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import type { Application, Todo } from "../../lib/types"
import { DOW, SWATCH, iso, monthDays, monthTitle, weekday } from "./dates"

export type CalEvent =
  | { kind: "deadline"; key: string; date: string; title: string; app: Application }
  | { kind: "todo"; key: string; date: string; title: string; todo: Todo }

export type OpenEvent = (event: CalEvent) => void

function chipTone(event: CalEvent, today: string): string {
  if (event.kind === "todo") return event.todo.done ? "bg-surface-sunk text-ink-tertiary line-through" : "bg-forest-soft text-link"
  return event.date < today ? "bg-surface-sunk text-ink-tertiary" : "bg-sun-soft text-sun-ink"
}

function eventLabel(event: CalEvent): string {
  return event.kind === "deadline" ? `Deadline: ${event.title}` : `To-do: ${event.title}`
}

export function EventIcon({ event, className }: { event: CalEvent; className?: string }) {
  const Icon = event.kind === "deadline" ? CalendarClock : event.todo.done ? CircleCheck : Circle
  return <Icon aria-hidden="true" className={cn("size-3 shrink-0", className)} strokeWidth={2} />
}

export function EventChip({ event, today, onOpen, wrap }: { event: CalEvent; today: string; onOpen: OpenEvent; wrap?: boolean }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onOpen(event)
      }}
      aria-label={eventLabel(event)}
      className={cn(
        "flex w-full min-w-0 cursor-pointer items-center gap-1 rounded-[4px] px-1.5 py-px text-left text-caption font-semibold transition-[filter] hover:brightness-95 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus",
        chipTone(event, today),
      )}
    >
      <EventIcon event={event} className="max-sm:hidden" />
      <span className={cn("min-w-0", wrap ? "line-clamp-2 wrap-anywhere" : "truncate")}>{event.title}</span>
    </button>
  )
}

function DayNumber({ date, today, muted, size = "md" }: { date: Date; today: string; muted?: boolean; size?: "md" | "lg" }) {
  const isToday = iso(date) === today
  return (
    <span
      className={cn(
        "inline-grid place-items-center rounded-full tabular-nums",
        size === "lg" ? "size-10 text-title-3 font-semibold" : "size-6 text-caption",
        isToday ? "bg-sun font-bold text-on-sun" : muted ? "text-ink-tertiary" : "text-ink",
      )}
    >
      {date.getDate()}
    </span>
  )
}

export function MonthView({ anchor, byDay, today, onOpen, onDay }: {
  anchor: Date
  byDay: Map<string, CalEvent[]>
  today: string
  onOpen: OpenEvent
  onDay: (date: Date) => void
}) {
  const days = monthDays(anchor)
  const weeks = days.length / 7
  const max = 3
  return (
    <div className="flex min-h-full flex-col">
      <div className="grid grid-cols-7 border-b border-separator">
        {DOW.map((d) => (
          <span key={d} className="py-1.5 text-center text-caption text-ink-tertiary uppercase">
            <span className="sm:hidden">{d[0]}</span>
            <span className="max-sm:hidden">{d}</span>
          </span>
        ))}
      </div>
      <div className="grid flex-1 grid-cols-7" style={{ gridTemplateRows: `repeat(${weeks}, minmax(5.5rem, 1fr))` }}>
        {days.map((d) => {
          const key = iso(d)
          const items = byDay.get(key) ?? []
          const outside = d.getMonth() !== anchor.getMonth()
          const shown = items.length > max ? items.slice(0, max - 1) : items
          return (
            <div
              key={key}
              onClick={() => onDay(d)}
              className={cn(
                "flex min-w-0 cursor-pointer flex-col gap-0.5 border-r border-b border-separator p-0.5 transition-colors hover:bg-highlight/50 sm:p-1 [&:nth-child(7n)]:border-r-0",
                outside && "bg-surface-sunk/50",
              )}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onDay(d)
                }}
                aria-label={`${weekday(d)} ${d.getDate()}${items.length ? `, ${items.length} ${items.length === 1 ? "item" : "items"}` : ""}`}
                className="mx-auto cursor-pointer rounded-full hover:bg-highlight focus-visible:outline-2 focus-visible:outline-focus"
              >
                <DayNumber date={d} today={today} muted={outside} />
              </button>
              <div className="hidden min-w-0 space-y-0.5 sm:block">
                {shown.map((e) => <EventChip key={e.key} event={e} today={today} onOpen={onOpen} />)}
                {items.length > shown.length ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDay(d)
                    }}
                    className="block w-full cursor-pointer rounded-[4px] px-1.5 text-left text-caption text-ink-secondary hover:bg-highlight hover:text-ink"
                  >
                    {items.length - shown.length} more
                  </button>
                ) : null}
              </div>
              {items.length ? (
                <span aria-hidden="true" className="flex flex-wrap justify-center gap-0.5 sm:hidden">
                  {items.slice(0, 4).map((e) => <span key={e.key} className={cn("size-1.5 rounded-full", SWATCH[e.kind])} />)}
                </span>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const HOUR = 48
const HOURS = Array.from({ length: 24 }, (_, h) => h)

function useNowMinutes(): number {
  const read = () => {
    const now = new Date()
    return now.getHours() * 60 + now.getMinutes()
  }
  const [minutes, setMinutes] = React.useState(read)
  React.useEffect(() => {
    const timer = window.setInterval(() => setMinutes(read()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  return minutes
}

export function TimeGridView({ days, byDay, today, onOpen, onDay }: {
  days: Date[]
  byDay: Map<string, CalEvent[]>
  today: string
  onOpen: OpenEvent
  onDay: (date: Date) => void
}) {
  const minutes = useNowMinutes()
  const scroller = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = Math.max(0, (new Date().getHours() - 2) * HOUR)
  }, [])
  const cols = { gridTemplateColumns: `3.25rem repeat(${days.length}, minmax(0, 1fr))` }
  const single = days.length === 1

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="grid shrink-0 border-b border-separator" style={cols}>
        <span />
        {days.map((d) => (
          <button
            key={iso(d)}
            type="button"
            disabled={single}
            onClick={() => onDay(d)}
            aria-label={single ? undefined : `${weekday(d)} ${d.getDate()}`}
            className={cn("flex flex-col items-center gap-0.5 py-1.5", single ? "items-start pl-2" : "cursor-pointer hover:bg-highlight/50")}
          >
            <span className={cn("text-caption uppercase", iso(d) === today ? "text-sun-ink" : "text-ink-tertiary")}>{weekday(d, "short")}</span>
            <DayNumber date={d} today={today} size={single ? "lg" : "md"} />
          </button>
        ))}
      </div>
      <div className="grid shrink-0 border-b border-separator" style={cols}>
        <span className="self-center pr-2 text-right text-caption text-ink-tertiary">All day</span>
        {days.map((d) => {
          const items = byDay.get(iso(d)) ?? []
          return (
            <div key={iso(d)} className="nice-scroll max-h-32 min-h-8 min-w-0 space-y-0.5 overflow-y-auto border-l border-separator p-0.5 sm:p-1">
              {items.map((e) => <EventChip key={e.key} event={e} today={today} onOpen={onOpen} wrap={single} />)}
            </div>
          )
        })}
      </div>
      <div ref={scroller} className="nice-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="relative grid" style={{ ...cols, height: HOUR * 24 }}>
          <div className="relative">
            {HOURS.slice(1).map((h) => (
              <span key={h} className="absolute right-2 -translate-y-1/2 text-caption font-normal text-ink-tertiary tabular-nums" style={{ top: h * HOUR }}>
                {String(h).padStart(2, "0")}:00
              </span>
            ))}
          </div>
          {days.map((d) => (
            <div key={iso(d)} className="relative border-l border-separator">
              {HOURS.slice(1).map((h) => <span key={h} aria-hidden="true" className="absolute inset-x-0 border-t border-separator" style={{ top: h * HOUR }} />)}
              {iso(d) === today ? (
                <span aria-hidden="true" className="absolute inset-x-0 z-10 h-0.5 bg-sun-ink" style={{ top: (minutes / 60) * HOUR }}>
                  <span className="absolute -top-[5px] -left-[6px] size-3 rounded-full bg-sun-ink" />
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function eventNote(event: CalEvent): string {
  if (event.kind === "deadline") return event.app.organization ? `Deadline, ${event.app.organization}` : "Deadline"
  if (event.todo.done) return "To-do, done"
  const parent = event.todo.application_label || event.todo.opportunity_title
  return parent ? `To-do for ${parent}` : "To-do"
}

export function EventRow({ event, onOpen }: { event: CalEvent; onOpen: OpenEvent }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(event)}
      className="flex w-full min-w-0 cursor-pointer items-start gap-3 rounded-sm px-2 py-2 text-left transition-colors hover:bg-highlight focus-visible:outline-2 focus-visible:outline-focus"
    >
      <span aria-hidden="true" className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", SWATCH[event.kind])} />
      <span className="min-w-0">
        <span className={cn("block text-callout font-semibold text-ink wrap-anywhere", event.kind === "todo" && event.todo.done && "text-ink-tertiary line-through")}>{event.title}</span>
        <span className="block truncate text-footnote text-ink-secondary">{eventNote(event)}</span>
      </span>
    </button>
  )
}

export function ScheduleView({ anchor, events, today, onOpen, onDay, undated }: {
  anchor: Date
  events: CalEvent[]
  today: string
  onOpen: OpenEvent
  onDay: (date: Date) => void
  undated: React.ReactNode
}) {
  const groups = React.useMemo(() => {
    const map = new Map<string, CalEvent[]>()
    for (const e of events) map.set(e.date, [...(map.get(e.date) ?? []), e])
    return [...map.entries()]
  }, [events])
  const list = React.useRef<HTMLOListElement>(null)
  React.useEffect(() => {
    list.current?.querySelector<HTMLElement>("[data-upcoming]")?.scrollIntoView({ block: "start" })
  }, [anchor])
  const firstUpcoming = groups.find(([date]) => date >= today)?.[0]

  return (
    <div className="mx-auto w-full max-w-3xl px-2 py-3 sm:px-4">
      {groups.length === 0 ? (
        <p className="px-2 py-10 text-center text-callout text-ink-secondary">Nothing scheduled in {monthTitle(anchor)}.</p>
      ) : (
        <ol ref={list} className="divide-y divide-separator">
          {groups.map(([date, items], i) => {
            const d = new Date(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)))
            return (
              <li
                key={date}
                data-upcoming={date === firstUpcoming ? "" : undefined}
                style={{ "--i": Math.min(i, 8) } as React.CSSProperties}
                className="bl-enter grid scroll-mt-2 grid-cols-[3.5rem_minmax(0,1fr)] gap-2 py-2 sm:grid-cols-[6rem_minmax(0,1fr)]"
              >
                <button type="button" onClick={() => onDay(d)} aria-label={`${weekday(d)} ${d.getDate()}`} className="flex cursor-pointer flex-col items-center gap-0.5 self-start rounded-sm py-1 hover:bg-highlight sm:flex-row sm:gap-2 sm:px-2">
                  <DayNumber date={d} today={today} />
                  <span className={cn("text-caption uppercase", date === today ? "text-sun-ink" : "text-ink-tertiary")}>{weekday(d, "short")}</span>
                </button>
                <div className="min-w-0">
                  {items.map((e) => <EventRow key={e.key} event={e} onOpen={onOpen} />)}
                </div>
              </li>
            )
          })}
        </ol>
      )}
      {undated}
    </div>
  )
}

export function MiniMonth({ selected, today, onSelect }: { selected: Date; today: string; onSelect: (date: Date) => void }) {
  const [shown, setShown] = React.useState(() => new Date(selected.getFullYear(), selected.getMonth(), 1))
  const [synced, setSynced] = React.useState(iso(selected))
  if (synced !== iso(selected)) {
    setSynced(iso(selected))
    setShown(new Date(selected.getFullYear(), selected.getMonth(), 1))
  }
  const days = monthDays(shown)
  const selectedKey = iso(selected)
  return (
    <section aria-label="Pick a date">
      <div className="mb-1 flex items-center">
        <h2 className="flex-1 pl-1 text-callout font-semibold text-ink" aria-live="polite">{monthTitle(shown)}</h2>
        <Button size="sm" variant="quiet" iconOnly aria-label="Previous month" onClick={() => setShown((s) => new Date(s.getFullYear(), s.getMonth() - 1, 1))} icon={<ChevronLeft />} className="size-8" />
        <Button size="sm" variant="quiet" iconOnly aria-label="Next month" onClick={() => setShown((s) => new Date(s.getFullYear(), s.getMonth() + 1, 1))} icon={<ChevronRight />} className="size-8" />
      </div>
      <div className="grid grid-cols-7 text-center">
        {DOW.map((d) => <span key={d} aria-hidden="true" className="py-1 text-caption text-ink-tertiary">{d[0]}</span>)}
        {days.map((d) => {
          const key = iso(d)
          const isToday = key === today
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelect(d)}
              aria-label={`${weekday(d)} ${d.getDate()} ${monthTitle(d)}`}
              aria-current={key === selectedKey ? "date" : undefined}
              className={cn(
                "mx-auto grid size-8 cursor-pointer place-items-center rounded-full text-caption font-medium tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-focus",
                isToday ? "bg-sun font-bold text-on-sun" : key === selectedKey ? "bg-forest-soft text-link" : d.getMonth() !== shown.getMonth() ? "text-ink-tertiary hover:bg-highlight" : "text-ink hover:bg-highlight",
              )}
            >
              {d.getDate()}
            </button>
          )
        })}
      </div>
    </section>
  )
}
