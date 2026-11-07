import * as React from "react"
import { Link, useParams } from "react-router-dom"
import { Activity, Landmark, Link as LinkIcon, Target, Users } from "lucide-react"
import { useProgram, useRun, useRunSchools, useRunScores } from "../lib/queries"
import { runTitle } from "../lib/format"
import { useUrlParam } from "../lib/urlParams"
import { plural } from "../lib/entities"
import { DetailSkeleton } from "../components/ui/feedback"
import { EmptyNote, ReadingSection, ReadingSurface } from "../components/ui/reading"
import { DetailHeader } from "../components/entity/detail"
import { CardGrid, PersonCard } from "../components/cards/EntityCards"
import { useOpenRecord } from "../components/layout/openRecord"
import { FactList } from "../components/entity/facts"
import { SchoolImage } from "../components/entity/SchoolImage"
import { HealthBanner } from "../components/layout/AppShell"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { SearchInput } from "../components/filters/SearchInput"
import { useDetailPanel } from "../components/layout/DetailPanel"

export function ProgramProfessors() {
  const { runId, programId } = useParams<{
    runId?: string
    programId?: string
  }>()
  // Search lives in the URL (?q=) so it survives opening a professor.
  const [query, setQuery] = useUrlParam("q")
  const { data: run } = useRun(runId ?? "")
  const { data: program, isLoading, isError } = useProgram(programId ?? null)
  const { clearPanel } = useDetailPanel()
  const { open, isOpen } = useOpenRecord()

  React.useEffect(() => () => clearPanel(), [clearPanel])

  const q = query.trim().toLowerCase()
  const professors = program?.professors ?? []
  const visible = q
    ? professors.filter((p) => p.name.toLowerCase().includes(q))
    : professors

  const scores = useRunScores(runId)
  const { data: schools } = useRunSchools(runId ?? "", false, !!runId)
  const school = schools?.find((s) => s.id === program?.school_id)
  const scored = professors.filter((p) => scores.has(p.id)).length
  const sorted = [...visible].sort((a, b) => {
    const ca = scores.get(a.id)
    const cb = scores.get(b.id)
    if (!!ca !== !!cb) return ca ? -1 : 1
    if (ca && cb) return (cb.similarity_score ?? -1) - (ca.similarity_score ?? -1)
    return a.name.localeCompare(b.name)
  })

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <HealthBanner />

      {isLoading ? (
        <DetailSkeleton />
      ) : isError || !program ? (
        <ErrorState
          mascot="not-found"
          title="Programme not found"
          description="It may have been deleted."
          action={<Link to={`/runs/${runId}`} className="type-meta hover:text-foreground">Go to the run</Link>}
        />
      ) : (
        <ReadingSurface>
          <DetailHeader
            size="page"
            banner={school?.image_url ? <SchoolImage src={school.image_url} name={school.name} variant="banner" /> : undefined}
            title={program.name}
            identity={[{ icon: Landmark, value: school ? <Link to={`/schools/${school.id}`} className="hover:text-foreground hover:underline">{program.school_name}</Link> : program.school_name }]}
          >
            <FactList
              facts={[
                { icon: Users, value: `${professors.length} faculty` },
                scored > 0 && { icon: Target, value: `${scored} scored` },
                program.department_url && { icon: LinkIcon, value: "Department page", href: program.department_url },
                run && { icon: Activity, value: <Link to={`/runs/${runId}`} className="text-primary hover:underline">{runTitle(run)}</Link>, title: "Run" },
              ]}
            />
          </DetailHeader>

          <ReadingSection
            title="Faculty"
            meta={professors.length || undefined}
            action={<SearchInput value={query} onChange={setQuery} placeholder="Search faculty" />}
          >
            {professors.length === 0 ? (
              <EmptyState
                mascot="no-file"
                title="No professors yet"
                description="No professors researched yet. Research is still running, or nothing was found for this programme."
              />
            ) : sorted.length === 0 ? (
              <EmptyNote>Nothing matches this search.</EmptyNote>
            ) : (
              <CardGrid>
                {sorted.map((p) => {
                  const c = scores.get(p.id)
                  const ref = c ? ({ kind: "candidate", id: c.id } as const) : ({ kind: "professor", id: p.id } as const)
                  return (
                    <PersonCard
                      key={p.id}
                      name={p.name}
                      photo={p.photo_url}
                      subtitle={p.lab_name || plural(p.papers, "paper")}
                      status={c?.status}
                      score={c ? c.similarity_score : null}
                      active={isOpen(ref)}
                      onOpen={() => open(ref, p.name)}
                    />
                  )
                })}
              </CardGrid>
            )}
          </ReadingSection>
        </ReadingSurface>
      )}
    </div>
  )
}
