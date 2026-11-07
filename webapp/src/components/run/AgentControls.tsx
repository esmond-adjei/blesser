import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Ban, Ellipsis, Pause, Play } from "lucide-react"
import * as api from "../../lib/api"
import { toastError, toastInfo } from "../../lib/toast"
import type { AgentState } from "../../lib/types"
import { Menu, MenuItem } from "../ui/menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { TASK_TYPE_TAB_LABELS, type TaskTypeFilter } from "./taskTypes"

/** Running tasks stop at their next step. Mount beside the tab trigger, never inside it, so opening the menu doesn't switch tabs. */
export function AgentControls({
  runId,
  taskType,
  state,
  queued,
}: {
  runId: string
  taskType: TaskTypeFilter
  state?: AgentState
  /** Its tasks not yet started (pending, paused, waiting): what cancel stops. */
  queued: number
}) {
  const qc = useQueryClient()
  const [busy, setBusy] = React.useState(false)
  const [confirmCancel, setConfirmCancel] = React.useState(false)
  const label = TASK_TYPE_TAB_LABELS[taskType]

  async function run(action: "pause" | "resume" | "cancel") {
    setBusy(true)
    try {
      const res = await api.controlAgent(runId, taskType, action)
      const verb = action === "pause" ? "Paused" : action === "resume" ? "Resumed" : "Cancelled"
      toastInfo(`${verb} the ${label}${res.affected ? ` (${res.affected} task${res.affected === 1 ? "" : "s"})` : ""}.`)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["run", runId] }),
        qc.invalidateQueries({ queryKey: ["runs"] }),
        qc.invalidateQueries({ queryKey: ["tasks", runId] }),
        qc.invalidateQueries({ queryKey: ["board", runId] }),
      ])
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
      setConfirmCancel(false)
    }
  }

  return (
    <>
      <div className="absolute right-1 top-1/2 z-10 -translate-y-1/2 opacity-0 transition-opacity pointer-events-none group-hover:pointer-events-auto group-hover:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100">
        <Menu
          label={`${label} controls`}
          trigger={
            <button
              type="button"
              aria-label={`${label} controls`}
              data-tooltip={`${label} controls`}
              className="flex size-6 min-w-0 cursor-pointer items-center justify-center rounded-md p-0 text-label-secondary transition-colors hover:bg-fill hover:text-label"
            >
              <Ellipsis className="size-3.5" />
            </button>
          }
        >
          {state === "paused" || state === "cancelled" ? (
            <MenuItem onSelect={() => void run("resume")}>
              <Play /> Resume agent
            </MenuItem>
          ) : (
            <MenuItem onSelect={() => void run("pause")}>
              <Pause /> Pause agent
            </MenuItem>
          )}
          {state !== "cancelled" && (
            <MenuItem destructive onSelect={() => setConfirmCancel(true)}>
              <Ban /> Cancel agent
            </MenuItem>
          )}
        </Menu>
      </div>
      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title={`Cancel the ${label}?`}
        description={
          `${queued} queued task${queued === 1 ? "" : "s"} and any running ones will be cancelled, and they won't take new work for the rest ` +
          "of this run unless you resume them. Running tasks stop at their next step. Finished results are kept."
        }
        confirmLabel="Cancel agent"
        loading={busy}
        onConfirm={() => void run("cancel")}
      />
    </>
  )
}

/** Why an agent is idle on this tab — paused or cancelled for the run. */
export function AgentStatusNote({ taskType, state }: { taskType: TaskTypeFilter; state?: AgentState }) {
  const label = TASK_TYPE_TAB_LABELS[taskType]
  const text =
    state === "paused"
      ? `${label} paused: their work, running tasks included, waits until you resume them.`
      : state === "cancelled"
        ? `${label} cancelled for this run. Finished results are kept; resume them from the tab's menu to continue.`
        : null
  if (!text) return null
  return <p className="min-w-0 type-caption">{text}</p>
}
