import * as React from "react"

/** Positions a `.bl-indicator` child under whichever item matches `selector`. */
export function useIndicator<T extends HTMLElement>(selector: string, key: unknown) {
  const ref = React.useRef<T>(null)
  const [ready, setReady] = React.useState(false)
  React.useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const place = () => {
      const item = root.querySelector<HTMLElement>(selector)
      root.style.setProperty("--bl-ind-x", `${item?.offsetLeft ?? 0}px`)
      root.style.setProperty("--bl-ind-w", `${item?.offsetWidth ?? 0}px`)
      root.style.setProperty("--bl-ind-top", `${item?.offsetTop ?? 0}px`)
      root.style.setProperty("--bl-ind-h", `${item?.offsetHeight ?? 0}px`)
    }
    place()
    // Fonts and counts change item widths after the first paint.
    const observer = new ResizeObserver(place)
    root.querySelectorAll(":scope > :not(.bl-indicator)").forEach((el) => observer.observe(el))
    const frame = requestAnimationFrame(() => setReady(true))
    return () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [selector, key])
  return { ref, ready }
}
