import * as React from "react"
import { Link } from "react-router-dom"
import { CalendarDays, ChevronRight, Copy, RefreshCw } from "lucide-react"
import * as api from "../lib/api"
import { useCalendarFeed, useTodos } from "../lib/opportunities"
import { useQueryClient } from "@tanstack/react-query"
import { toastError, toastSuccess } from "../lib/toast"
import { Button, Input, buttonVariants, cn } from "@blesser/ui"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { PageHeader } from "../components/layout/PageHeader"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog"
import { TodoAdd, TodoRow, groupTodos, todayIso } from "../components/todos/TodoList"

export function Todos() {
  const open = useTodos("open")
  const [showDone, setShowDone] = React.useState(false)
  const done = useTodos("done", showDone)
  const [syncing, setSyncing] = React.useState(false)
  const today = todayIso()
  const groups = groupTodos(open.data ?? [], today)

  return (
    <div className="bl-enter min-w-0 space-y-6">
      <PageHeader
        title="To-dos"
        description="The steps that move your applications forward."
        actions={<Button size="sm" variant="quiet" icon={<CalendarDays />} onClick={() => setSyncing(true)}>Sync calendar</Button>}
      />

      <TodoAdd />

      {open.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
          ))}
        </div>
      ) : open.isError ? (
        <ErrorState title="Your to-dos didn't load" description="Try again in a moment." onRetry={() => void open.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="Nothing to do yet"
          description="Add a to-do above, or add one from any opportunity or application."
          action={<Link to="/applications" className={buttonVariants({ size: "sm", variant: "secondary" })}>Go to applications</Link>}
        />
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <section key={group.id} aria-labelledby={`todo-group-${group.id}`} className="space-y-1.5">
              <h2 id={`todo-group-${group.id}`} className={cn("flex gap-1.5 text-caption", group.id === "overdue" ? "text-bloom-ink" : "text-ink-tertiary")}>
                {group.label} <span className="tabular-nums">{group.items.length}</span>
              </h2>
              <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
                {group.items.map((todo, i) => <TodoRow key={todo.id} todo={todo} today={today} index={i} />)}
              </ul>
            </section>
          ))}
        </div>
      )}

      <section className="space-y-1.5">
        <button
          type="button"
          aria-expanded={showDone}
          onClick={() => setShowDone((v) => !v)}
          className="flex cursor-pointer items-center gap-1 rounded-sm text-caption text-ink-tertiary hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
        >
          <ChevronRight aria-hidden="true" className={cn("size-3.5 transition-transform duration-150", showDone && "rotate-90")} />
          Done
        </button>
        {showDone ? (
          done.isLoading ? (
            <div className="h-14 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
          ) : !done.data?.length ? (
            <p className="text-footnote text-ink-secondary">Nothing done yet.</p>
          ) : (
            <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
              {done.data.map((todo, i) => <TodoRow key={todo.id} todo={todo} today={today} index={i} />)}
            </ul>
          )
        ) : null}
      </section>

      <Dialog open={syncing} onOpenChange={setSyncing}>
        {syncing ? (
          <DialogContent className="max-w-lg" onClose={() => setSyncing(false)}>
            <DialogHeader>
              <DialogTitle>Sync with your calendar</DialogTitle>
              <DialogDescription>
                Subscribe once and your application deadlines and dated to-dos appear in your calendar and stay up to date. The link is private: anyone with it can see your deadlines.
              </DialogDescription>
            </DialogHeader>
            <DialogBody><CalendarPanel /></DialogBody>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
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
    <div className="space-y-3">
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
    </div>
  )
}
