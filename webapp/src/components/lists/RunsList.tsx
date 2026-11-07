import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Ban, Pause, Pencil, Play, RefreshCw, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { useRunPages } from "../../lib/queries"
import type { RunListItem } from "../../lib/types"
import { formatRelativeDate, runTitle } from "../../lib/format"
import { cn } from "../../lib/utils"
import { runActivity } from "../../lib/runActivity"
import { MenuItem, MenuSeparator } from "../ui/menu"
import { RowMenu } from "../ui/row-menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { Skeleton, SkeletonStack } from "../ui/feedback"
import { DeleteRunDialog } from "../dialogs/DeleteRunDialog"
import { EditRunDialog } from "../dialogs/EditRunDialog"
import { LoadMore } from "../ui/LoadMore"

/** Status as a word, and only when it's news; a finished run just shows what it found. */
function runStatusWord(status: string): { label: string; className: string } | null {
  if (status === "running") return { label: "Researching", className: "text-positive" }
  if (status === "paused") return { label: "Paused", className: "text-caution" }
  if (status === "cancelled") return { label: "Cancelled", className: "text-critical" }
  return null
}

export function RunsList({ activeRunId }: { activeRunId: string | null }) {
  const [live, setLive] = React.useState(true)
  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = useRunPages(live ? 5_000 : undefined)
  // A run started between pages can push one onto the next: keep the first.
  const runs = React.useMemo(() => {
    if (!data) return undefined
    const seen = new Set<string>()
    return data.pages.flat().filter((r) => !seen.has(r.id) && !!seen.add(r.id))
  }, [data])
  const loadMore = React.useCallback(() => void fetchNextPage(), [fetchNextPage])

  React.useEffect(() => {
    setLive(!runs || runs.some((r) => runActivity(r.status, r.tasks) === "working"))
  }, [runs])

  return (
    <div className="min-h-0 flex-1 space-y-1 px-2 pb-2">
      {isLoading && (
        <div aria-label="Loading runs" aria-busy="true" className="space-y-3 px-2 py-3">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex items-center gap-2">
              <Skeleton className="size-5 rounded-full" />
              <SkeletonStack className="flex-1 space-y-1.5" blocks={["h-4 w-3/4", "h-3 w-1/2"]} />
            </div>
          ))}
        </div>
      )}
      {!isLoading && !runs?.length && <p className="px-2 py-4 type-caption">No runs yet. Start one above.</p>}
      {runs?.map((r) => {
        const active = r.id === activeRunId
        const word = runStatusWord(r.status)
        return (
          <div key={r.id} className="group relative">
            <Link
              to={`/runs/${r.id}`}
              data-tooltip={r.interest_statement}
              className={cn(
                "flex rounded-md px-2.5 pl-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-fill text-label" : "text-label-secondary hover:bg-fill-quiet hover:text-label",
              )}
            >
              <div className="flex flex-col min-w-0 flex-1 gap-0.5">
                <p className={cn("min-w-0 text-sm text-fade", runActivity(r.status, r.tasks) === "working" && "shimmer-text")}>
                  {runTitle(r)}
                </p>
                <div className="flex justify-between gap-2 type-caption text-label-tertiary">
                  <span className="truncate">
                    {word && <span className={word.className}>{word.label}, </span>}
                    {r.candidates} {r.candidates === 1 ? "candidate" : "candidates"}
                  </span>
                  <span className="shrink-0">{formatRelativeDate(r.created_at)}</span>
                </div>
              </div>
            </Link>
            <RunItemMenu run={r} title={runTitle(r)} isActive={active} />
          </div>
        )
      })}
      <LoadMore hasMore={!!hasNextPage} loading={isFetchingNextPage} onLoad={loadMore} />
    </div>
  )
}

/** A sibling of the row link so opening it never navigates. */
function RunItemMenu({ run, title, isActive }: { run: RunListItem; title: string; isActive: boolean }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [busy, setBusy] = React.useState<string | null>(null)
  const [confirmCancel, setConfirmCancel] = React.useState(false)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)

  const failedCount = run.tasks.error ?? 0

  async function control(action: "pause" | "resume" | "cancel" | "retry", fn: () => Promise<unknown>) {
    setBusy(action)
    try {
      await fn()
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["runs"] }),
        qc.invalidateQueries({ queryKey: ["run", run.id] }),
        qc.invalidateQueries({ queryKey: ["tasks", run.id] }),
      ])
    } catch {
      // Sidebar rows have no error surface; the run page surfaces failures.
      // Still close the cancel confirm so the menu doesn't wedge open.
    } finally {
      setBusy(null)
      setConfirmCancel(false)
    }
  }

  return (
    <>
      <RowMenu variant="sidebar" label={`Manage run ${title}`}>
        {run.status === "running" && (
          <MenuItem disabled={busy !== null} onSelect={() => void control("pause", () => api.pauseRun(run.id))}>
            <Pause /> {busy === "pause" ? "Pausing..." : "Pause"}
          </MenuItem>
        )}
        {(run.status === "paused" || run.status === "cancelled") && (
          <MenuItem disabled={busy !== null} onSelect={() => void control("resume", () => api.resumeRun(run.id))}>
            <Play /> {busy === "resume" ? "Resuming..." : "Resume"}
          </MenuItem>
        )}
        {(run.status === "running" || run.status === "paused") && (
          <MenuItem onSelect={() => setConfirmCancel(true)}>
            <Ban /> Cancel
          </MenuItem>
        )}
        {failedCount > 0 && (
          <MenuItem disabled={busy !== null} onSelect={() => void control("retry", () => api.retryFailed(run.id))}>
            <RefreshCw /> {busy === "retry" ? "Retrying..." : `Retry ${failedCount} failed`}
          </MenuItem>
        )}
        {(run.status === "running" || run.status === "paused" || run.status === "cancelled" || failedCount > 0) && <MenuSeparator />}
        <MenuItem onSelect={() => setEditOpen(true)}>
          <Pencil /> Edit run
        </MenuItem>
        <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
          <Trash2 /> Delete
        </MenuItem>
      </RowMenu>

      {editOpen && (
        <EditRunDialog
          key={`${run.id}-${editOpen}`}
          runId={run.id}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
      <DeleteRunDialog
        key={`delete-${run.id}-${confirmDelete}`}
        runId={run.id}
        title={title}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => {
          if (isActive) navigate("/new")
        }}
      />
      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title="Cancel this run?"
        description="Stops any new research and keeps everything you've reviewed. Resume whenever you're ready."
        confirmLabel="Cancel run"
        loading={busy === "cancel"}
        onConfirm={() => void control("cancel", () => api.cancelRun(run.id))}
      />
    </>
  )
}
