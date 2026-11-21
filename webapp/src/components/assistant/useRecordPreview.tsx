import { useCallback, useMemo, useState } from "react"
import type { AssistantSource } from "../../lib/assistant"
import { RecordPreview, type Ref } from "./RecordPreview"

/** Opens a record from the chat in a side sheet, using the same sheets as the pages the record lives on. */
export function useRecordPreview() {
  const [ref, setRef] = useState<Ref | null>(null)
  const open = useCallback((source: AssistantSource) => setRef({ kind: source.kind, id: source.id, slug: source.opportunity?.slug }), [])
  const close = useCallback(() => setRef(null), [])
  const node = useMemo(() => <RecordPreview target={ref} onClose={close} onSwap={setRef} />, [ref, close])
  return { open, node }
}
