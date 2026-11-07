import * as React from "react"

function loadWidth(key: string, fallback: number): number {
  try {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch {
    return fallback
  }
}

/** Storage key scoped to the route's first path segment, so each area
 * remembers its pane width: `/runs/x` -> `<base>:runs`, `/` -> `<base>:home`. */
export function routeScopedKey(base: string, pathname: string): string {
  const segment = pathname.split("/").find(Boolean) ?? "home"
  return `${base}:${segment}`
}

/** Persisted pixel width with clamping. A changed `storageKey` reloads that
 * key's width, or starts at `fallback` if none. */
export function usePaneWidth(storageKey: string, fallback: number, min: number, max: number) {
  const [state, setState] = React.useState(() => ({ key: storageKey, width: loadWidth(storageKey, fallback) }))
  let width = state.width
  if (state.key !== storageKey) {
    // Adjust during render (not in an effect) so the new route never
    // paints a frame at the previous route's width.
    width = loadWidth(storageKey, fallback)
    setState({ key: storageKey, width })
  }

  const setWidth = React.useCallback(
    (w: number) => {
      const next = Math.min(Math.max(w, min), max)
      setState({ key: storageKey, width: next })
      try {
        localStorage.setItem(storageKey, String(Math.round(next)))
      } catch {
        /* ignore */
      }
    },
    [storageKey, min, max],
  )

  return { width, setWidth }
}
