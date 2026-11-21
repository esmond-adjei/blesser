import { useEffect, useState } from "react"

/** Keeps an overlay mounted through its exit: `render` mounts it, `shown` drives the visible state. */
export function useOpenTransition(open: boolean, durationMs = 200) {
  const [render, setRender] = useState(open)
  const [shown, setShown] = useState(open)
  useEffect(() => {
    if (open) {
      setRender(true)
      // Two frames so the hidden state paints first and the enter transition runs.
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setShown(true)))
      return () => cancelAnimationFrame(frame)
    }
    setShown(false)
    const timer = window.setTimeout(() => setRender(false), durationMs)
    return () => window.clearTimeout(timer)
  }, [open, durationMs])
  return { render, shown }
}
