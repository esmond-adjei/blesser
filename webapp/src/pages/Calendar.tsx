import * as React from "react"
import { useSearchParams } from "react-router-dom"
import { CalendarSync, Check, ChevronLeft, ChevronRight, ListTodo, PanelLeft, Plus } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import { useIsMobile } from "../hooks/use-mobile"
import { OPEN_STATUSES, useApplications } from "../lib/applications"
import { useTodos } from "../lib/opportunities"
import { useDrawerParam } from "../lib/urlParams"
import type { Todo } from "../lib/types"
import { ErrorState } from "../components/feedback/EmptyState"
import { Segmented } from "../components/layout/PageHeader"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../components/ui/shadcn/sheet"
import { todayIso } from "../components/todos/TodoList"
import { type CalendarView, SWATCH, iso, parseIso, periodTitle, shiftAnchor, visibleRange, weekDays } from "../components/calendar/dates"
import { type CalEvent, MiniMonth, MonthView, ScheduleView, TimeGridView } from "../components/calendar/views"
import { CreateTodoDialog, TodoSheet, TodosSheet } from "../components/calendar/TodoSheets"
import { SyncDialog } from "../components/calendar/SyncDialog"
import { ApplicationSheet } from "./Applications"

const VIEWS: { value: CalendarView; label: string }[] = [
  { value: "month", label: "Month" },
  { value: "week", label: "Week" },
  { value: "day", label: "Day" },
  { value: "schedule", label: "Schedule" },
]

type Filters = { deadline: boolean; todo: boolean }
const FILTERS_KEY = "blesser.calendar.filters"

function useFilters(): [Filters, (next: Filters) => void] {
  const [filters, setFilters] = React.useState<Filters>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(FILTERS_KEY) ?? "null") as Partial<Filters> | null
      return { deadline: saved?.deadline !== false, todo: saved?.todo !== false }
    } catch {
      return { deadline: true, todo: true }
    }
  })
  return [
    filters,
    (next) => {
      setFilters(next)
      try {
        localStorage.setItem(FILTERS_KEY, JSON.stringify(next))
      } catch {
        // Storage can be blocked; the choice still holds for this visit.
      }
    },
  ]
}

function useWide(): boolean {
  const query = "(min-width: 1024px)"
  return React.useSyncExternalStore(
    (cb) => {
      const media = window.matchMedia(query)
      media.addEventListener("change", cb)
      return () => media.removeEventListener("change", cb)
    },
    () => window.matchMedia(query).matches,
    () => true,
  )
}

