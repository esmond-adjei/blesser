import { RefreshCw } from "lucide-react"
import { useRunRefusals, useRunUsage } from "../../lib/queries"
import { toastError } from "../../lib/toast"

export function StatsRefreshButton({ runId }: { runId: string }) {
  const usage = useRunUsage(runId)
  const refusals = useRunRefusals(runId)
  const refreshing = usage.isFetching || refusals.isFetching

  async function refresh() {
    try {
      await Promise.all([usage.refetch({ throwOnError: true }), refusals.refetch({ throwOnError: true })])
    } catch (error) {
      toastError(error, "Couldn't refresh stats")
    }
  }

  return (
    <button
      type="button"
      aria-label="Refresh stats"
      data-tooltip="Refresh stats"
      disabled={refreshing}
      onClick={() => void refresh()}
      className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-wait disabled:opacity-50"
    >
      <RefreshCw className={`size-4 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden />
    </button>
  )
}
