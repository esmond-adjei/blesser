import { useCandidate, useRunDrafts } from "../../lib/queries"
import { CandidateRowMenu } from "../dossier/CandidateRowMenu"
import { DraftRowMenu } from "../outbox/DraftRowMenu"

/** Reads live data by id: rails republish only on id changes, so a captured row would go stale. */
export function CandidatePreviewActions({ candidateId }: { candidateId: string }) {
  const { data } = useCandidate(candidateId)
  if (!data) return null
  return <CandidateRowMenu variant="header" candidate={data} runId={data.run_id} isActive />
}

export function DraftPreviewActions({ draftId, runId }: { draftId: string; runId: string }) {
  const { data } = useRunDrafts(runId)
  const draft = data?.find((d) => d.id === draftId)
  if (!draft) return null
  return <DraftRowMenu variant="header" draft={draft} runId={runId} isActive />
}
