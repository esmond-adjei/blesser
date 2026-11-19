import * as React from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router-dom"

/** Filter state in the URL query string, so it is shareable and survives reload
 * and back/forward. Missing params read as `initial`; writing it removes the
 * param; writes use `replace` so keystrokes don't stack history entries. */
export function useSetUrlParam(): (key: string, value: string) => void {
  const [, setParams] = useSearchParams()
  return React.useCallback(
    (key: string, value: string) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (value) next.set(key, value)
          else next.delete(key)
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )
}

/** Query param as state. See `useSetUrlParam` for the conventions. */
export function useUrlParam(key: string, initial = ""): [string, (next: string) => void] {
  const [params] = useSearchParams()
  const setParam = useSetUrlParam()
  const value = params.get(key) ?? initial
  const set = React.useCallback(
    (next: string) => setParam(key, next === initial ? "" : next),
    [key, initial, setParam],
  )
  return [value, set]
}

/** Drawer selection for listing pages: `?open=<id>` opens that record's sheet.
 * Opening pushes a history entry so Back closes the sheet; closing replaces the
 * entry, so dismissing it does not stack another one. Full detail pages live at
 * `/:id`; the param never navigates away from the listing. */
export function useDrawerParam(key = "open"): {
  id: string | null
  open: (id: string) => void
  close: () => void
} {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const id = searchParams.get(key) || null

  const open = React.useCallback(
    (next: string) => {
      if (searchParams.get(key) === next) return
      const search = new URLSearchParams(searchParams)
      search.set(key, next)
      navigate({ pathname, search: search.toString() })
    },
    [key, navigate, pathname, searchParams],
  )

  const close = React.useCallback(() => {
    const search = new URLSearchParams(searchParams)
    search.delete(key)
    navigate({ pathname, search: search.toString() }, { replace: true })
  }, [key, navigate, pathname, searchParams])

  return { id, open, close }
}
