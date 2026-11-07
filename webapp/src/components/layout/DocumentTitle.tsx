import * as React from "react"
import { useLocation } from "react-router-dom"
import {
  useAllRunSchools,
  useCandidate,
  useOutboxDrafts,
  useProfessor,
  useProgram,
  useRun,
} from "../../lib/queries"
import { useApplications } from "../../lib/applications"
import { runTitle } from "../../lib/format"

const APP_NAME = "Graduator"

function ApplyTitle({ label }: { label: string }) {
  React.useEffect(() => {
    document.title = `${label} | ${APP_NAME}`
  }, [label])
  return null
}

function CandidateTitle({
  candidateId,
  fallback,
}: {
  candidateId: string
  fallback: string
}) {
  const { data: candidate } = useCandidate(candidateId)
  return <ApplyTitle label={candidate?.professor_name ?? fallback} />
}

function ProfessorTitle({ professorId }: { professorId: string }) {
  const { data: professor } = useProfessor(professorId)
  return <ApplyTitle label={professor?.name ?? "Professor"} />
}

function ProgramTitle({ programId }: { programId: string }) {
  const { data: program } = useProgram(programId)
  return <ApplyTitle label={program?.name ?? "Programme"} />
}

function ApplicationTitle({ appId }: { appId: string }) {
  const { apps } = useApplications()
  const found = apps.find((a) => a.id === appId)
  return <ApplyTitle label={found?.school ?? "Application"} />
}

function DraftTitle({ draftId }: { draftId: string }) {
  const { items, isLoading } = useOutboxDrafts()
  const found = items.find((i) => i.draft.id === draftId)
  return <ApplyTitle label={isLoading ? "Draft" : found?.draft.subject || "Draft"} />
}

function SchoolTitle({ schoolId }: { schoolId: string }) {
  const { items } = useAllRunSchools()
  const found = items.find((i) => i.school.id === schoolId)
  return <ApplyTitle label={found?.school.name ?? "School"} />
}

function RunTitle({ runId, rest }: { runId: string; rest: string }) {
  const { data: run } = useRun(runId)
  const title = run ? runTitle(run) : "Run"

  const programme = rest.match(/^\/programmes\/([^/]+)/)
  if (programme) {
    return <ProgramTitle programId={programme[1]} />
  }

  return <ApplyTitle label={title} />
}

/** Mount once in the shell; reuses the query cache, so no extra fetches. */
export function DocumentTitle() {
  const { pathname } = useLocation()

  if (pathname === "/new") return <ApplyTitle label="New run" />
  if (pathname === "/dossier") return <ApplyTitle label="Matches" />
  if (pathname === "/chat" || pathname.startsWith("/chat/")) return <ApplyTitle label="Gradis" />
  if (pathname === "/outbox") return <ApplyTitle label="Outbox" />
  if (pathname === "/applications") return <ApplyTitle label="Applications" />
  if (pathname === "/schools") return <ApplyTitle label="Schools" />
  if (pathname === "/professors") return <ApplyTitle label="Professors" />
  if (pathname === "/settings/agents") return <ApplyTitle label="Agents & tools" />

  const runMatch = pathname.match(/^\/runs\/([^/]+)(\/.*)?$/)
  if (runMatch) return <RunTitle runId={runMatch[1]} rest={runMatch[2] ?? ""} />

  const dossierMatch = pathname.match(/^\/dossier\/([^/]+)/)
  if (dossierMatch) return <CandidateTitle candidateId={dossierMatch[1]} fallback="Professor" />

  const professorMatch = pathname.match(/^\/professors\/([^/]+)\/?$/)
  if (professorMatch) return <ProfessorTitle professorId={professorMatch[1]} />

  const outboxMatch = pathname.match(/^\/outbox\/([^/]+)/)
  if (outboxMatch) return <DraftTitle draftId={outboxMatch[1]} />

  const applicationMatch = pathname.match(/^\/applications\/([^/]+)/)
  if (applicationMatch) return <ApplicationTitle appId={applicationMatch[1]} />

  const schoolMatch = pathname.match(/^\/schools\/([^/]+)/)
  if (schoolMatch) return <SchoolTitle schoolId={schoolMatch[1]} />

  return <ApplyTitle label="Not found" />
}
