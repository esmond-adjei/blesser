import * as React from "react"

/** While `open`, a mousedown outside `ref` or Escape calls `onDismiss`. */
export function useDismiss(open: boolean, ref: React.RefObject<HTMLElement | null>, onDismiss: () => void) {
  const dismiss = React.useRef(onDismiss)
  React.useLayoutEffect(() => {
    dismiss.current = onDismiss
  })
  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) dismiss.current()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss.current()
    }
    document.addEventListener("mousedown", onDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open, ref])
}
