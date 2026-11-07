import * as React from "react"

const FADE = "2rem"

/**
 * Drives a `.scroll-fade-x` / `.scroll-fade-y` container: each edge fades
 * only while there is more to scroll to on that side. `deps` re-measures
 * when the content changes without the box resizing.
 */
export function useScrollFade<T extends HTMLElement>(axis: "x" | "y", deps: React.DependencyList = []) {
  const ref = React.useRef<T>(null)
  React.useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => {
      const pos = axis === "x" ? el.scrollLeft : el.scrollTop
      const room = axis === "x" ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight
      el.style.setProperty("--fade-start", pos > 1 ? FADE : "0px")
      el.style.setProperty("--fade-end", room - pos > 1 ? FADE : "0px")
    }
    update()
    el.addEventListener("scroll", update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      el.removeEventListener("scroll", update)
      ro.disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [axis, ...deps])
  return ref
}

/**
 * Fits an element to the viewport below where it starts, so what's inside
 * scrolls instead of the page. Re-measures as the window or page resizes.
 */
export function useFillViewport<T extends HTMLElement>(gap = 24, min = 360) {
  const ref = React.useRef<T>(null)
  React.useEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      el.style.height = `${Math.max(min, window.innerHeight - el.getBoundingClientRect().top - gap)}px`
    }
    fit()
    window.addEventListener("resize", fit)
    const ro = new ResizeObserver(fit)
    ro.observe(document.body)
    return () => {
      window.removeEventListener("resize", fit)
      ro.disconnect()
    }
  }, [gap, min])
  return ref
}
