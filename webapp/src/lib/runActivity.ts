/** What the agent is doing on a run, measured from open tasks, not the run row's
 * status, which can stay "running" after every task errors. working =
 * open tasks; stalled = running with only failed tasks; idle otherwise. */
export type RunActivity = "working" | "stalled" | "idle"

/** Run statuses that stop work even with tasks still queued. */
const HALTED_RUN_STATUSES = new Set(["paused", "cancelled", "done"])

export function runActivity(
  status: string | undefined,
  counts: Record<string, number> | undefined,
): RunActivity {
  if (!status || HALTED_RUN_STATUSES.has(status)) return "idle"
  const open = (counts?.pending ?? 0) + (counts?.running ?? 0)
  if (open > 0) return "working"
  return status === "running" && (counts?.error ?? 0) > 0 ? "stalled" : "idle"
}

const RATE_LIMIT = /rate.?limit|429|too many requests/i

/** One line on why a stalled run stopped, from its failed tasks' errors. */
export function stallReason(failed: number, errors: (string | null | undefined)[]): string {
  const noun = `${failed} task${failed === 1 ? "" : "s"}`
  if (errors.some((e) => e && RATE_LIMIT.test(e)))
    return `Nothing is running: ${noun} failed because the model provider is rate-limiting requests. Wait a minute, then retry the failed tasks.`
  const latest = errors.find(Boolean)
  return `Nothing is running: ${noun} failed${latest ? ` (${latest})` : ""}. Retry the failed tasks, or check your model settings if they fail again.`
}
