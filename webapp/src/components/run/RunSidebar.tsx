import * as React from "react"
import { BookOpen, Users } from "lucide-react"
import { useProgram, useRunCandidates, useRunSchools, useRunScores } from "../../lib/queries"
import type { Candidate, ProgramOut, School } from "../../lib/types"
import { Avatar } from "../ui/avatar"
import { Skeleton } from "../ui/feedback"
import { CandidateStatusBadge, ScoreBar } from "../ui/status"
import { EntityList, EntityRow, EntityRowSkeleton } from "../entity/EntityRow"
import { FactList } from "../entity/facts"
import { SchoolImage } from "../entity/SchoolImage"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs"
import { CandidatesTab } from "./CandidatesTab"
import { useApplications } from "../../lib/applications"
import { ApplicationAgenda } from "../applications/ApplicationViews"
import { ApplicationEditMenu } from "../applications/ApplicationEditMenu"
import { useOpenRecord } from "../layout/openRecord"

/** Fetches its own data over shared query keys. */
export function RunSidebar({
  runId,
  fallbackPoll,
}: {
  runId: string
  fallbackPoll: number | false
}) {
  const [tab, setTab] = React.useState("schools")
  const { data: schools } = useRunSchools(runId, fallbackPoll)
  // Badge total from the candidates query itself (limit 1, only `total`), so no summary endpoint.
  const { data: candidatePage } = useRunCandidates(
    runId,
    { status: "all", limit: 1, offset: 0 },
    fallbackPoll,
  )
  const { apps, isLoading: appsLoading } = useApplications()
  const runApps = apps.filter((a) => a.runId === runId)
  const schoolCount = schools?.length ?? 0
  const candidateTotal = candidatePage?.total ?? 0

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="w-full">
        <TabsTrigger value="schools" className="flex-1">
          Schools ({schoolCount})
        </TabsTrigger>
        <TabsTrigger value="applications" className="flex-1">
          Applications ({runApps.length})
        </TabsTrigger>
        <TabsTrigger value="candidates" className="flex-1">
          Candidates ({candidateTotal})
        </TabsTrigger>
      </TabsList>
      <TabsContent value="schools">
        <SchoolsTab runId={runId} pollMs={fallbackPoll} />
      </TabsContent>
      <TabsContent value="applications">
        <ApplicationsTab apps={runApps} isLoading={appsLoading} />
      </TabsContent>
      <TabsContent value="candidates">
        <CandidatesTab runId={runId} fallbackPoll={fallbackPoll} />
      </TabsContent>
    </Tabs>
  )
}

function ApplicationsTab({ apps, isLoading }: { apps: ReturnType<typeof useApplications>["apps"]; isLoading: boolean }) {
  const { open, isOpen } = useOpenRecord()
  if (isLoading) return <Skeleton className="h-16" />
  if (apps.length === 0)
    return <p className="type-meta">No applications yet. They appear here when the run saves one.</p>
  return (
    <ApplicationAgenda
      apps={apps}
      isActive={(a) => isOpen({ kind: "application", id: a.id })}
      onOpen={(a) => open({ kind: "application", id: a.id }, a.program || a.school)}
      menuFor={(a) => <ApplicationEditMenu app={a} />}
      compact
    />
  )
}

/** Schools as one expandable list: opening a school shows its programmes and their professors at once. */
function SchoolsTab({ runId, pollMs }: { runId: string; pollMs: number | false }) {
  const { data: schools, isLoading, isError } = useRunSchools(runId, pollMs)
  const scores = useRunScores(runId, pollMs)

  if (isLoading) return <div aria-label="Loading schools" aria-busy="true">{Array.from({ length: 3 }, (_, i) => <EntityRowSkeleton key={i} />)}</div>
  if (isError) return <p className="text-sm text-destructive">Couldn't load schools.</p>
  if (!schools || schools.length === 0)
    return (
      <p className="type-meta">
        No schools yet. They appear here once discovery saves programmes.
      </p>
    )

  return (
    <EntityList>
      {schools.map((s) => (
        <SchoolRow key={s.id} school={s} runId={runId} scores={scores} />
      ))}
    </EntityList>
  )
}

type Scores = Map<string, Candidate>

function SchoolRow({ school, runId, scores }: { school: School; runId: string; scores: Scores }) {
  const [open, setOpen] = React.useState(false)
  const faculty = school.programs.reduce((n, p) => n + p.professors, 0)
  return (
    <>
      <EntityRow
        onClick={() => setOpen((o) => !o)}
        expanded={open}
        leading={<SchoolImage src={school.image_url} name={school.name} variant="thumb" />}
        title={school.name}
        subtitle={school.country ?? undefined}
        end={
          <FactList
            size="sm"
            facts={[
              { icon: BookOpen, value: String(school.programs.length), title: "Programmes" },
              { icon: Users, value: String(faculty), title: "Faculty" },
            ]}
          />
        }
      />
      {open &&
        (school.programs.length === 0 ? (
          <p className="border-t border-border/70 py-2 pl-8 type-caption">No programmes yet.</p>
        ) : (
          school.programs.map((p) => <ProgramRow key={p.id} program={p} runId={runId} scores={scores} />)
        ))}
    </>
  )
}

/** A programme under an open school; the school's toggle opens everything. */
function ProgramRow({ program, runId, scores }: { program: ProgramOut; runId: string; scores: Scores }) {
  const { data, isLoading } = useProgram(program.id)
  const professors = data?.professors ?? []
  return (
    <>
      <EntityRow
        compact
        indent={1}
        className="border-t border-border/70 bg-muted/30 hover:bg-muted/30"
        title={program.name}
        end={<span className="type-caption tabular-nums" data-tooltip="Faculty">{program.professors}</span>}
      />
      {isLoading && <Skeleton className="mx-3 my-2 h-8" />}
      {!isLoading && professors.length === 0 && (
        <p className="border-t border-border/70 py-2 pl-12 type-caption">No professors yet.</p>
      )}
      {professors.map((prof) => {
        const c = scores.get(prof.id)
        return (
          <EntityRow
            key={prof.id}
            compact
            indent={2}
            className="border-t border-border/70"
            to={c ? `/dossier/${c.id}` : `/runs/${runId}/programmes/${program.id}?preview=${prof.id}`}
            leading={<Avatar name={prof.name} src={prof.photo_url} size="sm" className="size-6 text-xs" />}
            title={prof.name}
            end={
              <>
                {c && <CandidateStatusBadge status={c.status} quiet />}
                <ScoreBar score={c ? c.similarity_score : null} />
              </>
            }
          />
        )
      })}
    </>
  )
}
