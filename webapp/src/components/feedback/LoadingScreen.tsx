import { Logo } from "@blesser/ui"

/** Full-page wait. The Climb loop fades in after 400ms, so quick loads show nothing. */
export function LoadingScreen() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <Logo title="" motion="climb" className="size-10" />
    </div>
  )
}
