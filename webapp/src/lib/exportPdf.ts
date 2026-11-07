import * as React from "react"
import * as api from "./api"
import { saveFile } from "./download"
import { toastError, toastSuccess } from "./toast"

/** Mirrors MAX_CANDIDATES in api/api/exports/service.py. */
const MAX_CANDIDATES = 100

/** Export candidates as one branded PDF: a single dossier, or a cover,
 * contents and a section each. `exporting` covers the request. */
export function useExportPdf() {
  const [exporting, setExporting] = React.useState(false)
  const exportPdf = React.useCallback(async (candidateIds: string[]) => {
    if (candidateIds.length === 0) return
    if (candidateIds.length > MAX_CANDIDATES) {
      toastError(`At most ${MAX_CANDIDATES} candidates fit in one PDF. Export in batches.`)
      return
    }
    setExporting(true)
    try {
      const { blob, filename } = await api.exportCandidatesPdf(candidateIds)
      saveFile(blob, filename)
      toastSuccess(candidateIds.length === 1 ? "Dossier exported" : `${candidateIds.length} dossiers exported in one PDF`)
    } catch (err) {
      toastError(err)
    } finally {
      setExporting(false)
    }
  }, [])
  return { exporting, exportPdf }
}
