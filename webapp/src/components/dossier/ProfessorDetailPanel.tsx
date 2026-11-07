import { useProfessor } from "../../lib/queries"
import { Alert, AlertDescription, SkeletonStack } from "../ui/feedback"
import { DossierDetailPanel } from "./DossierDetailPanel"
import { ProfessorDetailView } from "./ProfessorDetailView"
import { CheckMatchButton } from "../dialogs/MatchProfessorDialog"

/** A scored professor hands off to the dossier preview. */
export function ProfessorDetailPanel({ professorId }: { professorId: string }) {
  const { data: prof, isLoading, isError } = useProfessor(professorId)

  if (isLoading) {
    return <SkeletonStack className="space-y-4" blocks={["h-20", "h-40"]} />
  }
  if (isError || !prof) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Couldn't load this professor. They may have been deleted.</AlertDescription>
      </Alert>
    )
  }
  if (prof.candidate_id) return <DossierDetailPanel candidateId={prof.candidate_id} />
  return <ProfessorDetailView size="panel" professor={prof} actions={prof.papers.length > 0 && <CheckMatchButton professor={prof} />} />
}
