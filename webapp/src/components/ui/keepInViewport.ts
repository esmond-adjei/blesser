import * as React from "react"

const VIEWPORT_MARGIN = 8

/** Nudges an absolutely placed dropdown sideways by its overflow so it stays on screen; re-fits on resize. */
export function useKeepInViewport(ref: React.RefObject<HTMLElement | null>, open: boolean) {
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!open || !el) return
    const fit = () => {
      // Measure from the CSS anchor, not the last nudge.
      el.style.translate = ""
      const r = el.getBoundingClientRect()
      const room = window.innerWidth - VIEWPORT_MARGIN
      const dx =
        r.left < VIEWPORT_MARGIN
          ? VIEWPORT_MARGIN - r.left
          : r.right > room
            ? -Math.min(r.right - room, r.left - VIEWPORT_MARGIN)
            : 0
      if (dx) el.style.translate = `${dx}px 0`
    }
    fit()
    window.addEventListener("resize", fit)
    return () => window.removeEventListener("resize", fit)
  }, [ref, open])
}