export function Calendar() {
  const [params, setParams] = useSearchParams()
  const phone = useIsMobile()
  const wide = useWide()
  const today = todayIso()
  const viewParam = params.get("view")
  const view: CalendarView = VIEWS.some((v) => v.value === viewParam) ? (viewParam as CalendarView) : phone ? "schedule" : "month"
  const anchor = parseIso(params.get("date"))

  const go = React.useCallback(
    (next: { view?: CalendarView; date?: Date }) =>
      setParams(
        (prev) => {
          const search = new URLSearchParams(prev)
          if (next.view) search.set("view", next.view)
          if (next.date) {
            if (iso(next.date) === todayIso()) search.delete("date")
            else search.set("date", iso(next.date))
          }
          return search
        },
        { replace: true },
      ),
    [setParams],
  )

  const appDrawer = useDrawerParam("open")
  const todoDrawer = useDrawerParam("todo")
  const [filters, setFilters] = useFilters()
  const [railOpen, setRailOpen] = React.useState(false)
  const [todosOpen, setTodosOpen] = React.useState(false)
  const [creating, setCreating] = React.useState(false)
  const [syncing, setSyncing] = React.useState(false)

  const apps = useApplications()
  const todos = useTodos("open")
  const found = todoDrawer.id ? todos.data?.find((t) => t.id === todoDrawer.id) : undefined
  const all = useTodos("all", !!todoDrawer.id && todos.isSuccess && !found)
  const todo = found ?? (todoDrawer.id ? all.data?.find((t) => t.id === todoDrawer.id) : undefined) ?? null
  const missing = !!todoDrawer.id && all.isSuccess && !todo
  const closeTodo = todoDrawer.close
  React.useEffect(() => {
    if (missing) closeTodo()
  }, [missing, closeTodo])

  // Jump once to a to-do's day when it opens (e.g. from a link) outside the visible range.
  const jumped = React.useRef("")
  const [rangeStart, rangeEnd] = visibleRange(view, anchor)
  React.useEffect(() => {
    if (!todo?.due_date) return
    const key = `${todo.id}:${todo.due_date}`
    if (jumped.current === key) return
    jumped.current = key
    if (todo.due_date < rangeStart || todo.due_date > rangeEnd) go({ date: parseIso(todo.due_date) })
  }, [todo?.id, todo?.due_date, rangeStart, rangeEnd, go])

  const events = React.useMemo(() => {
    const list: CalEvent[] = []
    if (filters.deadline)
      for (const app of apps.data ?? [])
        if (app.deadline_date && (OPEN_STATUSES.includes(app.status) || app.status === "submitted"))
          list.push({ kind: "deadline", key: `d-${app.id}`, date: app.deadline_date, title: app.title, app })
    if (filters.todo)
      for (const t of todos.data ?? []) if (t.due_date) list.push({ kind: "todo", key: `t-${t.id}`, date: t.due_date, title: t.title, todo: t })
    return list.sort((a, b) => a.date.localeCompare(b.date) || (a.kind === b.kind ? 0 : a.kind === "deadline" ? -1 : 1))
  }, [apps.data, todos.data, filters])

  const byDay = React.useMemo(() => {
    const map = new Map<string, CalEvent[]>()
    for (const e of events) map.set(e.date, [...(map.get(e.date) ?? []), e])
    return map
  }, [events])

  const undated = filters.todo ? (todos.data ?? []).filter((t) => !t.due_date) : []
  const openEvent = (e: CalEvent) => (e.kind === "deadline" ? appDrawer.open(e.app.id) : todoDrawer.open(e.todo.id))
  const openTodo = (t: Todo) => {
    setRailOpen(false)
    todoDrawer.open(t.id)
  }
  const openApplicationFromTodo = (id: string) =>
    setParams((prev) => {
      const search = new URLSearchParams(prev)
      search.delete("todo")
      search.set("open", id)
      return search
    })
  const toDay = (d: Date) => go({ view: "day", date: d })
  const title = periodTitle(view, anchor)
  const loading = apps.isLoading || todos.isLoading
  const failed = apps.isError || todos.isError

  const rail = (inSheet: boolean) => (
    <Rail
      showCreate={!inSheet}
      onCreate={() => setCreating(true)}
      selected={anchor}
      today={today}
      onSelect={(d) => {
        go({ date: d })
        setRailOpen(false)
      }}
      filters={filters}
      onFilters={setFilters}
      undated={inSheet && view === "schedule" ? [] : undated}
      onOpenTodo={openTodo}
      onSync={() => {
        setRailOpen(false)
        setSyncing(true)
      }}
    />
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-1.5 gap-y-2 border-b border-separator px-3 py-2 sm:px-4">
        <Button size="sm" variant="quiet" iconOnly aria-label="Show mini calendar and filters" data-tooltip="Mini calendar and filters" className="lg:hidden" icon={<PanelLeft />} onClick={() => setRailOpen(true)} />
        <Button size="sm" variant="secondary" onClick={() => go({ date: new Date() })}>Today</Button>
        <div className="flex items-center">
          <Button size="sm" variant="quiet" iconOnly aria-label={`Previous ${view === "schedule" ? "month" : view}`} icon={<ChevronLeft />} onClick={() => go({ date: shiftAnchor(view, anchor, -1) })} />
          <Button size="sm" variant="quiet" iconOnly aria-label={`Next ${view === "schedule" ? "month" : view}`} icon={<ChevronRight />} onClick={() => go({ date: shiftAnchor(view, anchor, 1) })} />
        </div>
        <h2 className="min-w-0 flex-1 truncate font-display text-headline text-ink sm:text-title-3" aria-live="polite">{title}</h2>
        <Segmented label="Calendar view" value={view} onChange={(v) => go({ view: v })} options={VIEWS} className="max-sm:order-last" />
        <Button size="sm" variant="secondary" icon={<ListTodo />} aria-label="To-dos" className="max-sm:aspect-square max-sm:px-0" onClick={() => setTodosOpen(true)}>
          <span className="max-sm:sr-only">To-dos</span>
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        {wide ? (
          <aside aria-label="Mini calendar and filters" className="nice-scroll w-64 shrink-0 overflow-y-auto border-r border-separator p-4">
            {rail(false)}
          </aside>
        ) : null}
        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          {failed ? (
            <div className="p-3">
              <ErrorState
                compact
                title={apps.isError ? "Your applications didn't load" : "Your to-dos didn't load"}
                description="Try again in a moment."
                onRetry={() => void (apps.isError ? apps.refetch() : todos.refetch())}
              />
            </div>
          ) : null}
          {loading ? (
            <div className="m-3 flex-1 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" role="status" aria-label="Loading your calendar" />
          ) : (
            <div key={`${view}:${title}`} className={cn("bl-enter min-h-0 flex-1", view === "week" || view === "day" ? "flex flex-col" : "nice-scroll overflow-y-auto")}>
              {view === "month" ? (
                <MonthView anchor={anchor} byDay={byDay} today={today} onOpen={openEvent} onDay={toDay} />
              ) : view === "week" || view === "day" ? (
                <TimeGridView days={view === "day" ? [anchor] : weekDays(anchor)} byDay={byDay} today={today} onOpen={openEvent} onDay={toDay} />
              ) : (
                <ScheduleView
                  anchor={anchor}
                  events={events.filter((e) => e.date >= rangeStart && e.date <= rangeEnd)}
                  today={today}
                  onOpen={openEvent}
                  onDay={toDay}
                  undated={!wide && undated.length ? <NoDateList todos={undated} onOpen={openTodo} className="mt-4 border-t border-separator px-2 pt-4" /> : null}
                />
              )}
            </div>
          )}
          {!wide ? (
            <Button
              size="lg"
              variant="primary"
              iconOnly
              aria-label="Create a to-do"
              data-tooltip="Create a to-do"
              icon={<Plus />}
              onClick={() => setCreating(true)}
              className="absolute right-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-20 shadow-elevation-2"
            />
          ) : null}
        </main>
      </div>

      {!wide ? (
        <Sheet open={railOpen} onOpenChange={setRailOpen}>
          <SheetContent side="left" className="nice-scroll w-[19rem] max-w-[85vw] gap-0 overflow-y-auto p-4">
            <SheetHeader className="p-0 pr-10 pb-3">
              <SheetTitle>Calendar</SheetTitle>
              <SheetDescription className="sr-only">Pick a date and choose what to show.</SheetDescription>
            </SheetHeader>
            {rail(true)}
          </SheetContent>
        </Sheet>
      ) : null}

      <ApplicationSheet id={appDrawer.id} onClose={appDrawer.close} />
      <TodoSheet todo={todo} loading={!!todoDrawer.id && !todo && !missing} onClose={todoDrawer.close} onOpenApplication={openApplicationFromTodo} />
      <TodosSheet open={todosOpen} onClose={() => setTodosOpen(false)} />
      <CreateTodoDialog open={creating} date={iso(anchor)} onClose={() => setCreating(false)} />
      <SyncDialog open={syncing} onClose={() => setSyncing(false)} />
    </div>
  )
}

