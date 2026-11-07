import * as React from "react"
import { cn } from "../../lib/utils"

/** Reading-surface primitives: hierarchy through type and spacing, with borders reserved for interactive controls. */

export function ReadingSurface({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-7", className)} {...props} />
}

export function ReadingSection({
  title,
  meta,
  action,
  children,
  className,
}: {
  title: React.ReactNode
  meta?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={className}>
      <div className="mb-2 flex min-h-7 items-center gap-2">
        <h3 className="type-section-title">
          {title}
          {meta != null && <span className="ml-1.5 font-normal text-muted-foreground">{meta}</span>}
        </h3>
        {action && <div className="ml-auto flex items-center gap-1">{action}</div>}
      </div>
      {children}
    </section>
  )
}

export function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground">{children}</p>
}
