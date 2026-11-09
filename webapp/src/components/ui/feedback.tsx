import * as React from "react"
import { cn } from "@blesser/ui"

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-surface-sunk motion-reduce:animate-none", className)} {...props} />
}

export function SkeletonStack({ blocks, ...props }: { blocks: string[] } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...props}>
      {blocks.map((b, i) => <Skeleton key={i} className={b} />)}
    </div>
  )
}

const ALERT_TONES = {
  info: "bg-info-soft [&>svg]:text-info",
  caution: "bg-caution-soft [&>svg]:text-caution",
  destructive: "bg-critical-soft [&>svg]:text-critical",
}

export function Alert({
  className,
  variant = "info",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { variant?: keyof typeof ALERT_TONES }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex w-full gap-2.5 rounded-md px-3.5 py-3 text-callout text-ink [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0",
        ALERT_TONES[variant],
        className,
      )}
      {...props}
    />
  )
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 flex-1", className)} {...props} />
}
