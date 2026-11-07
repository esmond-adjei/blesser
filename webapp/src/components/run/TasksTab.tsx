import * as React from "react"
import { createPortal } from "react-dom"
import { useRunTasksInfinite } from "../../lib/queries"
import { Skeleton } from "../ui/feedback"
import { TaskCard } from "../cards/TaskCard"
import { EmptyState } from "../feedback/EmptyState"
import { DEFAULT_PAGE_SIZE } from "./Pager"
import { TasksOutline } from "./TasksOutline"
import type { TaskTypeFilter } from "./taskTypes"

const PAGE_SIZE = DEFAULT_PAGE_SIZE

/** Infinite task list for one task type ("all" = every type), filtered server-side. */
export function TasksTab({
  runId,
  fallbackPoll,
  taskType = "discover_programs",
  status = "all",
  outlineSlot,
}: {
  runId: string
  fallbackPoll: number | false
  taskType?: TaskTypeFilter
  status?: string
  /** Where the folded outline goes: the run page's sticky header. */
  outlineSlot?: HTMLElement | null
}) {
  const [sort] = React.useState("recent")

  const base = React.useMemo(
    () => ({
      status,
      task_type: taskType,
      sort,
      limit: PAGE_SIZE,
    }),
    [status, taskType, sort],
  )
  const {
    data,
    isPending,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useRunTasksInfinite(runId, base, fallbackPoll)
  // Tasks queued while the list is open shift the offset windows, so a
  // task can arrive on two pages; keep its first copy.
  const items = React.useMemo(() => {
    const seen = new Set<string>()
    return (data?.pages ?? []).flatMap((p) => p.items).filter((t) => !seen.has(t.id) && !!seen.add(t.id))
  }, [data])
  const total = data?.pages[0]?.total ?? 0
  // Collapsed cards show their header only; ids outlive refetches.
  const [collapsed, setCollapsed] = React.useState<Set<string>>(() => new Set())
  const allCollapsed = items.length > 0 && items.every((t) => collapsed.has(t.id))
  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const sentinelRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasNextPage || isFetchingNextPage) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void fetchNextPage()
      },
      { rootMargin: "600px" },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, items.length])

  const collapseAll = (collapse: boolean) => setCollapsed(collapse ? new Set(items.map((t) => t.id)) : new Set())

  if (isPending) return <TaskListSkeleton rows={4} />
  if (total === 0 && status === "all")
    return (
      <EmptyState
        mascot="happy"
        title="No tasks"
        description="This run hasn't started any research yet."
      />
    )

  return (
    <div className="relative">
      {/* In the page's left margin when `/main` has room beside the column; otherwise a strip in the sticky header. */}
      <div className="absolute inset-y-0 right-full mr-6 hidden w-56 @min-[82rem]/main:block">
        <TasksOutline variant="list" tasks={items} allCollapsed={allCollapsed} onCollapseAll={collapseAll} />
      </div>
      {outlineSlot &&
        createPortal(
          <TasksOutline variant="strip" className="@min-[82rem]/main:hidden" tasks={items} allCollapsed={allCollapsed} onCollapseAll={collapseAll} />,
          outlineSlot,
        )}
      <div className="space-y-6">
        {items.length === 0 && (
          <p className="type-meta">No tasks with this filter yet.</p>
        )}
        {items.map((t) => (
          <TaskCard key={t.id} task={t} runId={runId} collapsed={collapsed.has(t.id)} onToggleCollapsed={() => toggle(t.id)} />
        ))}
        {hasNextPage && (
          <div ref={sentinelRef} aria-hidden>
            {isFetchingNextPage && <TaskListSkeleton rows={2} />}
          </div>
        )}
      </div>
    </div>
  )
}

function TaskListSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-3" aria-label="Loading tasks">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="max-w-4xl space-y-2 pt-3">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-36" />
        </div>
      ))}
    </div>
  )
}
