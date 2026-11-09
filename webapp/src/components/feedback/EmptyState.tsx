import * as React from "react"
import { RefreshCw } from "lucide-react"
import { Button, cn } from "@blesser/ui"

type Props = {
  title: string
  description: string
  action?: React.ReactNode
  illustration?: string
  compact?: boolean
  className?: string
}

function Panel({ title, description, action, illustration, compact, className, error }: Props & { error?: boolean }) {
  return (
    <div
      role={error ? "alert" : undefined}
      className={cn(
        "flex flex-col items-center gap-1 rounded-lg border border-separator bg-surface px-6 text-center",
        compact ? "py-5" : "py-10",
        className,
      )}
    >
      {illustration && !compact ? <img src={illustration} alt="" className="mb-2 h-24 w-auto max-w-full opacity-90" /> : null}
      <h2 className="text-headline text-ink">{title}</h2>
      <p className="max-w-md text-footnote text-ink-secondary">{description}</p>
      {action ? <div className="mt-3 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  )
}

export function EmptyState(props: Props) {
  return <Panel {...props} />
}

/** Load-failure panel with an optional retry. */
export function ErrorState({ onRetry, action, ...props }: Props & { onRetry?: () => void }) {
  return (
    <Panel
      {...props}
      illustration={undefined}
      error
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
  )
}
