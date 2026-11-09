import { cn } from "../lib"

export type ApplicationStage = "saved" | "preparing" | "submitted" | "interview" | "accepted" | "not-this-time"

export const APPLICATION_STAGES = [
  { id: "saved", label: "Saved" },
  { id: "preparing", label: "Preparing" },
  { id: "submitted", label: "Submitted" },
  { id: "interview", label: "Interview" },
  { id: "accepted", label: "Accepted" },
] as const

export interface ApplicationStatusProps {
  status: ApplicationStage
  className?: string
}

export function ApplicationStatus({ status, className }: ApplicationStatusProps) {
  const index = APPLICATION_STAGES.findIndex((s) => s.id === status)
  const accepted = status === "accepted"
  const ended = status === "not-this-time"
  const label = ended ? "Not this time" : APPLICATION_STAGES[index].label
  const note = accepted
    ? "Congratulations"
    : ended
      ? "Keep going, more are coming"
      : `Step ${index + 1} of ${APPLICATION_STAGES.length}`
  return (
    <div className={cn("flex w-full flex-col gap-2", className)} data-status={status}>
      <div className={cn("flex justify-between gap-3 text-sm leading-5 font-semibold", accepted ? "text-bloom-ink" : "text-ink")}>
        {label}
        <span className="text-footnote font-normal text-ink-tertiary">{note}</span>
      </div>
      <div className="flex gap-1" aria-hidden="true">
        {APPLICATION_STAGES.map((s, i) => (
          <span
            key={s.id}
            className={cn(
              "relative h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunk",
              !accepted && !ended && i < index && "bg-forest",
              !accepted && !ended && i === index && "bg-sun",
            )}
          >
            {accepted ? (
              <span
                className="absolute inset-0 origin-left bg-bloom motion-safe:animate-[blesser-bloom-fill_120ms_linear_both]"
                style={{ animationDelay: `${i * 120}ms` }}
              />
            ) : null}
          </span>
        ))}
      </div>
    </div>
  )
}
