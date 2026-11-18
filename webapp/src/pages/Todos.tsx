import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link } from "react-router-dom"
import { CalendarDays, Copy, Flag, RefreshCw, Trash2 } from "lucide-react"
import * as api from "../lib/api"
import { useCalendarFeed, useTodoMutations, useTodos } from "../lib/opportunities"
import { useQueryClient } from "@tanstack/react-query"
import { toastError, toastSuccess } from "../lib/toast"
import type { Todo, TodoPriority } from "../lib/types"
import { Button, Input, Select, buttonVariants, cn } from "@blesser/ui"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { PageHeader } from "../components/layout/PageHeader"

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
    <div className="space-y-5">
      <PageHeader
        title="To-dos"
        description="What you need to do for the opportunities you're chasing. Dated to-dos also flow into your calendar."
      />

      <form
        className="flex flex-wrap items-center gap-2 rounded-lg border border-separator bg-surface p-2"
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
          className="h-control-sm min-w-[220px] flex-1 border-transparent text-callout"
        />
        <Input aria-label="Due date" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="h-control-sm w-auto text-footnote" />
        <Select
          aria-label="Priority"
          className="h-control-sm w-auto min-w-[110px] text-footnote"
          value={priority}
          onChange={(e) => setPriority(e.target.value as TodoPriority)}
        >
          {(Object.keys(PRIORITY_LABELS) as TodoPriority[]).map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABELS[p]}
            </option>
          ))}
        </Select>
        <Button type="submit" size="sm" variant="primary" disabled={create.isPending || !title.trim()}>
          Add
        </Button>
      </form>

      {open.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
          ))}
        </div>
      ) : open.isError ? (
        <ErrorState title="Your to-dos didn't load" description="Try again in a moment." onRetry={() => void open.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="Nothing to do yet"
          description="Add a to-do above, or add one from any opportunity."
          action={
            <Link to="/opportunities" className={buttonVariants({ size: "sm" })}>
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
                className={cn("mb-1.5 text-caption", group.id === "overdue" ? "text-caution" : "text-ink-tertiary")}
              >
                {group.label} <span className="font-normal tabular-nums">{group.items.length}</span>
              </h2>
              <ul className="divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface">
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
        <Button variant="quiet" size="sm" onClick={() => setShowDone((v) => !v)}>
          {showDone ? "Hide done" : "Show done"}
        </Button>
        {showDone && done.data ? (
          done.data.length === 0 ? (
            <p className="text-callout text-ink-secondary mt-2">Nothing done yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface">
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
    <li className="group flex items-start gap-3 px-4 py-2.5">
      <Checkbox
        className="mt-1"
        checked={todo.done}
        onCheckedChange={onToggle}
        aria-label={todo.done ? `Mark "${todo.title}" not done` : `Mark "${todo.title}" done`}
      />
      <div className="min-w-0 flex-1">
        <p className={cn("text-callout text-ink", todo.done && "text-ink-tertiary line-through")}>
          {todo.priority === "high" ? <Flag className="mr-1.5 inline size-3.5 align-[-2px] text-sun-ink" aria-label="High priority" /> : null}
          {todo.title}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-footnote text-ink-tertiary">
          {todo.due_date ? (
            <span className={cn("font-medium", overdue ? "text-caution" : todo.done ? "text-ink-tertiary" : "text-ink-secondary")}>
              {dueLabel(todo.due_date, today)}
            </span>
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
        size="sm"
        variant="quiet"
        aria-label={`Delete "${todo.title}"`}
        data-tooltip="Delete"
        className="opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
        onClick={onDelete}
        icon={<Trash2 />}
      />
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
    <section aria-labelledby="calendar-heading" className="space-y-3 rounded-lg border border-separator bg-surface p-4">
      <div className="flex items-start gap-3">
        <CalendarDays className="mt-0.5 size-4 shrink-0 text-ink-tertiary" />
        <div className="space-y-1">
          <h2 id="calendar-heading" className="text-callout font-semibold text-ink">
            Sync with your calendar
          </h2>
          <p className="text-footnote text-ink-secondary">
            Subscribe once and your application deadlines and dated to-dos appear in Google Calendar, Apple Calendar or
            Outlook, and stay up to date. The link is private: anyone with it can see your deadlines.
          </p>
        </div>
      </div>
      {!enabled ? (
        <Button size="sm" variant="secondary" onClick={() => setEnabled(true)}>
          Get my calendar link
        </Button>
      ) : feed.isLoading ? (
        <div className="h-10 animate-pulse rounded-md bg-surface-sunk motion-reduce:animate-none" />
      ) : feed.data ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input readOnly value={feed.data.url} aria-label="Calendar subscription link" className="h-control-sm min-w-[240px] flex-1 type-code" onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" onClick={() => void copy(feed.data.url)} icon={<Copy />}>
              Copy
            </Button>
            <a href={feed.data.webcal_url} className={buttonVariants({ size: "sm", variant: "secondary" })}>
              Open in calendar app
            </a>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-footnote text-ink-secondary">
            <li>Google Calendar: Other calendars, then From URL, and paste the link.</li>
            <li>Apple Calendar: File, then New Calendar Subscription.</li>
            <li>Outlook: Add calendar, then Subscribe from web.</li>
          </ul>
          <Button
            size="sm"
            variant="quiet"
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
            icon={<RefreshCw />}
          >
            Make a new link
          </Button>
        </div>
      ) : (
        <ErrorState compact title="Your calendar link didn't load" description="Try again in a moment." onRetry={() => void feed.refetch()} />
      )}
    </section>
  )
}
