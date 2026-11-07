import * as React from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router-dom"

/** Busy state for a row menu's actions. Rows have no error surface, so
 * failures stay silent and show on the record's own page. Removing the
 * record open in the preview rail closes the rail, on whatever page hosts it. */
export function useRowActions(refresh: () => Promise<unknown>, isActive: boolean) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const [busy, setBusy] = React.useState<string | null>(null)

  async function run(action: string, fn: () => Promise<unknown>, after?: () => void) {
    setBusy(action)
    try {
      await fn()
      await refresh()
      after?.()
    } catch {
      // Silent: see above.
    } finally {
      setBusy(null)
    }
  }

  function remove(fn: () => Promise<unknown>) {
    return run("delete", fn, () => {
      if (!isActive) return
      const search = new URLSearchParams(searchParams)
      search.delete("preview")
      navigate({ pathname, search: search.toString() }, { replace: true })
    })
  }

  return { busy, run, remove }
}
