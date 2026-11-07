import * as React from "react"
import { ArrowRight, CircleHelp } from "lucide-react"
import { useRun, useRunBoard, useTask } from "../../lib/queries"
import type { BoardTask } from "../../lib/types"
import { Button } from "../ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Skeleton, SkeletonStack } from "../ui/feedback"
import { TaskCard } from "../cards/TaskCard"
import { EmptyState, ErrorState } from "../feedback/EmptyState"
import { TaskTypeLabel } from "../ui/status"
import { TASK_TYPE_TAB_LABELS } from "../run/taskTypes"
import { TaskActions, TaskConfirmDialogs } from "../cards/TaskActions"
import { dropAction, useTaskControls } from "../../lib/taskControls"
import { formatAgo } from "../../lib/format"
import { useNow } from "../../lib/useNow"
import { cn } from "../../lib/utils"

const COLUMNS = [
  { status: "deferred", label: "Waiting", description: "Held until research limits allow; may remain after the run ends.", hint: "" },
  {
    status: "pending",
    label: "Pending",
    description: "Queued for a worker or waiting for a retry.",
    hint: "These tasks are ready and will start on their own. They wait for a free worker (only so many tasks run at once), for a retry after a temporary error, or for OpenAlex's daily lookup limit to reset. Drag one to Paused to hold it, or to Cancelled to drop it.",
  },
  {
    status: "running",
    label: "Running",
    description: "Currently being processed.",
    hint: "A worker is on these right now: the agent is searching, reading pages and scoring. Open a card to watch its live trace. Drag one to Paused to stop it after its current step.",
  },
  {
    status: "paused",
    label: "Paused",
    description: "Temporarily stopped; resume to continue.",
    hint: "You paused these, or paused this kind of agent. They keep their progress and pick up where they left off. Drag one to Pending to resume it.",
  },
  {
    status: "done",
    label: "Done",
    description: "Finished, including tasks with no match.",
    hint: "These finished normally. Done doesn't mean a match: a professor whose work didn't fit your interests is done too. Drag one to Pending to rerun it from scratch.",
  },
  {
    status: "error",
    label: "Failed",
    description: "Stopped by an error; can be retried.",
    hint: "These stopped on an error they couldn't recover from, such as a site that kept failing or the model being unavailable. The card shows the error. Drag one to Pending to retry from where it stopped.",
  },
  {
    status: "cancelled",
    label: "Cancelled",
    description: "Stopped before completion; can be rerun.",
    hint: "You cancelled these, or the run was cancelled, before they finished. Nothing more happens to them. Drag one to Pending to rerun it from scratch.",
  },
] as const

const BOARD_LIMIT = 200

