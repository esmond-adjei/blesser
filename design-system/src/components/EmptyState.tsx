import * as React from "react"
import { cn } from "../lib"

export interface EmptyStateProps {
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
  /** Errors keep the layout but drop the sunrise. */
  error?: boolean
  className?: string
}

/** A half sun on the horizon: the empty-state image. */
export function Sunrise({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn("relative block h-12 w-24", className)}>
      <span className="absolute inset-0 overflow-hidden">
        <span className="absolute top-0 left-0 size-24 rounded-full bg-sun" />
      </span>
      <span className="absolute -inset-x-4 bottom-0 h-0.5 bg-forest" />
    </span>
  )
}

export function EmptyState({ title, description, action, error, className }: EmptyStateProps) {
  return (
    <div
      role={error ? "alert" : undefined}
      className={cn("mx-auto flex max-w-xl flex-col items-center px-6 py-8 text-center", className)}
    >
      {error ? null : <Sunrise className="mb-1" />}
      <div className="flex flex-col items-center gap-1">
        <h2 className="m-0 type-title-2 text-ink">{title}</h2>
        {description ? <p className="m-0 text-body text-ink-secondary">{description}</p> : null}
        {action ? <div className="mt-2 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
      </div>
    </div>
  )
}
