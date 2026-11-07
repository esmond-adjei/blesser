import type * as React from "react"
import { cn } from "../../lib/utils"

/** The open button covering a card; content sits above it without taking clicks. */
export function Cover({ label, onOpen }: { label: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      className="absolute inset-0 z-0 cursor-pointer rounded-[inherit] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]"
    />
  )
}

/** Children opt out of clicks (`pointer-events-none relative`) so the Cover gets them; a menu goes on top with its own z-index. */
export function CoverCard({
  label,
  onOpen,
  active,
  className,
  children,
  ...rest
}: {
  label: string
  onOpen: () => void
  active?: boolean
  className?: string
  children: React.ReactNode
} & Omit<React.HTMLAttributes<HTMLDivElement>, "className" | "children">) {
  return (
    <div className={cn("g-ecard group relative", className)} data-interactive="" aria-selected={active || undefined} {...rest}>
      <Cover label={label} onOpen={onOpen} />
      {children}
    </div>
  )
}
