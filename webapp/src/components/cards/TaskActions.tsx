import * as React from "react"
import { Ban, Copy, EllipsisVertical, Pause, Play, RefreshCw, RotateCcw, Trash2 } from "lucide-react"
import { useTaskControls, type TaskAction, type TaskControls } from "../../lib/taskControls"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { Menu, MenuItem, MenuSeparator } from "../ui/menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"

/** Cancel and delete ask first; every other action runs at once. */
export function TaskConfirmDialogs({
  taskId,
  status,
  confirm,
  onClose,
  controls,
}: {
  taskId: string
  status: string
  confirm: "cancel" | "delete" | null
  onClose: () => void
  controls: TaskControls
}) {
  async function go(action: "cancel" | "delete") {
    await controls.run(taskId, action)
    onClose()
  }
  return (
    <>
      <ConfirmDialog
        open={confirm === "cancel"}
        onOpenChange={(o) => { if (!o) onClose() }}
        title="Cancel this task?"
        description={status === "running"
          ? "The task stops at its next step and its result is discarded. Rerun starts it fresh from here."
          : "The task stops for good. Rerun restarts it fresh from here."}
        confirmLabel="Cancel task"
        loading={controls.busy === "cancel"}
        onConfirm={() => void go("cancel")}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        onOpenChange={(o) => { if (!o) onClose() }}
        title="Delete this task?"
        description="Removes the task and its tool-call records. Anything it already saved stays in the database."
        confirmLabel="Delete task"
        loading={controls.busy === "delete"}
        onConfirm={() => void go("delete")}
      />
    </>
  )
}

/** Only actions valid for the current status show. Retry resumes from the checkpoint, rerun starts fresh. */
export function TaskActions({
  task,
  runId,
  controls: given,
  onCopy,
  className,
}: {
  task: { id: string; status: string }
  runId: string
  controls?: TaskControls
  onCopy?: () => void
  className?: string
}) {
  const own = useTaskControls(runId)
  const controls = given ?? own
  const [confirm, setConfirm] = React.useState<"cancel" | "delete" | null>(null)
  const { status } = task
  const busy = controls.busy !== null
  const act = (action: TaskAction) => void controls.run(task.id, action)

  return (
    <>
      <Menu
        label="Task actions"
        trigger={
          <Button size="icon" variant="ghost" aria-label="Task actions" className={cn("size-7 shrink-0", className)}>
            <EllipsisVertical />
          </Button>
        }
      >
        {(status === "pending" || status === "running") && (
          <MenuItem disabled={busy} onSelect={() => act("pause")}>
            <Pause /> Pause
          </MenuItem>
        )}
        {status === "paused" && (
          <MenuItem disabled={busy} onSelect={() => act("resume")}>
            <Play /> Resume
          </MenuItem>
        )}
        {status === "error" && (
          <MenuItem disabled={busy} onSelect={() => act("retry")}>
            <RefreshCw /> Retry (resume)
          </MenuItem>
        )}
        {(status === "done" || status === "error" || status === "cancelled") && (
          <MenuItem disabled={busy} onSelect={() => act("rerun")}>
            <RotateCcw /> Rerun (fresh)
          </MenuItem>
        )}
        {(status === "pending" || status === "paused" || status === "running" || status === "deferred") && (
          <MenuItem disabled={busy} onSelect={() => setConfirm("cancel")}>
            <Ban /> Cancel
          </MenuItem>
        )}
        {onCopy && (
          <MenuItem onSelect={onCopy}>
            <Copy /> Copy as Markdown
          </MenuItem>
        )}
        <MenuSeparator />
        <MenuItem
          destructive
          disabled={busy || status === "running"}
          onSelect={() => setConfirm("delete")}
        >
          <Trash2 /> {status === "running" ? "Delete (cancel first)" : "Delete"}
        </MenuItem>
      </Menu>
      <TaskConfirmDialogs taskId={task.id} status={status} confirm={confirm} onClose={() => setConfirm(null)} controls={controls} />
    </>
  )
}
