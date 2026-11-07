import * as React from "react"
import { cn } from "../../lib/utils"
import { initials } from "../../lib/initials"

/** Photo when a URL is known and loads, else an initials tile. */
export function Avatar({
  name,
  src,
  size = "md",
  shape = "circle",
  className,
}: {
  name: string
  src?: string | null
  size?: "sm" | "md" | "lg"
  /** Circles for people, rounded squares for institutions. */
  shape?: "circle" | "square"
  className?: string
}) {
  const round = shape === "square" ? (size === "lg" ? "rounded-xl" : "rounded-lg") : "rounded-full"
  const [failed, setFailed] = React.useState(false)
  const cls =
    size === "lg"
      ? "size-16 text-xl"
      : size === "sm"
        ? "size-8 text-xs"
        : "size-11 text-sm"
  if (src && !failed) {
    return (
      <img
        src={src}
        alt=""
        onError={() => setFailed(true)}
        // Institutions are mostly logos: show them whole on white rather
        // than cropping a crest to its middle.
        className={cn("shrink-0", shape === "square" ? "bg-white object-contain p-0.5" : "object-cover", round, cls, className)}
      />
    )
  }
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center bg-fill font-semibold tracking-[0.01em] text-label-secondary",
        round,
        cls,
        className,
      )}
    >
      {initials(name) || "?"}
    </span>
  )
}
