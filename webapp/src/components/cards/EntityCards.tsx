import type * as React from "react"
import { Link as LinkIcon, Target, Users } from "lucide-react"
import { plural } from "../../lib/entities"
import { cn } from "../../lib/utils"
import type { ApplicationStatus } from "../../lib/applications"
import { Avatar } from "../ui/avatar"
import { ApplicationStatusBadge, CandidateStatusBadge, ScoreBar } from "../ui/status"
import { Deadline, FactList } from "../entity/facts"
import { SchoolImage } from "../entity/SchoolImage"
import { ItemCard } from "./ItemCard"
import { CoverCard } from "./CoverCard"
import { ApplicationSchoolLink } from "../applications/ApplicationSchoolLink"

/** Two columns once the container has room, one in a narrow panel. */
export function CardGrid({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className="@container">
      <ul className={cn("grid gap-3 @lg:grid-cols-2", className)}>{children}</ul>
    </div>
  )
}

export function PersonCard({
  name,
  photo,
  subtitle,
  status,
  score,
  active,
  unscored = "",
  onOpen,
}: {
  name: string
  photo?: string | null
  subtitle?: React.ReactNode
  /** The candidate's status; omitted for a professor not yet scored. */
  status?: string | null
  score?: number | null
  active?: boolean
  /** Shown in place of the fit bar when there's no score. */
  unscored?: string
  /** Omitted when there's nothing to open (an unlinked name). */
  onOpen?: () => void
}) {
  return (
    <li className="min-w-0">
      <ItemCard
        onOpen={onOpen}
        openLabel={`Open ${name}`}
        active={active}
        leading={<Avatar name={name} src={photo} size="sm" />}
        title={name}
        subtitle={subtitle}
        badges={status ? <CandidateStatusBadge status={status} quiet /> : undefined}
        signal={score != null ? <ScoreBar score={score} /> : <span className="type-caption">{unscored}</span>}
      />
    </li>
  )
}

export function ProgrammeCard({
  name,
  faculty,
  candidates,
  departmentUrl,
  active,
  onOpen,
}: {
  name: string
  faculty: number
  candidates?: number
  departmentUrl?: string | null
  active?: boolean
  onOpen: () => void
}) {
  return (
    <li className="min-w-0">
      <ItemCard
        onOpen={onOpen}
        openLabel={`Open ${name}`}
        active={active}
        title={<span className={cn("line-clamp-2 whitespace-normal", departmentUrl && "pr-8")}>{name}</span>}
        badges={
          <FactList
            size="sm"
            facts={[
              { icon: Users, value: `${faculty} faculty` },
              !!candidates && { icon: Target, value: plural(candidates, "candidate") },
            ]}
          />
        }
        // Outside the card's open button, so it stays its own link.
        menu={
          departmentUrl ? (
            <a
              href={departmentUrl}
              target="_blank"
              rel="noreferrer"
              aria-label={`${name} department page`}
              data-tooltip="Department page"
              className="absolute top-3 right-3 inline-flex size-7 items-center justify-center rounded-md text-label-tertiary hover:bg-fill-quiet hover:text-tint"
            >
              <LinkIcon className="size-4" />
            </a>
          ) : undefined
        }
      />
    </li>
  )
}

export function LinkedApplicationCard({
  program,
  school,
  schoolImage,
  status,
  deadline,
  active,
  onOpen,
}: {
  program: string
  school: string
  schoolImage?: string | null
  status: ApplicationStatus
  deadline: string
  active?: boolean
  onOpen: () => void
}) {
  return (
    <li className="min-w-0">
      <CoverCard label={`Open your application to ${program || school}`} onOpen={onOpen} active={active}>
        <div className="pointer-events-none relative flex w-full items-center gap-3">
          <SchoolImage src={schoolImage} name={school} variant="thumb" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{program || "Programme not set"}</p>
            <p className="truncate type-caption"><ApplicationSchoolLink name={school} /></p>
          </div>
        </div>
        <div className="pointer-events-none relative flex flex-wrap items-center gap-1.5">
          <ApplicationStatusBadge status={status} />
          <Deadline deadline={deadline} />
        </div>
      </CoverCard>
    </li>
  )
}
