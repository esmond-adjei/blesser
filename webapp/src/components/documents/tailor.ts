import * as api from "../../lib/api"
import type { CvDocumentDetail } from "../../lib/types"
import { type DocumentDraft, listDrafts, loadCopy, newDraftId, storeDraft } from "./documentLocal"
import { KIND, kindOf } from "./kinds"

/** The variant already saved for them, else the device draft, else a new draft; nothing
 * is created on the server until "Save variant". */
export async function tailoredPath(user: string, doc: CvDocumentDetail, candidateId: string): Promise<string> {
  const saved = doc.versions.find((v) => v.candidate_id === candidateId)
  if (saved) return `/documents/${doc.id}?version=${saved.id}`
  const kept = listDrafts(user).find((d) => d.documentId === doc.id && d.candidateId === candidateId)
  if (kept) return `/documents/${doc.id}?draft=${kept.id}`
  const what = KIND[kindOf(doc.kind)]
  let name = `Tailored ${what.noun}`
  let label: string | null = null
  try {
    const c = await api.getCandidate(candidateId)
    name = `${what.label} for ${c.professor_name}`
    label = [c.professor_name, c.school_name].filter(Boolean).join(", ") || null
  } catch {
    /* named generically; the server links the professor on save */
  }
  return `/documents/${doc.id}?draft=${startDraft(user, doc, { candidateId, name, targetLabel: label }).id}`
}

export function startDraft(
  user: string,
  doc: CvDocumentDetail,
  opts: { candidateId: string | null; name: string; targetLabel: string | null },
): DocumentDraft {
  const now = Date.now()
  const draft: DocumentDraft = {
    id: newDraftId(),
    documentId: doc.id,
    candidateId: opts.candidateId,
    name: opts.name,
    targetLabel: opts.targetLabel,
    // Edits to the base CV not yet synced count: it's the text on screen.
    markdown: loadCopy(user, { kind: "doc", id: doc.id })?.markdown ?? doc.markdown,
    createdAt: now,
    updatedAt: now,
  }
  storeDraft(user, draft)
  return draft
}

/** A file name like the server's (api/cv/service.py:_safe_name). */
export function safeName(title: string): string {
  const name = title.replace(/[^A-Za-z0-9 ._-]+/g, "").replace(/^[ .]+|[ .]+$/g, "")
  return (name || "CV").slice(0, 80)
}
