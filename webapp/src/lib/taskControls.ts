import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import { toastError } from "./toast"

export type TaskAction = "retry" | "rerun" | "pause" | "resume" | "cancel" | "delete"

const CALLS: Record<TaskAction, (id: string) => Promise<unknown>> = {
  retry: api.retryTask,
  rerun: api.rerunTask,
  pause: api.pauseTask,
  resume: api.resumeTask,
  cancel: api.cancelTask,
  delete: api.deleteTask,
}

/** One task's operator controls: the call, then a refresh of everything that
 * shows the task. `busy` names the action in flight. */
export function useTaskControls(runId: string) {
  const qc = useQueryClient()
  const [busy, setBusy] = React.useState<TaskAction | null>(null)

  const run = React.useCallback(
    async (taskId: string, action: TaskAction) => {
      setBusy(action)
      try {
        await CALLS[action](taskId)
        await Promise.all([
          qc.invalidateQueries({ queryKey: ["tasks", runId] }),
          qc.invalidateQueries({ queryKey: ["task", taskId] }),
          qc.invalidateQueries({ queryKey: ["board", runId] }),
          qc.invalidateQueries({ queryKey: ["run", runId] }),
          qc.invalidateQueries({ queryKey: ["runs"] }),
        ])
      } catch (e) {
        toastError(e)
      } finally {
        setBusy(null)
      }
    },
    [qc, runId],
  )
  return { busy, run }
}

export type TaskControls = ReturnType<typeof useTaskControls>

/** The action a board card dropped on another column stands for, or null
 * when that move isn't one the task can make. */
export function dropAction(from: string, to: string): TaskAction | null {
  if (to === "paused" && (from === "pending" || from === "running")) return "pause"
  if (to === "pending") {
    if (from === "paused") return "resume"
    if (from === "error") return "retry"
    if (from === "done" || from === "cancelled") return "rerun"
  }
  if (to === "cancelled" && (from === "pending" || from === "paused" || from === "running" || from === "deferred")) return "cancel"
  return null
}
