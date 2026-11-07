import * as React from "react"

/** Enter/exit transition state for overlays. `render` stays true through the
 * exit so the closing animation can play; `shown` drives the visible end-state. */
export function useOpenTransition(open: boolean, durationMs = 200) {
  const [render, setRender] = React.useState(open)
  const [shown, setShown] = React.useState(open)

  React.useEffect(() => {
    if (open) {
      setRender(true)
      // Two frames so the browser paints the hidden state first —
      // otherwise the enter transition never runs.
      const raf = requestAnimationFrame(() =>
        requestAnimationFrame(() => setShown(true)),
      )
      return () => cancelAnimationFrame(raf)
    }
    setShown(false)
    const t = window.setTimeout(() => setRender(false), durationMs)
    return () => window.clearTimeout(t)
  }, [open, durationMs])

  return { render, shown }
}
