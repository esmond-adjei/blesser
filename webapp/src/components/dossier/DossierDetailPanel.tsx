import { useCandidate, useProfessor } from "../../lib/queries"
import { Alert, AlertDescription, SkeletonStack } from "../ui/feedback"
import { ProfessorDetailView } from "./ProfessorDetailView"

/** Loads by candidate id so a stale listing can't leak in; remounts per selection. */
export function DossierDetailPanel({ candidateId }: { candidateId: string }) {
  const { data: c, isLoading, isError } = useCandidate(candidateId)
  const { data: prof } = useProfessor(c?.professor_id ?? null)

  if (isLoading) {
    return <SkeletonStack className="space-y-4" blocks={["h-20", "h-40"]} />
  }
  if (isError || !c) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Couldn't load this match. It may have been discarded. Pick another professor on the left.
        </AlertDescription>
      </Alert>
    )
  }
  return <ProfessorDetailView size="panel" candidate={c} professor={prof} />
}
