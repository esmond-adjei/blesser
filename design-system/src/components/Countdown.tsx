import { cn, formatDay } from "../lib"

export interface CountdownProps {
  /** Whole days left in Africa/Accra time; negative once closed. */
  daysLeft?: number | null
  /** yyyy-mm-dd, shown as "Closes 21 Nov 2026" on hover. */
  date?: string | null
  rolling?: boolean
  /** Shown when there is no date, such as the source's own wording. */
  label?: string
  /** "text" drops the fill for dense lists; urgency shows only in the text colour. */
  variant?: "pill" | "text"
  className?: string
}

const pill = "inline-flex shrink-0 items-baseline gap-1 rounded-full py-0.5 px-2.5 text-footnote font-medium whitespace-nowrap"

const text = "inline-flex shrink-0 items-baseline gap-1 text-footnote font-medium whitespace-nowrap tabular-nums"

function TextCountdown({ daysLeft, date, rolling, label, className }: CountdownProps) {
  const title = date ? `Closes ${formatDay(date)}` : undefined
  let words: string
  let tone = "text-ink-secondary"
  if (rolling) words = "Rolling"
  else if (daysLeft == null) words = label || "No deadline listed"
  else if (daysLeft < 0) [words, tone] = ["Closed", "text-ink-tertiary"]
  else if (daysLeft === 0) [words, tone] = ["Closes today", "text-bloom-ink"]
  else {
    words = daysLeft === 1 ? "1 day left" : `${daysLeft} days left`
    if (daysLeft <= 3) tone = "text-bloom-ink"
    else if (daysLeft <= 14) tone = "text-sun-ink"
  }
  return (
    <span title={title} className={cn(text, tone, className)}>
      {words}
    </span>
  )
}

export function Countdown(props: CountdownProps) {
  if (props.variant === "text") return <TextCountdown {...props} />
  const { daysLeft, date, rolling, label, className } = props
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
      <b className={cn("font-semibold tabular-nums", number)}>{daysLeft}</b>
      {daysLeft === 1 ? "day to go" : daysLeft <= 3 ? "days left" : "days to go"}
    </span>
  )
}
