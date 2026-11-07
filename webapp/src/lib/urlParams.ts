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

/** Rail selection for listing pages: `?preview=<id>` opens the shell detail rail.
 * Pushes on open (so back closes) and replaces on close. Full detail pages live
 * at `/:id`; the preview param never navigates away from the listing. */
export function usePreviewParam(): {
  previewId: string | null
  openPreview: (id: string) => void
  closePreview: () => void
} {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const previewId = searchParams.get("preview") || null

  const openPreview = React.useCallback(
    (id: string) => {
      if (searchParams.get("preview") === id) return
      const search = new URLSearchParams(searchParams)
      search.set("preview", id)
      navigate({ pathname, search: search.toString() })
    },
    [navigate, pathname, searchParams],
  )

  const closePreview = React.useCallback(() => {
    const search = new URLSearchParams(searchParams)
    search.delete("preview")
    navigate({ pathname, search: search.toString() }, { replace: true })
  }, [navigate, pathname, searchParams])

  return { previewId, openPreview, closePreview }
}
