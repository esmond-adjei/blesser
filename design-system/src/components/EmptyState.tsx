import * as React from "react"
import { cn } from "../lib"

export interface EmptyStateProps {
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
  /** Image src shown instead of the sunrise. */
  illustration?: string
  /** Errors keep the layout but drop the sunrise. */
  error?: boolean
  className?: string
}

export function EmptyState({ title, description, action, illustration, error, className }: EmptyStateProps) {
  return (
    <div
      role={error ? "alert" : undefined}
      className={cn("mx-auto flex max-w-[420px] flex-col items-center gap-3 px-6 py-8 text-center", className)}
    >
      {illustration ? (
        <img src={illustration} alt="" className="mb-1 h-32 w-auto max-w-full" />
      ) : error ? null : (
        <span aria-hidden="true" className="relative mb-1 block h-12 w-24">
          <span className="absolute inset-0 overflow-hidden">
            <span className="absolute top-0 left-0 size-24 rounded-full bg-sun" />
          </span>
          <span className="absolute -inset-x-4 bottom-0 h-0.5 bg-forest" />
        </span>
      )}
      <h2 className="m-0 type-title-2 text-ink">{title}</h2>
      {description ? <p className="m-0 text-body text-ink-secondary">{description}</p> : null}
      {action ? <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  )
}
