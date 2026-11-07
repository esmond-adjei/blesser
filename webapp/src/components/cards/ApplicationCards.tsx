/* eslint-disable react/only-export-components -- status helpers live with the cards that render them */
import * as React from "react"
import { useNavigate } from "react-router-dom"
import {
  ArrowRight,
  GraduationCap,
  Landmark,
  Link as LinkIcon,
  MapPin,
  Pencil,
  SquareArrowOutUpRight,
  Trash2,
} from "lucide-react"
import { APPLICATION_STATUSES, type Application } from "../../lib/applications"
import type { ApplicationStatus } from "../../lib/applications"
import { useCandidate, useProfessor } from "../../lib/queries"
import { ApplicationTile } from "../applications/ApplicationViews"
import { Button } from "../ui/button"
import { ReadingSection, ReadingSurface } from "../ui/reading"
import { Markdown } from "../ui/MarkdownLazy"
import { MenuItem, MenuSeparator } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"
import { ApplicationStatusBadge } from "../ui/status"
import { CardGrid, PersonCard } from "./EntityCards"
import { useOpenRecord } from "../layout/openRecord"
import { Deadline, FactList } from "../entity/facts"
import { DetailHeader, type DetailSize } from "../entity/detail"
import { SchoolImage } from "../entity/SchoolImage"
import { cn } from "../../lib/utils"
import { toastError, toastInfo, toastSuccess } from "../../lib/toast"
import { ApplicationSchoolLink } from "../applications/ApplicationSchoolLink"
import { ProfessorCard } from "./ProfessorCard"
import { MatchProfessorDialog } from "../dialogs/MatchProfessorDialog"

export function statusLabel(s: ApplicationStatus): string {
  return s[0].toUpperCase() + s.slice(1)
}

/** Callbacks run on the page's store instance: the localStorage hook closes over its own state. */
export function ApplicationRowMenu({
  app,
  onEdit,
  onDelete,
  onMove,
  variant = "row",
  className,
}: {
  app: Application
  onEdit: () => void
  onDelete: () => void
  /** Status moves, the board's keyboard path; omitted where status isn't managed. */
  onMove?: (status: ApplicationStatus) => void
  variant?: RowMenuVariant
  className?: string
}) {
  const navigate = useNavigate()
  return (
    <RowMenu variant={variant} label={`Manage ${app.program || app.school}`} className={className}>
      {/* The rail header already has its own "Open as page" button. */}
      {variant === "row" && (
        <MenuItem onSelect={() => navigate(`/applications/${app.id}`)}>
          <SquareArrowOutUpRight /> Open as page
        </MenuItem>
      )}
      <MenuItem onSelect={onEdit}>
        <Pencil /> Edit
      </MenuItem>
      {onMove && (
        <>
          <MenuSeparator />
          {APPLICATION_STATUSES.filter((st) => st !== app.status).map((st) => (
            <MenuItem key={st} onSelect={() => onMove(st)}>
              <ArrowRight /> Move to {statusLabel(st).toLowerCase()}
            </MenuItem>
          ))}
        </>
      )}
      <MenuSeparator />
      <MenuItem destructive onSelect={onDelete}>
        <Trash2 /> Delete
      </MenuItem>
    </RowMenu>
  )
}

type ApplicationCardProps = {
  app: Application
  isActive: boolean
  onOpen: () => void
} & ({ preview: true; menu?: React.ReactNode; onEdit?: never; onDelete?: never } | { preview?: false; onEdit: () => void; onDelete: () => void })

export function ApplicationCard(props: ApplicationCardProps) {
  const { app, isActive, onOpen } = props
  return (
    <ApplicationTile
      app={app}
      active={isActive}
      onOpen={onOpen}
      menu={props.preview ? props.menu : <ApplicationRowMenu app={app} onEdit={props.onEdit} onDelete={props.onDelete} />}
    />
  )
}

