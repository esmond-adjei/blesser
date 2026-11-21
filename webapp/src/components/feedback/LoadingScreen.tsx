import { Logo, cn } from "@blesser/ui"

/** Page wait. `fill` sizes to the space it's in, under the app's top bar. The Climb loop fades in after 400ms, so quick loads show nothing. */
export function LoadingScreen({ fill }: { fill?: boolean }) {
  return (
    <div className={cn("flex items-center justify-center", fill ? "min-h-0 flex-1" : "min-h-dvh")} role="status" aria-label="Loading">
      <Logo title="" motion="climb" className="size-10" />
    </div>
  )
}
