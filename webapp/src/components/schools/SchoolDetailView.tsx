import * as React from "react"
import { Link } from "react-router-dom"
import { Activity, BookOpen, ExternalLink, FileText, Globe, Layers, MapPin, Target, Users } from "lucide-react"
import { useApplications } from "../../lib/applications"
import { useAllRunSchools, useRuns, useSchoolFaculty } from "../../lib/queries"
import { runTitle } from "../../lib/format"
import type { FacultyRow } from "../../lib/types"
import { hostOf, plural } from "../../lib/entities"
import { tierColors } from "../../lib/schools"
import { DetailSkeleton, Skeleton } from "../ui/feedback"
import { EmptyNote, ReadingSection, ReadingSurface } from "../ui/reading"
import { ErrorState } from "../feedback/EmptyState"
import { useOpenRecord } from "../layout/openRecord"
import { DetailHeader, type DetailSize } from "../entity/detail"
import { FactList } from "../entity/facts"
import { SchoolImage } from "../entity/SchoolImage"
import { CardGrid } from "../cards/EntityCards"
import { ApplicationCard } from "../cards/ApplicationCards"
import { ProfessorCard } from "../cards/ProfessorCard"
import { MatchProfessorDialog } from "../dialogs/MatchProfessorDialog"
import { SchoolTierText } from "./SchoolTierText"
import { SchoolRowMenu } from "./SchoolCard"
import { ApplicationEditMenu } from "../applications/ApplicationEditMenu"

const norm = (s: string) => s.trim().toLowerCase()

export function SchoolDetailView({ schoolId, size }: { schoolId: string; size: DetailSize }) {
  const page = size === "page"
  const { items, isLoading: schoolsLoading } = useAllRunSchools()
  const found = items.find(({ school }) => school.id === schoolId) ?? null
  const school = found?.school ?? null

  const facultyQuery = useSchoolFaculty(found ? schoolId : null)
  const facultyLoading = !!found && facultyQuery.isLoading
  const faculty = facultyQuery.data ?? []
  const matches = faculty.filter((f) => f.candidate_id)

  const { data: runs } = useRuns()
  const runsUsing = (runs ?? []).filter((r) => found?.runIds.includes(r.id))
  const { apps, isLoading: appsLoading } = useApplications()
  const schoolApps = school ? apps.filter((a) => norm(a.school) === norm(school.name)) : []

  const { open, isOpen } = useOpenRecord()
  const [checking, setChecking] = React.useState<FacultyRow | null>(null)
  if (schoolsLoading) return <DetailSkeleton />
  if (!school || !found) {
    return (
      <ErrorState
        mascot="not-found"
        title="School not found"
        description="It may have been deleted."
        action={page ? <Link to="/schools" className="type-meta hover:text-label">Go to schools</Link> : undefined}
      />
    )
  }

  const personCard = (f: FacultyRow) => (
    <ProfessorCard key={f.id} professor={f} showSchool={false} onCheck={() => setChecking(f)} />
  )
  const unassigned = faculty.filter((f) => !school.programs.some((p) => p.id === f.program_id))

  return (
    <ReadingSurface>
      <DetailHeader
        size={size}
        banner={<SchoolImage src={school.image_url} name={school.name} variant={page && school.image_url ? "banner" : "banner-sm"} />}
        title={school.name}
        actions={<SchoolRowMenu school={school} variant="header" />}
        identity={[
          school.country && { icon: MapPin, value: school.country },
          school.tier && { icon: Layers, iconClassName: tierColors[school.tier], value: <SchoolTierText tier={school.tier} /> },
        ]}
      >
        <FactList
          facts={[
            { icon: BookOpen, value: plural(school.programs.length, "programme") },
            { icon: Users, value: `${faculty.length} faculty` },
            { icon: Target, value: plural(matches.length, "candidate") },
            schoolApps.length > 0 && { icon: FileText, value: plural(schoolApps.length, "application") },
          ]}
        />
        <FactList
          facts={[
            school.website_url && { icon: Globe, value: hostOf(school.website_url), href: school.website_url },
            ...runsUsing.map((r) => ({
              icon: Activity,
              value: (
                <Link to={`/runs/${r.id}`} className="text-tint hover:underline">
                  {runTitle(r)}
                </Link>
              ),
              title: "Run that found it",
            })),
          ]}
        />
      </DetailHeader>

      {(appsLoading || schoolApps.length > 0) && (
        <ReadingSection title="Your applications" meta={schoolApps.length || undefined}>
          {appsLoading ? (
            <Skeleton className="h-16" />
          ) : (
            <CardGrid>
              {schoolApps.map((a) => (
                <ApplicationCard
                  key={a.id}
                  app={a}
                  preview
                  menu={<ApplicationEditMenu app={a} />}
                  isActive={isOpen({ kind: "application", id: a.id })}
                  onOpen={() => open({ kind: "application", id: a.id }, a.program || school.name)}
                />
              ))}
            </CardGrid>
          )}
        </ReadingSection>
      )}

      {facultyLoading ? (
        <ReadingSection title="Professors"><Skeleton className="h-24" /></ReadingSection>
      ) : facultyQuery.isError ? (
        <ReadingSection title="Professors"><EmptyNote>Couldn’t load professors for this school.</EmptyNote></ReadingSection>
      ) : (
        <>
          {[...school.programs].sort((a, b) => a.name.localeCompare(b.name)).map((program) => {
            const members = faculty.filter((f) => f.program_id === program.id).sort((a, b) => a.name.localeCompare(b.name))
            return (
              <ReadingSection
                key={program.id}
                title={program.department_url ? (
                  <a href={program.department_url} target="_blank" rel="noopener noreferrer" className="group/faculty inline-flex items-center gap-1.5 hover:underline">
                    {program.name}
                    <ExternalLink className="size-3.5 opacity-0 transition-opacity group-hover/faculty:opacity-100 group-focus-visible/faculty:opacity-100" aria-hidden="true" />
                  </a>
                ) : program.name}
                action={<span className="type-caption">{plural(members.length, "professor")}</span>}
              >
                {members.length ? <ul className="grid gap-3">{members.map(personCard)}</ul> : (
                  <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border px-4 py-8 text-center text-muted-foreground">
                    <Users className="size-5" aria-hidden="true" />
                    <p className="text-sm">No professors listed yet.</p>
                  </div>
                )}
              </ReadingSection>
            )
          })}
          {unassigned.length > 0 && (
            <ReadingSection title="Other professors" meta={plural(unassigned.length, "professor")}>
              <ul className="grid gap-3">{unassigned.map(personCard)}</ul>
            </ReadingSection>
          )}
          {school.programs.length === 0 && faculty.length === 0 && (
            <ReadingSection title="Professors"><EmptyNote>No programmes or professors saved for this school yet.</EmptyNote></ReadingSection>
          )}
        </>
      )}
      {checking && <MatchProfessorDialog professor={checking} open onOpenChange={(o) => !o && setChecking(null)} />}
    </ReadingSurface>
  )
}
