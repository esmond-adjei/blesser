import * as React from "react"
import { Link } from "react-router-dom"
import { CalendarDays, Copy, Flag, RefreshCw, Trash2 } from "lucide-react"
import * as api from "../lib/api"
import { useCalendarFeed, useTodoMutations, useTodos } from "../lib/opportunities"
import { useQueryClient } from "@tanstack/react-query"
import { toastError, toastSuccess } from "../lib/toast"
import { cn } from "../lib/utils"
import type { Todo, TodoPriority } from "../lib/types"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Input } from "../components/ui/input"
import { Select } from "../components/ui/select"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"

/** Local yyyy-mm-dd: due dates are calendar days, not instants. */
function todayIso(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function daysBetween(fromIso: string, toIso: string): number {
  const a = Date.parse(fromIso + "T00:00:00Z")
  const b = Date.parse(toIso + "T00:00:00Z")
  return Math.round((b - a) / 86_400_000)
}

type Group = { id: string; label: string; items: Todo[] }

function groupTodos(todos: Todo[], today: string): Group[] {
  const groups: Group[] = [
    { id: "overdue", label: "Overdue", items: [] },
    { id: "today", label: "Today", items: [] },
    { id: "week", label: "Next 7 days", items: [] },
    { id: "later", label: "Later", items: [] },
    { id: "someday", label: "No date", items: [] },
  ]
  const by = Object.fromEntries(groups.map((g) => [g.id, g]))
  for (const t of todos) {
    if (!t.due_date) by.someday.items.push(t)
    else {
      const d = daysBetween(today, t.due_date)
      if (d < 0) by.overdue.items.push(t)
      else if (d === 0) by.today.items.push(t)
      else if (d <= 7) by.week.items.push(t)
      else by.later.items.push(t)
    }
  }
  return groups.filter((g) => g.items.length > 0)
}

function dueLabel(due: string, today: string): string {
  const d = daysBetween(today, due)
  if (d === 0) return "Today"
  if (d === 1) return "Tomorrow"
  if (d === -1) return "Yesterday"
  if (d < 0) return `${-d} days overdue`
  if (d <= 7) return `In ${d} days`
  return new Date(due + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

const PRIORITY_LABELS: Record<TodoPriority, string> = { high: "High", normal: "Normal", low: "Low" }

export function Todos() {
  const open = useTodos("open")
  const [showDone, setShowDone] = React.useState(false)
  const done = useTodos("done", showDone)
  const { create, update, remove } = useTodoMutations()
  const today = todayIso()

  const [title, setTitle] = React.useState("")
  const [due, setDue] = React.useState("")
  const [priority, setPriority] = React.useState<TodoPriority>("normal")

  const groups = groupTodos(open.data ?? [], today)

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="type-page-title">To-dos</h1>
        <p className="type-meta">
          Everything you need to do for the opportunities you're chasing. Deadlines of tracked applications and dated
          to-dos also flow into your calendar.
        </p>
      </header>

      <form
        className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault()
          if (!title.trim()) return
          create.mutate(
            { title: title.trim(), due_date: due || null, priority },
            {
              onSuccess: () => {
                setTitle("")
                setDue("")
                setPriority("normal")
              },
              onError: (err) => toastError(err, "Couldn't add the to-do"),
            },
          )
        }}
      >
        <Input
          aria-label="New to-do"
          placeholder="Add a to-do, e.g. Ask two referees for letters"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={300}
          className="min-w-[220px] flex-1"
        />
        <Input aria-label="Due date" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-auto" />
        <Select
          aria-label="Priority"
          className="w-auto min-w-[120px]"
          value={priority}
          onChange={(e) => setPriority(e.target.value as TodoPriority)}
        >
          {(Object.keys(PRIORITY_LABELS) as TodoPriority[]).map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABELS[p]}
            </option>
          ))}
        </Select>
        <Button type="submit" disabled={create.isPending || !title.trim()}>
          Add
        </Button>
      </form>

      {open.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-fill-quiet" />
          ))}
        </div>
      ) : open.isError ? (
        <ErrorState title="Couldn't load your to-dos" description="Try again in a moment." onRetry={() => void open.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="Nothing to do yet"
          description="Add a to-do above, or add one from any opportunity."
          action={
            <Link to="/opportunities" className="text-sm font-medium text-tint underline-offset-4 hover:underline">
              Browse opportunities
            </Link>
          }
        />
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <section key={group.id} aria-labelledby={`todo-group-${group.id}`}>
              <h2
                id={`todo-group-${group.id}`}
                className={cn(
                  "mb-2 text-xs font-semibold tracking-wide uppercase",
                  group.id === "overdue" ? "text-critical" : "text-label-tertiary",
                )}
              >
                {group.label} · {group.items.length}
              </h2>
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
                {group.items.map((todo) => (
                  <TodoRow
                    key={todo.id}
                    todo={todo}
                    today={today}
                    onToggle={() => update.mutate({ id: todo.id, body: { done: !todo.done } })}
                    onDelete={() =>
                      remove.mutate(todo.id, { onError: (err) => toastError(err, "Couldn't delete the to-do") })
                    }
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <div>
        <Button variant="ghost" size="sm" onClick={() => setShowDone((v) => !v)}>
          {showDone ? "Hide done" : "Show done"}
        </Button>
        {showDone && done.data ? (
          done.data.length === 0 ? (
            <p className="type-meta mt-2">Nothing done yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
              {done.data.map((todo) => (
                <TodoRow
                  key={todo.id}
                  todo={todo}
                  today={today}
                  onToggle={() => update.mutate({ id: todo.id, body: { done: !todo.done } })}
                  onDelete={() => remove.mutate(todo.id)}
                />
              ))}
            </ul>
          )
        ) : null}
      </div>

      <CalendarPanel />
    </div>
  )
}

function TodoRow({
  todo,
  today,
  onToggle,
  onDelete,
}: {
  todo: Todo
  today: string
  onToggle: () => void
  onDelete: () => void
}) {
  const overdue = !todo.done && todo.due_date !== null && daysBetween(today, todo.due_date) < 0
  return (
    <li className="group flex items-start gap-3 px-3 py-2.5">
      <input
        type="checkbox"
        className="mt-1 size-4 shrink-0 cursor-pointer"
        checked={todo.done}
        onChange={onToggle}
        aria-label={todo.done ? `Mark "${todo.title}" not done` : `Mark "${todo.title}" done`}
      />
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm text-label", todo.done && "text-label-tertiary line-through")}>
          {todo.priority === "high" ? <Flag className="mr-1 inline size-3.5 text-critical" aria-label="High priority" /> : null}
          {todo.title}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-label-secondary">
          {todo.due_date ? (
            <Badge variant={overdue ? "destructive" : "outline"}>{dueLabel(todo.due_date, today)}</Badge>
          ) : null}
          {todo.application_id && todo.application_label ? (
            <Link to={`/applications/${todo.application_id}`} className="hover:underline">
              {todo.application_label}
            </Link>
          ) : null}
          {todo.opportunity_id && todo.opportunity_title ? (
            <Link to={`/opportunities?q=${encodeURIComponent(todo.opportunity_title)}`} className="hover:underline">
              {todo.opportunity_title}
            </Link>
          ) : null}
          {todo.priority === "low" ? <span>Low priority</span> : null}
        </div>
      </div>
      <Button
        size="icon"
        variant="ghost"
        aria-label={`Delete "${todo.title}"`}
        className="opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
        onClick={onDelete}
      >
        <Trash2 />
      </Button>
    </li>
  )
}

function CalendarPanel() {
  const [enabled, setEnabled] = React.useState(false)
  const feed = useCalendarFeed(enabled)
  const client = useQueryClient()
  const [rotating, setRotating] = React.useState(false)
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toastSuccess("Link copied")
    } catch (err) {
      toastError(err, "Couldn't copy")
    }
  }
  return (
    <section aria-labelledby="calendar-heading" className="space-y-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start gap-3">
        <CalendarDays className="mt-0.5 size-5 shrink-0 text-tint" />
        <div className="space-y-1">
          <h2 id="calendar-heading" className="text-sm font-semibold text-label">
            Sync with your calendar
          </h2>
          <p className="text-sm text-label-secondary">
            Subscribe once and your application deadlines and dated to-dos appear in Google Calendar, Apple Calendar or
            Outlook, and stay up to date. The link is private: anyone with it can see your deadlines.
          </p>
        </div>
      </div>
      {!enabled ? (
        <Button size="sm" variant="outline" onClick={() => setEnabled(true)}>
          Get my calendar link
        </Button>
      ) : feed.isLoading ? (
        <div className="h-9 animate-pulse rounded-md bg-fill-quiet" />
      ) : feed.data ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input readOnly value={feed.data.url} aria-label="Calendar subscription link" className="min-w-[240px] flex-1 font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" variant="outline" onClick={() => void copy(feed.data.url)}>
              <Copy /> Copy
            </Button>
            <a href={feed.data.webcal_url} className="g-btn g-btn--secondary g-btn--sm">
              Open in calendar app
            </a>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-xs text-label-secondary">
            <li>Google Calendar: Other calendars, then From URL, and paste the link.</li>
            <li>Apple Calendar: File, then New Calendar Subscription.</li>
            <li>Outlook: Add calendar, then Subscribe from web.</li>
          </ul>
          <Button
            size="sm"
            variant="ghost"
            disabled={rotating}
            onClick={async () => {
              setRotating(true)
              try {
                const next = await api.rotateCalendarFeed()
                client.setQueryData(["calendar-feed"], next)
                toastSuccess("New link made. The old one no longer works.")
              } catch (err) {
                toastError(err, "Couldn't make a new link")
              } finally {
                setRotating(false)
              }
            }}
          >
            <RefreshCw /> Make a new link
          </Button>
        </div>
      ) : (
        <ErrorState compact title="Couldn't load your calendar link" description="Try again in a moment." onRetry={() => void feed.refetch()} />
      )}
    </section>
  )
}
