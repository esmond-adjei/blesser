import * as React from "react"
import { useAutosave } from "./autosave"

/** A local draft that saves itself a moment after edits stop, one save at a time, and once more on unmount. */
export function useDraft<T, P>(
  initial: T,
  toPayload: (value: T) => P,
  save: (payload: P) => Promise<unknown>,
  { delay = 900, canSave = () => true }: { delay?: number; canSave?: (payload: P) => boolean } = {},
) {
  const track = useAutosave()
  const [draft, setDraft] = React.useState(initial)
  const latest = React.useRef(draft)
  const saved = React.useRef(JSON.stringify(toPayload(initial)))
  const chain = React.useRef<Promise<unknown>>(Promise.resolve())
  const fns = React.useRef({ toPayload, save, track, canSave })
  React.useLayoutEffect(() => {
    fns.current = { toPayload, save, track, canSave }
    latest.current = draft
  })

  const flush = React.useCallback(() => {
    chain.current = chain.current.then(async () => {
      const payload = fns.current.toPayload(latest.current)
      const key = JSON.stringify(payload)
      if (key === saved.current || !fns.current.canSave(payload)) return
      const ok = await fns.current.track(fns.current.save(payload).then(() => true))
      if (ok) saved.current = key
    })
    return chain.current
  }, [])

  React.useEffect(() => {
    if (JSON.stringify(fns.current.toPayload(draft)) === saved.current) return
    const timer = window.setTimeout(() => void flush(), delay)
    return () => window.clearTimeout(timer)
  }, [draft, delay, flush])

  React.useEffect(() => () => void flush(), [flush])

  const update = React.useCallback((change: Partial<T> | ((prev: T) => T)) => {
    setDraft((prev) => (typeof change === "function" ? change(prev) : { ...prev, ...change }))
  }, [])

  /** Forget unsaved edits, e.g. before deleting the record. */
  const discard = React.useCallback(() => {
    saved.current = JSON.stringify(fns.current.toPayload(latest.current))
  }, [])

  return { draft, update, flush, discard }
}
