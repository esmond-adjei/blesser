import { Logo, cn } from "@blesser/ui"

/** `fill` sizes to the space it's in instead of the whole viewport, for use under the app's top bar. */
export function LoadingScreen({ fill }: { fill?: boolean }) {
  return (
    <div className={cn("flex items-center justify-center", fill ? "min-h-0 flex-1" : "min-h-dvh")} role="status" aria-label="Loading">
      <Logo title="" className="size-10 animate-pulse motion-reduce:animate-none" />
    </div>
  )
}
