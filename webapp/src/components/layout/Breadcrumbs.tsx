import { Link, useLocation } from "react-router-dom"
import {
  BookOpen,
  ChevronRight,
  ContactRound,
  FileText,
  FlaskConical,
  Landmark,
  ListTodo,
  Sparkles,
  Users,
  Mail,
  MessageSquare,
  Plus,
  SendHorizontal,
  type LucideIcon,
} from "lucide-react"
import { useAllRunSchools, useCandidate, useOutboxDrafts, useProfessor, useProgram, useRun } from "../../lib/queries"
import { useApplications } from "../../lib/applications"
import { runTitle } from "../../lib/format"
import { GradisTitleMenu } from "../gradis/GradisChat"

type Crumb = { label: string; to?: string; icon?: LucideIcon }

function Trail({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 w-full items-center gap-1 text-sm">
        {items.map((item, i) => {
          const last = i === items.length - 1
          const Icon = item.icon
          const content = (
            <>
              {Icon && <Icon className="size-4 shrink-0" aria-hidden />}
              <span className="min-w-0 max-w-full truncate">{item.label}</span>
            </>
          )
          return (
            <li
              key={`${item.label}-${i}`}
              className="flex min-w-0 max-w-36 items-center gap-1 sm:max-w-48 last:min-w-0 last:max-w-none last:flex-1"
            >
              {i > 0 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />}
              {item.to && !last ? (
                <Link
                  to={item.to}
                  data-tooltip={item.label}
                  className="inline-flex min-w-0 max-w-full items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground"
                >
                  {content}
                </Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  data-tooltip={item.label}
                  className={
                    last
                      ? "inline-flex min-w-0 max-w-full items-center gap-1.5 font-medium text-foreground"
                      : "inline-flex min-w-0 max-w-full items-center gap-1.5 text-muted-foreground"
                  }
                >
                  {content}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function RunCrumbs({ runId, rest }: { runId: string; rest: string }) {
  const { data: run } = useRun(runId)
  const title = run ? runTitle(run) : "Run"
  const base: Crumb[] = [
    { label: "Runs", icon: FlaskConical },
    { label: title, to: `/runs/${runId}`, icon: FlaskConical },
  ]

  const programme = rest.match(/^\/programmes\/([^/]+)/)
  if (programme) {
    return (
      <ProgrammeCrumbs
        base={base}
        programId={programme[1]}
      />
    )
  }

  return <Trail items={base} />
}

function ProgrammeCrumbs({
  base,
  programId,
}: {
  base: Crumb[]
  programId: string
}) {
  const { data: program } = useProgram(programId)
  const programName = program?.name ?? "Programme"
  return <Trail items={[...base, { label: programName, icon: BookOpen }]} />
}

function DossierDetailCrumbs({ candidateId }: { candidateId: string }) {
  const { data: candidate } = useCandidate(candidateId)
  return (
    <Trail
      items={[
        { label: "Matches", to: "/dossier", icon: ContactRound },
        { label: candidate?.professor_name ?? "Professor", icon: ContactRound },
      ]}
    />
  )
}

function ProfessorDetailCrumbs({ professorId }: { professorId: string }) {
  const { data: professor } = useProfessor(professorId)
  return (
    <Trail
      items={[
        { label: "Professors", to: "/professors", icon: Users },
        { label: professor?.name ?? "Professor", icon: ContactRound },
      ]}
    />
  )
}

function OutboxDetailCrumbs({ draftId }: { draftId: string }) {
  const { items, isLoading } = useOutboxDrafts()
  const found = items.find((i) => i.draft.id === draftId)
  return (
    <Trail
      items={[
        { label: "Outbox", to: "/outbox", icon: Mail },
        { label: isLoading ? "Draft" : (found?.draft.subject || "Draft"), icon: SendHorizontal },
      ]}
    />
  )
}

function ApplicationDetailCrumbs({ appId }: { appId: string }) {
  const { apps } = useApplications()
  const found = apps.find((a) => a.id === appId)
  return (
    <Trail
      items={[
        { label: "Applications", to: "/applications", icon: FileText },
        { label: found?.school ?? "Application", icon: FileText },
      ]}
    />
  )
}

function SchoolDetailCrumbs({ schoolId }: { schoolId: string }) {
  const { items } = useAllRunSchools()
  const found = items.find((i) => i.school.id === schoolId)
  return (
    <Trail
      items={[
        { label: "Schools", to: "/schools", icon: Landmark },
        { label: found?.school.name ?? "School", icon: Landmark },
      ]}
    />
  )
}

/** Chat header: the open chat's title menu, replacing a "Gradis" crumb. */
function ChatCrumbs() {
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm">
      <MessageSquare className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <GradisTitleMenu isPage className="max-w-full font-medium" />
    </nav>
  )
}

/** Rendered above the max-width column so it spans the full main width. */
export function Breadcrumbs() {
  const { pathname } = useLocation()

  if (pathname === "/new") {
    return (
      <Trail
        items={[
          { label: "New run", icon: Plus },
        ]}
      />
    )
  }
  if (pathname === "/dossier") return <Trail items={[{ label: "Matches", icon: ContactRound }]} />
  if (pathname === "/chat" || pathname.startsWith("/chat/")) return <ChatCrumbs />
  if (pathname === "/outbox") return <Trail items={[{ label: "Outbox", icon: Mail }]} />
  if (pathname === "/opportunities") return <Trail items={[{ label: "Opportunities", icon: Sparkles }]} />
  if (pathname === "/todos") return <Trail items={[{ label: "To-dos", icon: ListTodo }]} />
  if (pathname === "/applications")
    return <Trail items={[{ label: "Applications", icon: FileText }]} />
  if (pathname === "/schools")
    return <Trail items={[{ label: "Schools", icon: Landmark }]} />
  if (pathname === "/professors")
    return <Trail items={[{ label: "Professors", icon: Users }]} />
  if (pathname === "/settings/agents")
    return <Trail items={[{ label: "Settings" }, { label: "Agents & tools" }]} />

  const runMatch = pathname.match(/^\/runs\/([^/]+)(\/.*)?$/)
  if (runMatch) return <RunCrumbs runId={runMatch[1]} rest={runMatch[2] ?? ""} />

  const dossierMatch = pathname.match(/^\/dossier\/([^/]+)/)
  if (dossierMatch) return <DossierDetailCrumbs candidateId={dossierMatch[1]} />

  const professorMatch = pathname.match(/^\/professors\/([^/]+)\/?$/)
  if (professorMatch) return <ProfessorDetailCrumbs professorId={professorMatch[1]} />

  const outboxMatch = pathname.match(/^\/outbox\/([^/]+)/)
  if (outboxMatch) return <OutboxDetailCrumbs draftId={outboxMatch[1]} />

  const applicationMatch = pathname.match(/^\/applications\/([^/]+)/)
  if (applicationMatch) return <ApplicationDetailCrumbs appId={applicationMatch[1]} />

  const schoolMatch = pathname.match(/^\/schools\/([^/]+)/)
  if (schoolMatch) return <SchoolDetailCrumbs schoolId={schoolMatch[1]} />

  return <Trail items={[{ label: "Not found" }]} />
}
