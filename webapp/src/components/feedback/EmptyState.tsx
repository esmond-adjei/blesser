import * as React from "react"
import { RefreshCw } from "lucide-react"
import { Button, EmptyState as BaseEmptyState, cn } from "@blesser/ui"

type Props = {
  title: string
  description: string
  action?: React.ReactNode
  illustration?: string
  compact?: boolean
  className?: string
}

/** The shared EmptyState on a surface card. */
export function EmptyState({ compact, className, ...props }: Props) {
  return (
    <div className={cn("rounded-lg bg-surface shadow-elevation-1", className)}>
      <BaseEmptyState {...props} className={cn(compact && "py-5")} />
    </div>
  )
}

/** Load-failure panel in EmptyState's layout, with an optional retry. */
export function ErrorState({ onRetry, action, compact, className, ...props }: Props & { onRetry?: () => void }) {
  return (
    <div className={cn("rounded-lg bg-surface shadow-elevation-1", className)}>
      <BaseEmptyState
        {...props}
        error
        className={cn(compact && "py-5")}
        action={
          onRetry || action ? (
            <>
              {onRetry ? (
                <Button size="sm" onClick={onRetry} icon={<RefreshCw />}>
                  Try again
                </Button>
              ) : null}
              {action}
            </>
          ) : undefined
        }
      />
    </div>
  )
}