/** Rows are slim (no traces); dragging a card to another column does what it means (pause, resume, retry, rerun or cancel). */
export function TaskBoard({
  runId,
  counts,
  fallbackPoll,
  onViewAll,
}: {
  runId: string
  counts: Record<string, number>
  fallbackPoll: number | false
  onViewAll: (status: string) => void
}) {
  const grandTotal = COLUMNS.reduce((n, c) => n + (counts[c.status] ?? 0), 0)
  const [openTask, setOpenTask] = React.useState<BoardTask | null>(null)
  const { data: board, isLoading, isError } = useRunBoard(runId, fallbackPoll)
  const controls = useTaskControls(runId)
  const { data: run } = useRun(runId)
  const perProgramme = run?.max_professors_per_program
  const cap = run?.max_professors
  const waitingHint = [
    "These professors are leads waiting their turn, not stuck tasks.",
    perProgramme
      ? `Each programme gets at most ${perProgramme} professors researched, so once a programme has used its ${perProgramme} slots its other leads wait here.`
      : "Each programme gets a limited number of professors researched, so once a programme uses its slots its other leads wait here.",
    `Leads are also held while the run nears its${cap ? ` ${cap}-professor` : ""} cap, while programmes take turns, and after a programme's last few professors didn't align.`,
    "Leads still waiting when the run ends simply weren't needed; raise the per-programme limit to research more of them.",
  ].join(" ")
  const [dragTask, setDragTask] = React.useState<BoardTask | null>(null)
  const [over, setOver] = React.useState<string | null>(null)
  const [cancelling, setCancelling] = React.useState<BoardTask | null>(null)
  // "5m ago" stamps: a slow tick is enough.
  const now = useNow(true, 30_000)

  function drop(task: BoardTask, to: string) {
    const action = dropAction(task.status, to)
    if (action === "cancel") setCancelling(task)
    else if (action) void controls.run(task.id, action)
  }

  if (grandTotal === 0)
    return (
      <EmptyState
        mascot="happy"
        title="No tasks"
        description="This run hasn't started any research yet."
      />
    )

  return (
    <>
      <div className={cn("nice-scroll flex gap-3 overflow-x-auto pb-2", !dragTask && "snap-x")}>
        {COLUMNS.map((col) => (
          <BoardColumn
            key={col.status}
            status={col.status}
            label={col.label}
            description={col.description}
            hint={col.status === "deferred" ? waitingHint : col.hint}
            total={counts[col.status] ?? 0}
            items={(board?.[col.status] ?? []).slice(0, BOARD_LIMIT)}
            isLoading={isLoading}
            isError={isError}
            onViewAll={onViewAll}
            drop={dragTask ? { valid: dropAction(dragTask.status, col.status) !== null, over: over === col.status } : null}
            draggingId={dragTask?.id ?? null}
            now={now}
            renderActions={(t) => <TaskActions task={t} runId={runId} className="size-6" />}
            onOpen={setOpenTask}
            columnHandlers={{
              onDragOver: (e) => {
                if (!dragTask || dropAction(dragTask.status, col.status) === null) return
                e.preventDefault()
                e.dataTransfer.dropEffect = "move"
                setOver(col.status)
              },
              onDragLeave: (e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null)
              },
              onDrop: (e) => {
                e.preventDefault()
                setOver(null)
                setDragTask(null)
                if (dragTask) drop(dragTask, col.status)
              },
            }}
            cardHandlers={(t) => ({
              draggable: true,
              onDragStart: (e) => {
                e.dataTransfer.setData("text/plain", t.id)
                e.dataTransfer.effectAllowed = "move"
                setDragTask(t)
              },
              onDragEnd: () => {
                setDragTask(null)
                setOver(null)
              },
            })}
          />
        ))}
      </div>

      {cancelling && (
        <TaskConfirmDialogs
          taskId={cancelling.id}
          status={cancelling.status}
          confirm="cancel"
          onClose={() => setCancelling(null)}
          controls={controls}
        />
      )}

      <Dialog open={openTask !== null} onOpenChange={(o) => { if (!o) setOpenTask(null) }}>
        <DialogContent
          onClose={() => setOpenTask(null)}
          className="max-w-3xl"
        >
          <DialogHeader>
            <DialogTitle>
              {openTask && TASK_TYPE_TAB_LABELS[openTask.task_type as keyof typeof TASK_TYPE_TAB_LABELS] || "Task Agent"}
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="pb-10">
            {openTask && (
              <TaskDialogBody
                key={openTask.id}
                task={openTask}
                runId={runId}
              />
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenTask(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** Rows are slim, so the open task is polled separately; polling stops at a terminal status and resumes on requeue. */
function TaskDialogBody({ task, runId }: { task: BoardTask; runId: string }) {
  const [live, setLive] = React.useState(true)
  const { data: full, isLoading, isError, refetch } = useTask(task.id, live ? 3000 : false)

  React.useEffect(() => {
    const s = full?.status
    setLive(!s || s === "pending" || s === "running")
  }, [full?.status])

  if (isLoading) return <SkeletonStack aria-label="Loading task details" aria-busy="true" className="space-y-3" blocks={["h-6 w-1/2", "h-16", "h-16", "h-24"]} />
  if (isError || !full) {
    return (
      <ErrorState
        compact
        mascot="error-gear"
        title="Couldn't load this task"
        description="It may have been deleted."
        onRetry={() => void refetch()}
      />
    )
  }
  return <TaskCard task={full} runId={runId} />
}

function BoardColumn({
  status,
  label,
  description,
  hint,
  total,
  items,
  isLoading,
  isError,
  onViewAll,
  drop,
  draggingId,
  now,
  renderActions,
  onOpen,
  columnHandlers,
  cardHandlers,
}: {
  status: string
  label: string
  description: string
  hint?: string
  total: number
  items: BoardTask[]
  isLoading: boolean
  isError: boolean
  onViewAll: (status: string) => void
  /** While a card is dragged: whether it can land here, and if it's over us. */
  drop: { valid: boolean; over: boolean } | null
  draggingId: string | null
  now: number
  renderActions: (task: BoardTask) => React.ReactNode
  onOpen: (task: BoardTask) => void
  columnHandlers: Pick<React.HTMLAttributes<HTMLDivElement>, "onDragOver" | "onDragLeave" | "onDrop">
  cardHandlers: (task: BoardTask) => React.HTMLAttributes<HTMLDivElement>
}) {

  return (
    <Card
      {...columnHandlers}
      className={cn(
        "flex max-h-[65vh] w-72 shrink-0 snap-start flex-col bg-muted/50 dark:bg-foreground/5 transition-[box-shadow,opacity] sm:w-80",
        drop && !drop.valid && "opacity-60",
        drop?.valid && "outline-2 outline-dashed outline-primary/40",
        drop?.valid && drop.over && "outline-primary",
      )}
    >
      <CardHeader className="flex-none space-y-1 p-3 pb-2">
        <CardTitle className="flex items-center gap-1.5 text-sm">
          {label} <span className="tabular-nums text-muted-foreground">{total}</span>
          {hint && (
            <span data-tooltip={hint} tabIndex={0} aria-label={hint} className="cursor-help text-muted-foreground hover:text-foreground">
              <CircleHelp className="size-3.5" />
            </span>
          )}
        </CardTitle>
        <p className="type-caption">{description}</p>
      </CardHeader>
      <CardContent className="nice-scroll min-h-0 flex-1 space-y-2 overflow-y-auto p-3 pt-0">
        {isLoading && (
          <>
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <p className="rounded-md bg-fill-quiet px-2 py-4 text-center type-caption">
            Empty
          </p>
        )}
        {!isLoading && isError && (
          <p className="rounded-md bg-critical-soft px-2 py-4 text-center text-xs text-critical">
            Couldn't load {label.toLowerCase()} tasks.
          </p>
        )}
        {items.map((t) => (
          <div
            key={t.id}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault()
                onOpen(t)
              }
            }}
            {...cardHandlers(t)}
            onClick={() => onOpen(t)}
            className={cn(
              "group relative block w-full cursor-pointer select-none rounded-lg border border-border bg-card p-2.5 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              draggingId === t.id && "opacity-40",
            )}
          >
            <span
              // Portalled menu events bubble here through React: they mustn't open or drag the card.
              onClick={(e) => e.stopPropagation()}
              onDragStart={(e) => e.preventDefault()}
              onKeyDown={(e) => e.stopPropagation()}
              className="absolute right-1.5 top-1.5"
            >
              {renderActions(t)}
            </span>
            <span className="block pr-7 text-sm">
              <TaskTypeLabel type={t.task_type} />
            </span>
            {t.target_name && (
              <span className="block truncate type-caption">{t.target_name}</span>
            )}
            {t.status === "error" && t.error && (
              <span className="mt-0.5 line-clamp-2 block text-xs text-critical">{t.error}</span>
            )}
            {(t.status === "pending" || t.status === "deferred") && t.error && (
              <span className="mt-0.5 line-clamp-2 block type-caption">{t.error}</span>
            )}
            {t.updated_at && (
              <time dateTime={t.updated_at} className="mt-1.5 block text-right tabular-nums type-caption">
                {formatAgo(t.updated_at, now)}
              </time>
            )}
          </div>
        ))}
        {total > BOARD_LIMIT && (
          <Button size="sm" variant="ghost" className="w-full" onClick={() => onViewAll(status)}>
            View all {total} <ArrowRight />
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
