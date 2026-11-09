import * as React from "react"
import { cva } from "class-variance-authority"
import { cn } from "../lib"

export type ChipTone = "neutral" | "forest" | "sun" | "bloom" | "info" | "caution" | "critical"

export const chipVariants = cva(
  "inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 text-caption whitespace-nowrap [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "bg-surface-sunk text-ink-secondary",
        forest: "bg-forest-soft text-link",
        sun: "bg-sun-soft text-sun-ink",
        bloom: "bg-bloom-soft text-bloom-ink",
        info: "bg-info-soft text-info",
        caution: "bg-caution-soft text-caution",
        critical: "bg-critical-soft text-critical",
      },
      pressable: {
        false: "h-6",
        true: "h-8 cursor-pointer border-0 px-3 transition-colors duration-160 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-pressed:bg-forest-soft aria-pressed:text-link aria-pressed:shadow-[inset_0_0_0_1px_var(--forest)]",
      },
    },
    defaultVariants: { tone: "neutral", pressable: false },
  },
)

export interface ChipProps {
  tone?: ChipTone
  icon?: React.ReactNode
  /** Makes the chip a filter toggle. */
  onClick?: () => void
  selected?: boolean
  className?: string
  children: React.ReactNode
}

export function Chip({ tone, icon, onClick, selected, className, children }: ChipProps) {
  if (onClick)
    return (
      <button
        type="button"
        aria-pressed={!!selected}
        onClick={onClick}
        className={cn(chipVariants({ tone, pressable: true }), !selected && "hover:bg-separator", className)}
      >
        {icon}
        {children}
      </button>
    )
  return (
    <span className={cn(chipVariants({ tone }), className)}>
      {icon}
      {children}
    </span>
  )
}
