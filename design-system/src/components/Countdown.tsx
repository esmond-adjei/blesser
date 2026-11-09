import { cn, formatDay } from "../lib"

export interface CountdownProps {
  /** Whole days left in Africa/Accra time; negative once closed. */
  daysLeft?: number | null
  /** yyyy-mm-dd, shown as "Closes 21 Nov 2026" on hover. */
  date?: string | null
  rolling?: boolean
  /** Shown when there is no date, such as the source's own wording. */
  label?: string
  className?: string
}

const pill = "inline-flex shrink-0 items-baseline gap-1.5 rounded-full py-1.5 pr-3.5 pl-3 text-footnote font-medium whitespace-nowrap"

export function Countdown({ daysLeft, date, rolling, label, className }: CountdownProps) {
  const title = date ? `Closes ${formatDay(date)}` : undefined
  if (rolling) return <span className={cn(pill, "bg-forest-soft text-link", className)}>Rolling, apply any time</span>
  if (daysLeft == null)
    return <span className={cn(pill, "bg-surface-sunk text-ink-secondary", className)}>{label || "No deadline listed"}</span>
  if (daysLeft < 0)
    return (
      <span title={title} className={cn(pill, "bg-surface-sunk text-ink-tertiary", className)}>
        Closed
      </span>
    )
  if (daysLeft === 0)
    return (
      <span title={title} className={cn(pill, "bg-bloom-soft text-bloom-ink", className)}>
        Closes today
      </span>
    )
  const tone = daysLeft <= 3 ? "bg-bloom-soft text-bloom-ink" : daysLeft <= 14 ? "bg-sun-soft text-sun-ink" : "bg-surface-sunk text-ink-secondary"
  const number = daysLeft <= 3 ? "text-bloom-ink" : daysLeft <= 14 ? "text-sun-ink" : "text-ink"
  return (
    <span title={title} className={cn(pill, tone, className)}>
      <b className={cn("font-display text-xl leading-[22px] font-bold tracking-[-0.02em] tabular-nums", number)}>{daysLeft}</b>
      {daysLeft === 1 ? "day to go" : daysLeft <= 3 ? "days left" : "days to go"}
    </span>
  )
}
