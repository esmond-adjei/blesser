import { cn } from "../../lib/utils"

/** A four-point spark on the tint: an opportunity caught in the light. */
export function AppLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" role="img" aria-label="Blesser logo" className={cn("size-9 shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill="var(--tint)" />
      <path
        d="M16 5.5c.9 4.9 2.6 6.6 7.5 7.5v.1c-4.9.9-6.6 2.6-7.5 7.5h-.1c-.9-4.9-2.6-6.6-7.5-7.5V13c4.9-.9 6.6-2.6 7.5-7.5Z"
        fill="#fff"
      />
      <circle cx="23" cy="23" r="2.2" fill="#fff" opacity="0.85" />
    </svg>
  )
}
