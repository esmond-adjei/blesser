import { Logo } from "@blesser/ui"

export function LoadingScreen() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <Logo title="" className="size-10 animate-pulse motion-reduce:animate-none" />
    </div>
  )
}
