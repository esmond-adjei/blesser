import { MASCOT_STATES } from "./mascotStates"

/** The group sits slightly above and left of centre to look optically centred. */
export function LoadingScreen() {
  return (
    <div role="status" aria-live="polite" className="fixed inset-0 z-50 grid place-items-center bg-background">
      <div className="flex -translate-y-[6%] flex-col items-center gap-3 text-center">
        <img
          src={MASCOT_STATES.loading.src}
          alt=""
          aria-hidden
          width={84}
          height={128}
          className="h-32 w-auto -translate-x-[1.4%] animate-pulse object-contain motion-reduce:animate-none"
        />
        <p className="type-meta">Loading…</p>
      </div>
    </div>
  )
}
