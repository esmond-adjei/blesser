import { cn } from "../../lib/utils"

const STYLES: Record<string, string> = {
  running: "bg-tint",
  done: "bg-positive",
  error: "bg-critical",
  pending: "bg-muted",
  deferred: "border border-dashed border-muted-foreground/50",
  paused: "bg-caution",
  cancelled: "bg-label-tertiary",
}

/** A task's status as one coloured square; it pulses while a worker runs it. */
export function TaskStatusSquare({ status, working, className }: { status: string; working?: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("size-4 shrink-0 rounded-xs", STYLES[status] ?? "bg-muted", status === "running" && working && "animate-pulse", className)}
    />
  )
}
