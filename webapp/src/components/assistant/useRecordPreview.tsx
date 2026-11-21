import { useCallback, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import type { AssistantSource } from "../../lib/assistant"
import { RecordPreview, type Ref } from "./RecordPreview"

const PAGES: Partial<Record<AssistantSource["kind"], (source: AssistantSource) => string | undefined>> = {
  scan: (source) => `/scans/${encodeURIComponent(source.id)}`,
  site: () => "/scans",
  saved_search: () => "/settings/matching",
  profile: () => "/kit/profile",
  settings: (source) => `/settings/${encodeURIComponent(source.id)}`,
}

/** Opens a record from the chat: in a side sheet when it has one, otherwise on the page it lives on. */
export function useRecordPreview() {
  const navigate = useNavigate()
  const [ref, setRef] = useState<Ref | null>(null)
  const open = useCallback((source: AssistantSource) => {
    const page = PAGES[source.kind]?.(source)
    if (page) return navigate(page)
    if (source.kind === "find") {
      if (source.url) window.open(source.url, "_blank", "noopener,noreferrer")
      return
    }
    setRef({ kind: source.kind, id: source.id, slug: source.opportunity?.slug })
  }, [navigate])
  const close = useCallback(() => setRef(null), [])
  const node = useMemo(() => <RecordPreview target={ref} onClose={close} onSwap={setRef} />, [ref, close])
  return { open, node }
}
