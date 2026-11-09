import type { ReactNode } from "react"
import { cn } from "@blesser/ui"
import { CheckIcon } from "./icons"

/** A white "product moment" pill floated over feature illustrations. */
export function FloatChip({ children, check, className }: { children: ReactNode; check?: boolean; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-full border border-separator bg-surface/95 py-2 pr-4 pl-2 text-callout font-semibold text-ink shadow-elevation-2",
        className,
      )}
    >
      {check ? (
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-forest text-on-forest [&_svg]:size-4">
          <CheckIcon />
        </span>
      ) : null}
      {children}
    </div>
  )
}

export function ChecklistChip({ done, total, className }: { done: number; total: number; className?: string }) {
  return (
    <div className={cn("w-56 rounded-lg border border-separator bg-surface/95 p-3.5 shadow-elevation-2", className)}>
      <div className="flex justify-between text-callout font-semibold text-ink">
        Checklist
        <span className="text-footnote font-normal text-ink-tertiary tabular-nums">
          {done} of {total}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-sunk">
        <div className="h-full rounded-full bg-forest" style={{ width: `${(done / total) * 100}%` }} />
      </div>
    </div>
  )
}

export function Panelled({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-lg border border-separator bg-surface/95 p-3.5 shadow-elevation-2", className)}>{children}</div>
}
