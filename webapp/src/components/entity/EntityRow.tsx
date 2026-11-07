import * as React from "react"
import { Link } from "react-router-dom"
import { ChevronRight } from "lucide-react"
import { cn } from "../../lib/utils"
import { Skeleton, SkeletonStack } from "../ui/feedback"

/** The row size of every entity; opens through `to` or `onClick`. */
export function EntityRow({
  leading,
  title,
  subtitle,
  end,
  menu,
  to,
  onClick,
  active = false,
  compact = false,
  indent = 0,
  expanded,
  selected,
  onSelect,
  label,
  className,
}: {
  leading?: React.ReactNode
  title: React.ReactNode
  subtitle?: React.ReactNode
  end?: React.ReactNode
  /** A RowMenu; give it `className={ROW_MENU_POSITION}` (or compact). */
  menu?: React.ReactNode
  to?: string
  onClick?: () => void
  active?: boolean
  compact?: boolean
  indent?: 0 | 1 | 2
  /** Set to show an expand chevron (rotated when true). */
  expanded?: boolean
  selected?: boolean
  onSelect?: () => void
  /** Accessible name for the open control when the title isn't plain text. */
  label?: string
  className?: string
}) {
  const body = (
    <>
      {leading}
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate", compact ? "text-compact font-medium" : "text-sm font-semibold")}>{title}</span>
        {subtitle && <span className="block truncate type-caption">{subtitle}</span>}
      </span>
      {end && <span className="flex shrink-0 items-center gap-2.5">{end}</span>}
      {expanded !== undefined && (
        <ChevronRight
          aria-hidden
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-90")}
        />
      )}
    </>
  )
  const area = cn(
    "flex min-w-0 flex-1 items-center text-left outline-none",
    compact ? "gap-2.5 py-1.5" : "gap-3 py-2.5",
  )
  return (
    <div
      className={cn(
        "group relative flex items-center gap-2.5 transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-inset",
        compact ? "min-h-10 px-2.5" : "min-h-14 px-3",
        indent === 1 && (compact ? "pl-7" : "pl-8"),
        indent === 2 && (compact ? "pl-12" : "pl-14"),
        active ? "bg-tint-soft" : "hover:bg-muted/50",
        className,
      )}
    >
      {onSelect && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={onSelect}
          aria-label={`Select ${label ?? (typeof title === "string" ? title : "row")}`}
          className={cn(
            "size-4 shrink-0 cursor-pointer accent-primary transition-opacity",
            !selected && "opacity-40 group-hover:opacity-100 focus-visible:opacity-100",
          )}
        />
      )}
      {to ? (
        <Link to={to} aria-label={label} aria-current={active || undefined} className={area}>
          {body}
        </Link>
      ) : onClick ? (
        <button type="button" onClick={onClick} aria-label={label} aria-current={active || undefined} className={cn(area, "cursor-pointer")}>
          {body}
        </button>
      ) : (
        <div className={area}>{body}</div>
      )}
      {menu}
    </div>
  )
}

/** Where a RowMenu floats on an EntityRow: vertically centred at the end. */
export const ROW_MENU_POSITION = "top-1/2 right-2 -translate-y-1/2"

export function EntityList({ children }: { children: React.ReactNode }) {
  return <ul className="g-list">{React.Children.map(children, (child) => (child ? <li>{child}</li> : null))}</ul>
}

/** Loading placeholder with the same anatomy and height as an EntityRow. */
export function EntityRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5" aria-hidden>
      <Skeleton className="size-8 rounded-full" />
      <SkeletonStack className="flex-1 space-y-1.5" blocks={["h-3.5 w-2/5", "h-3 w-3/5"]} />
      <Skeleton className="h-5 w-16 rounded-full" />
    </div>
  )
}