/** Page actions sit beside the title; the panel's live in the rail header menu. */
export function ApplicationDetail({
  app,
  size,
  onEdit,
  onDelete,
  onToggleRequirement,
  onResolve,
}: {
  app: Application
  size: DetailSize
  onEdit: () => void
  onDelete: () => void
  onToggleRequirement: (index: number) => void
  onResolve: () => Promise<Application>
}) {
  const doneCount = app.requirements.filter((r) => r.done).length
  const [resolving, setResolving] = React.useState(false)
  async function handleResolve() {
    if (resolving) return
    setResolving(true)
    try {
      const updated = await onResolve()
      const fresh = updated.professors.filter((p, index) =>
        (p.candidateId && !app.professors[index]?.candidateId) ||
        (p.professorId && !app.professors[index]?.professorId),
      ).length
      if (fresh > 0) toastSuccess(`Linked ${fresh} professor${fresh === 1 ? "" : "s"} to research`)
      else toastInfo("No new research matches found")
    } catch (err) {
      toastError(err, "Couldn't link professors")
    } finally {
      setResolving(false)
    }
  }
  const page = size === "page"
  return (
    <ReadingSurface>
      <DetailHeader
        size={size}
        banner={app.schoolImageUrl ? <SchoolImage src={app.schoolImageUrl} name={app.school} variant={page ? "banner" : "banner-sm"} /> : undefined}
        title={app.program || "Programme not set"}
        identity={[
          { icon: Landmark, value: app.school && <ApplicationSchoolLink name={app.school} /> },
          { icon: MapPin, value: app.location },
          { icon: GraduationCap, value: app.degreeType },
        ]}
        actions={
          <>
            <Button data-tooltip="Edit this application" size="sm" onClick={onEdit}>
              <Pencil /> Edit
            </Button>
            <ApplicationRowMenu variant="header" app={app} onEdit={onEdit} onDelete={onDelete} />
          </>
        }
      >
        <span className="flex flex-wrap items-center gap-3">
          <ApplicationStatusBadge status={app.status} />
          <Deadline deadline={app.deadline} long />
          {app.source === "agent" && <span className="type-caption">Found by the research agents</span>}
        </span>
        <FactList facts={[app.link && { icon: LinkIcon, value: "Admissions page", href: app.link }]} />
      </DetailHeader>

      {app.requirements.length > 0 && <ReadingSection
        title="Requirements"
        meta={`${doneCount} of ${app.requirements.length} done`}
      >
          <ul className="-mx-2">
            {app.requirements.map((r, i) => (
              <li key={i}>
                <label className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent">
                  <input
                    type="checkbox"
                    checked={r.done}
                    onChange={() => onToggleRequirement(i)}
                    aria-label={`Mark ${r.label} as ${r.done ? "not done" : "done"}`}
                    className="mt-0.5 size-4 shrink-0 cursor-pointer accent-primary"
                  />
                  <span className={cn(r.done && "text-muted-foreground line-through")}>{r.label}</span>
                </label>
              </li>
            ))}
          </ul>
      </ReadingSection>}

      {app.professors.length > 0 && <ReadingSection
        title="Professors"
        meta={app.professors.length || undefined}
        action={
          app.professors.length > 0 && (
            <Button data-tooltip="Connect this application to a researched programme or professor" size="sm" variant="ghost" disabled={resolving} onClick={() => void handleResolve()}>
              <LinkIcon /> {resolving ? "Linking…" : "Link to research"}
            </Button>
          )
        }
      >
          <CardGrid className="auto-rows-fr [&>li>div]:h-full">
            {app.professors.map((p, i) => (
              <LinkedProfessorCard key={`${p.name}-${i}`} professor={p} />
            ))}
          </CardGrid>
      </ReadingSection>}

      {app.offer.trim() && (
        <ReadingSection title="Funding">
          <p>{app.offer}</p>
        </ReadingSection>
      )}

      {(app.feeWaiver || app.feeWaiverNotes.trim()) && (
        <ReadingSection title="Fee waiver">
          <p>{app.feeWaiverNotes.trim() || "A fee waiver is available."}</p>
        </ReadingSection>
      )}

      {app.notes.trim() && <Markdown text={app.notes} />}
    </ReadingSurface>
  )
}

/** A linked professor opens their match in the detail panel. */
function LinkedProfessorCard({ professor }: { professor: Application["professors"][number] }) {
  const { data: c } = useCandidate(professor.candidateId ?? null)
  const { data: profile } = useProfessor(professor.professorId ?? c?.professor_id ?? null)
  const { open, isOpen } = useOpenRecord()
  const [checking, setChecking] = React.useState(false)
  const ref = professor.candidateId
    ? { kind: "candidate" as const, id: professor.candidateId }
    : professor.professorId ? { kind: "professor" as const, id: professor.professorId } : null
  if (profile && ref) {
    const faculty = {
      id: profile.id,
      name: profile.name,
      program_id: profile.program_id,
      program: profile.program_name,
      school_id: c?.school_id ?? "",
      school: profile.school_name,
      lab_name: profile.lab_name,
      photo_url: profile.photo_url,
      bio: profile.bio,
      papers: profile.papers.length,
      candidate_id: professor.candidateId ?? null,
      similarity_score: c?.similarity_score ?? null,
    }
    return (
      <>
        <ProfessorCard professor={faculty} onCheck={() => setChecking(true)} onOpen={() => open(ref, profile.name)} />
        {checking && <MatchProfessorDialog professor={faculty} open onOpenChange={setChecking} />}
      </>
    )
  }
  return (
    <PersonCard
      name={professor.name}
      photo={c?.professor_photo_url}
      subtitle={c ? c.program_name : professor.school || undefined}
      status={c?.status}
      score={c ? c.similarity_score : null}
      unscored={ref ? "Not scored yet" : "Not in your research yet"}
      active={ref ? isOpen(ref) : false}
      onOpen={ref ? () => open(ref, professor.name) : undefined}
    />
  )
}
