import { cn } from "../lib"

export type LogoVariant = "mark" | "symbol" | "symbol-white"

export interface LogoProps {
  variant?: LogoVariant
  className?: string
  /** Accessible name; pass "" when a visible wordmark sits beside it. */
  title?: string
}

const STEPS = "M7.75 22.5h6.5a2.25 2.25 0 0 1 0 4.5h-6.5a2.25 2.25 0 0 1 0-4.5Zm5 -6h4.5a2.25 2.25 0 0 1 0 4.5h-4.5a2.25 2.25 0 0 1 0-4.5Z"
const TOP_STEP = "M17.75 10.5h2.5a2.25 2.25 0 0 1 0 4.5h-2.5a2.25 2.25 0 0 1 0-4.5Z"

/** The Path: three steps climbing to the sun. Brand colours are fixed, not themed. */
export function Logo({ variant = "mark", className, title = "Blesser" }: LogoProps) {
  const label = title ? { role: "img", "aria-label": title } : { "aria-hidden": true }
  if (variant === "mark")
    return (
      <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", className)} {...label}>
        <rect width="32" height="32" rx="10" fill="#0f4f3b" />
        <path d={STEPS} fill="#ffffff" />
        <path d={TOP_STEP} fill="#ff7d66" />
        <circle cx="24.5" cy="7.5" r="3.25" fill="#ffbe1a" />
      </svg>
    )
  const fill = variant === "symbol-white" ? "#ffffff" : "#0f4f3b"
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", className)} {...label}>
      <path d={STEPS + TOP_STEP} fill={fill} />
      <circle cx="24.5" cy="7.5" r="3.25" fill={fill} />
    </svg>
  )
}
