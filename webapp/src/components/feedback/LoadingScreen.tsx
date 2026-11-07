import { AppLogo } from "../layout/AppLogo"

export function LoadingScreen() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <AppLogo className="size-10 animate-pulse" />
    </div>
  )
}