function Rail({ showCreate, onCreate, selected, today, onSelect, filters, onFilters, undated, onOpenTodo, onSync }: {
  showCreate: boolean
  onCreate: () => void
  selected: Date
  today: string
  onSelect: (date: Date) => void
  filters: Filters
  onFilters: (next: Filters) => void
  undated: Todo[]
  onOpenTodo: (todo: Todo) => void
  onSync: () => void
}) {
  return (
    <div className="space-y-5">
      {showCreate ? <Button variant="primary" icon={<Plus />} onClick={onCreate} className="shadow-elevation-1">Create</Button> : null}
      <MiniMonth selected={selected} today={today} onSelect={onSelect} />
      <section aria-labelledby="calendar-show" className="space-y-1">
        <h2 id="calendar-show" className="px-1 text-caption text-ink-tertiary">Show</h2>
        <FilterCheck checked={filters.deadline} tone="bg-sun text-on-sun" onChange={(v) => onFilters({ ...filters, deadline: v })}>Application deadlines</FilterCheck>
        <FilterCheck checked={filters.todo} tone="bg-forest text-on-forest" onChange={(v) => onFilters({ ...filters, todo: v })}>To-dos</FilterCheck>
      </section>
      {undated.length ? <NoDateList todos={undated} onOpen={onOpenTodo} /> : null}
      <Button size="sm" variant="quiet" icon={<CalendarSync />} onClick={onSync} className="-ml-1">Sync with your calendar</Button>
    </div>
  )
}

function FilterCheck({ checked, tone, onChange, children }: { checked: boolean; tone: string; onChange: (next: boolean) => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-sm px-1 text-callout text-ink transition-colors hover:bg-highlight focus-visible:outline-2 focus-visible:outline-focus"
    >
      <span aria-hidden="true" className={cn("grid size-4 place-items-center rounded-[4px] border-2", checked ? cn("border-transparent", tone) : "border-control-border")}>
        {checked ? <Check className="size-3" strokeWidth={3} /> : null}
      </span>
      {children}
    </button>
  )
}

function NoDateList({ todos, onOpen, className }: { todos: Todo[]; onOpen: (todo: Todo) => void; className?: string }) {
  return (
    <section aria-labelledby="calendar-no-date" className={cn("space-y-1", className)}>
      <h2 id="calendar-no-date" className="flex gap-1.5 px-1 text-caption text-ink-tertiary">
        No date <span className="tabular-nums">{todos.length}</span>
      </h2>
      <ul>
        {todos.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => onOpen(t)}
              className="flex w-full min-w-0 cursor-pointer items-center gap-2.5 rounded-sm px-1 py-1.5 text-left text-callout text-ink transition-colors hover:bg-highlight focus-visible:outline-2 focus-visible:outline-focus"
            >
              <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", SWATCH.todo)} />
              <span className="min-w-0 truncate">{t.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
