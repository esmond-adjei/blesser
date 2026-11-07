import * as React from "react"
import { Inbox, RefreshCw } from "lucide-react"
import { Button } from "../ui/button"
import { cn } from "../../lib/utils"
import { MASCOT_STATES, type MascotStateName } from "./mascotStates"

export function EmptyState({
  title,
  description,
  action,
  mascot,
  compact,
}: {
  title: string
  description: string
  action?: React.ReactNode
  /** Gradis sticker shown above the copy instead of the inbox icon. */
  mascot?: MascotStateName
  /** Tighter padding + smaller sticker for inline no-match rows. */
  compact?: boolean
}) {
  const art = mascot ? MASCOT_STATES[mascot] : null
  return (
    <div
      className={cn(
        "g-empty h-full rounded-lg bg-surface shadow-sm",
        compact && "py-6",
      )}
    >
      {art ? (
        <img
          src={art.src}
          alt={art.alt}
          loading="lazy"
          className={cn("w-auto object-contain", compact ? "h-20" : "h-28")}
        />
      ) : (
        <span className="g-icon-tile size-12 rounded-md">
          <Inbox className="size-6" strokeWidth={1.75} />
        </span>
      )}
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
  mascot = "offline",
  compact,
}: {
  title: string
  description: string
  action?: React.ReactNode
  onRetry?: () => void
  mascot?: MascotStateName
  compact?: boolean
}) {
  const art = MASCOT_STATES[mascot]
  return (
    <div
      className={cn(
        "g-empty h-full max-w-xl rounded-lg bg-card text-center shadow-sm mx-auto mt-50",
        compact && "py-6",
      )}
    >
      <img
        src={art.src}
        alt={art.alt}
        loading="lazy"
        className={cn("w-auto object-contain", compact ? "h-20" : "h-28")}
      />
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
