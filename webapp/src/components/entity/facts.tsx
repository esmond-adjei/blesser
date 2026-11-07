import * as React from "react"
import { CalendarDays, type LucideIcon } from "lucide-react"
import { daysUntil } from "../../lib/applications"
import { cn } from "../../lib/utils"

/** Each value carries its own icon; spacing separates them instead of punctuation or chips. */
export interface Fact {
  icon: LucideIcon
  iconClassName?: string
  /** Plain text or a link. Falsy facts are skipped. */
  value: React.ReactNode
  title?: string
  href?: string | null
}

export function FactList({
  facts,
  size = "md",
  className,
}: {
  facts: Array<Fact | null | false | undefined | "" | 0>
  /** "sm" for rows and cards, "md" for detail headers. */
  size?: "sm" | "md"
  className?: string
}) {
  const shown = facts.filter((f): f is Fact => !!f && !!f.value)
  if (shown.length === 0) return null
  return (
    <span
      className={cn(
        "flex min-w-0 flex-wrap items-center text-muted-foreground",
        size === "sm" ? "gap-x-3 gap-y-0.5 text-xs" : "gap-x-4 gap-y-1 text-compact",
        className,
      )}
    >
      {shown.map((f, i) => {
        const Icon = f.icon
        const body = (
          <>
            <Icon aria-hidden className={cn("shrink-0", size === "sm" ? "size-3.5" : "size-3.5", f.iconClassName)} />
            <span className="truncate">{f.value}</span>
          </>
        )
        return f.href ? (
          <a
            key={i}
            href={f.href}
            target="_blank"
            rel="noreferrer"
            data-tooltip={f.title}
            className="inline-flex min-w-0 items-center gap-1.5 text-primary hover:underline"
          >
            {body}
          </a>
        ) : (
          <span key={i} data-tooltip={f.title} className="inline-flex min-w-0 items-center gap-1.5">
            {body}
          </span>
        )
      })}
    </span>
  )
}

/** Under seven days a caution pill, past it a neutral "Closed" one, never red. */
export function Deadline({ deadline, long = false, className }: { deadline: string; long?: boolean; className?: string }) {
  if (!deadline) {
    return <span className={cn("inline-flex items-center gap-1.5 type-caption", className)}>No deadline</span>
  }
  const d = daysUntil(deadline)
  const date = new Date(`${deadline}T12:00:00`)
  const label = isNaN(date.getTime())
    ? deadline
    : date.toLocaleDateString(undefined, long ? { year: "numeric", month: "short", day: "numeric" } : { month: "short", day: "numeric" })
  if (d !== null && d < 7) {
    const word = d < 0 ? "Closed" : d === 0 ? "Due today" : `${d} day${d === 1 ? "" : "s"} left`
    return (
      <span className={cn("g-pill shrink-0 whitespace-nowrap", d >= 0 && "g-pill--caution", className)}>
        {word}, {label}
      </span>
    )
  }
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 type-caption whitespace-nowrap tabular-nums", className)}>
      <CalendarDays aria-hidden className="size-3.5" />
      {label}
      {d !== null && `, ${d} days left`}
    </span>
  )
}
