import * as React from "react"
import { cn } from "../../lib/utils"
import { Skeleton, SkeletonStack } from "../ui/feedback"

/** `menu` renders outside the open button so it stays its own control. */
export function ItemCard({
  title,
  subtitle,
  leading,
  description,
  badges,
  signal,
  menu,
  media,
  onOpen,
  openLabel,
  active = false,
  className,
}: {
  title: React.ReactNode
  subtitle?: React.ReactNode
  leading?: React.ReactNode
  description?: React.ReactNode
  badges?: React.ReactNode
  /** Bottom row, e.g. a score bar. */
  signal?: React.ReactNode
  menu?: React.ReactNode
  /** Inset banner above the title row. */
  media?: React.ReactNode
  onOpen?: () => void
  openLabel?: string
  active?: boolean
  className?: string
}) {
  const body = (
    <>
      {media && <span className="-mx-1.5 -mt-1.5 mb-0.5 block w-[calc(100%+0.75rem)]">{media}</span>}
      <span className="flex w-full items-center gap-3">
        {leading}
        <span className="min-w-0 flex-1">
          <span className={cn("block", media ? "line-clamp-2 text-md leading-snug font-semibold" : "truncate font-semibold")}>
            {title}
          </span>
          {subtitle && <span className="block truncate type-caption">{subtitle}</span>}
        </span>
      </span>
      {description && (
        <span className="line-clamp-2 w-full text-sm leading-relaxed text-muted-foreground">{description}</span>
      )}
      {badges && <span className="flex w-full flex-wrap items-center gap-1.5">{badges}</span>}
      {signal && (
        <span className="mt-auto flex w-full items-center gap-2 pt-1">
          <span className="flex min-w-0 flex-1">{signal}</span>
        </span>
      )}
    </>
  )
  const inner = "flex flex-1 flex-col items-start gap-2.5 text-left"
  return (
    <div aria-selected={active || undefined} className={cn("group relative flex min-w-0 flex-col g-ecard", className)}>
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label={openLabel}
          aria-current={active || undefined}
          className={cn(inner, "cursor-pointer outline-none")}
        >
          {body}
        </button>
      ) : (
        <div className={inner}>{body}</div>
      )}
      {menu}
    </div>
  )
}

/** Loading placeholder with the same anatomy and height as an ItemCard. */
export function ItemCardSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 rounded-lg bg-card p-4 shadow-sm" aria-hidden>
      <div className="flex items-center gap-3">
        <Skeleton className="size-11 rounded-full" />
        <SkeletonStack className="flex-1 space-y-1.5" blocks={["h-3.5 w-3/5", "h-3 w-4/5"]} />
      </div>
      <div className="flex gap-1.5">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-12 rounded-full" />
      </div>
      <Skeleton className="mt-auto h-3 w-full" />
    </div>
  )
}
