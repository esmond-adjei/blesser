import { useCallback, useState } from "react"

function load(key: string, fallback: number) {
  try {
    const value = Number(localStorage.getItem(key))
    return Number.isFinite(value) && value > 0 ? value : fallback
  } catch {
    return fallback
  }
}

/** A pixel size that survives reloads, clamped to a range. */
export function usePaneSize(key: string, fallback: number, min: number, max: number) {
  const [size, setSize] = useState(() => Math.min(Math.max(load(key, fallback), min), max))
  const update = useCallback((next: number) => {
    const clamped = Math.min(Math.max(next, min), max)
    setSize(clamped)
    try {
      localStorage.setItem(key, String(Math.round(clamped)))
    } catch {
      // A size that isn't remembered resets on reload; that is all.
    }
  }, [key, min, max])
  return [size, update] as const
}
