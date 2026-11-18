import { cn } from "../lib"

/** The lowercase "blesser" set beside the logo; size it with a text-* class. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-sans text-[27px] leading-none font-extrabold tracking-[-0.04em] text-[var(--logo-ink,#0f4f3b)]", className)}>
      blesser
    </span>
  )
}
