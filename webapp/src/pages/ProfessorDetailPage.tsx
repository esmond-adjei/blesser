import { Navigate, useLocation, useParams } from "react-router-dom"
import { useProfessor } from "../lib/queries"
import { ProfessorDetailView } from "../components/dossier/ProfessorDetailView"
import { ErrorState } from "../components/feedback/EmptyState"
import { DetailSkeleton } from "../components/ui/feedback"
import { CheckMatchButton } from "../components/dialogs/MatchProfessorDialog"

export function ProfessorDetailPage() {
  const { professorId } = useParams()
  // Kept through the redirect, so ?paper= still opens its paper.
  const { search } = useLocation()
  const { data, isLoading, isError } = useProfessor(professorId ?? null)
  if (isLoading) return <DetailSkeleton />
  if (isError || !data) return <ErrorState title="Professor not found" description="This professor may have been deleted." />
  if (data.candidate_id) return <Navigate to={`/dossier/${data.candidate_id}${search}`} replace />
  return <div className="mx-auto max-w-4xl"><ProfessorDetailView size="page" professor={data} actions={data.papers.length > 0 && <CheckMatchButton professor={data} />} /></div>
}
