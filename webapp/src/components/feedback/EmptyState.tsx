import * as React from "react"
import { AlertCircle, Inbox, RefreshCw } from "lucide-react"
import { Button } from "../ui/button"
import { cn } from "../../lib/utils"

export function EmptyState({
  title,
  description,
  action,
  compact,
}: {
  title: string
  description: string
  action?: React.ReactNode
  compact?: boolean
}) {
  return (
    <div className={cn("g-empty rounded-lg bg-surface shadow-sm", compact && "py-6")}>
      <span className="g-icon-tile size-12 rounded-md">
        <Inbox className="size-6" strokeWidth={1.75} />
      </span>
      <p className={compact ? "font-semibold" : "g-empty__title"}>{title}</p>
      <p className="g-empty__body">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

/** Load-failure panel in EmptyState's layout, with an optional retry. */
export function ErrorState({
  title,
  description,
  action,
  onRetry,
  compact,
}: {
  title: string
  description: string
  action?: React.ReactNode
  onRetry?: () => void
  compact?: boolean
}) {
  return (
    <div className={cn("g-empty mx-auto max-w-xl rounded-lg bg-surface text-center shadow-sm", compact && "py-6")}>
      <span className="g-icon-tile size-12 rounded-md text-critical">
        <AlertCircle className="size-6" strokeWidth={1.75} />
      </span>
      <p className={compact ? "font-semibold" : "g-empty__title"}>{title}</p>
      <p className="g-empty__body">{description}</p>
      {onRetry || action ? (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          {onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw /> Try again
            </Button>
          ) : null}
          {action}
        </div>
      ) : null}
    </div>
  )
}
