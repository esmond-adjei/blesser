import { Landmark, Link as LinkIcon, Target, Users } from "lucide-react"
import { useProgram, useRunSchools, useRunScores } from "../../lib/queries"
import { Alert, AlertDescription, SkeletonStack } from "../ui/feedback"
import { EmptyNote, ReadingSection, ReadingSurface } from "../ui/reading"
import { DetailHeader } from "../entity/detail"
import { CardGrid, PersonCard } from "../cards/EntityCards"
import { useOpenRecord } from "../layout/openRecord"
import { FactList } from "../entity/facts"
import { SchoolImage } from "../entity/SchoolImage"

/** The full faculty listing is the rail header's "Open as page". */
export function SavedProgramPanel({ programId, runId }: { programId: string; runId: string }) {
  const { data: program, isLoading, isError } = useProgram(programId)
  const { data: schools } = useRunSchools(runId)
  const scores = useRunScores(runId)
  const { open } = useOpenRecord()
  if (isLoading) {
    return <SkeletonStack className="space-y-4" blocks={["h-24", "h-40"]} />
  }
  if (isError || !program) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Couldn't load this program. It may have been deleted.</AlertDescription>
      </Alert>
    )
  }
  const school = schools?.find((s) => s.id === program.school_id)
  const scored = program.professors.filter((p) => scores.has(p.id)).length
  return (
    <ReadingSurface>
      <DetailHeader
        size="panel"
        banner={school?.image_url ? <SchoolImage src={school.image_url} name={school.name} variant="banner-sm" /> : undefined}
        title={program.name}
        identity={[{ icon: Landmark, value: program.school_name }]}
      >
        <FactList
          facts={[
            { icon: Users, value: `${program.professors.length} faculty` },
            scored > 0 && { icon: Target, value: `${scored} scored` },
            program.department_url && { icon: LinkIcon, value: "Department page", href: program.department_url },
          ]}
        />
      </DetailHeader>
      <ReadingSection title="Faculty" meta={program.professors.length || undefined}>
        {program.professors.length === 0 ? (
          <EmptyNote>No professors yet.</EmptyNote>
        ) : (
          <CardGrid>
            {program.professors.map((p) => {
              const c = scores.get(p.id)
              const ref = c ? ({ kind: "candidate", id: c.id } as const) : ({ kind: "professor", id: p.id } as const)
              return (
                <PersonCard
                  key={p.id}
                  name={p.name}
                  photo={p.photo_url}
                  subtitle={p.lab_name || undefined}
                  status={c?.status}
                  score={c ? c.similarity_score : null}
                  onOpen={() => open(ref, p.name)}
                />
              )
            })}
          </CardGrid>
        )}
      </ReadingSection>
    </ReadingSurface>
  )
}
