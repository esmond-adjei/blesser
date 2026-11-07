import { useRunBudget } from "../../lib/queries"
import { cn } from "../../lib/utils"

function Meter({
  label,
  used,
  limit,
}: {
  label: string
  used: number
  limit: number
}) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
  const full = used >= limit

  return (
    <>
      <span className="truncate">{label}</span>

      <span className="h-1 w-8 overflow-hidden rounded-full bg-fill">
        <span
          className={cn(
            "block h-full rounded-full",
            full ? "bg-caution" : "bg-tint"
          )}
          style={{ width: `${pct}%` }}
        />
      </span>

      <span className={cn("tabular-nums", full && "text-caution")}>
        {used}/{limit}
      </span>
    </>
  )
}

export function RunAllowance({
  runId,
  live,
}: {
  runId: string
  live: boolean
}) {
  const { data } = useRunBudget(runId, live ? 5000 : false)

  if (!data) return null

  const explain = [
    "Research allowance: what the research agent may save for this run.",
    "Lookups (web search, page fetch, OpenAlex) never count, in runs or in chat.",
    data.user_programs.used > 0
      ? `Schools you added (${data.user_programs.used} of ${data.user_programs.limit}) have their own allowance and don't count.`
      : `Schools you add yourself have their own allowance (${data.user_programs.limit}) and don't count.`,
  ].join("\n")

  return (
    <div
      className="grid grid-cols-[max-content_2rem_max-content] justify-items-start items-center gap-x-1 text-[10px] leading-3"
      data-tooltip={explain}
      aria-label={explain}
    >
      <Meter label="Programmes" used={data.programs.used} limit={data.programs.limit} />
      <Meter label="Professors" used={data.professors.used} limit={data.professors.limit} />
    </div>
  )
}
