import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../lib/utils"

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("g-skeleton", className)} {...props} />
}

/** Placeholder blocks in a column; each entry is one block's size classes. */
export function SkeletonStack({ blocks, ...props }: { blocks: string[] } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...props}>
      {blocks.map((b, i) => <Skeleton key={i} className={b} />)}
    </div>
  )
}

export function DetailSkeleton({ className }: { className?: string }) {
  return (
    <div aria-label="Loading details" aria-busy="true" className={cn("mx-auto max-w-4xl space-y-4", className)}>
      <div className="rounded-lg bg-surface p-5 shadow-sm">
        <div className="flex items-center gap-4">
          <Skeleton className="size-14 shrink-0 rounded-full" />
          <div className="w-full space-y-2"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-4 w-2/3" /></div>
        </div>
      </div>
      <div className="space-y-3 rounded-lg bg-surface p-5 shadow-sm">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  )
}

/** A page's shape while its route code loads: title, toolbar, a few rows. */
export function PageSkeleton({ className }: { className?: string }) {
  return (
    <div aria-label="Loading page" aria-busy="true" className={cn("mx-auto w-full max-w-5xl space-y-4 px-4 py-6", className)}>
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-16 w-full" />)}
    </div>
  )
}

/** Inline banner; the ground carries the tone, the text stays label ink. */
const alertVariants = cva("g-banner relative w-full [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0", {
  variants: {
    variant: {
      default: "",
      info: "g-banner--info [&>svg]:text-tint",
      caution: "g-banner--caution [&>svg]:text-caution",
      destructive: "g-banner--critical [&>svg]:text-critical",
    },
  },
  defaultVariants: { variant: "default" },
})

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

export function Alert({ className, variant, ...props }: AlertProps) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h5 className={cn("mb-0.5 font-semibold", className)} {...props} />
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 flex-1", className)} {...props} />
}
