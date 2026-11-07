import { Circle, CircleCheck } from "lucide-react"
import { Link } from "react-router-dom"
import { hasDraft } from "../../lib/drafts"
import type { Candidate } from "../../lib/types"
import { notableCandidateStatus, plainText, professorPlace } from "../../lib/entities"
import { cn } from "../../lib/utils"
import { Avatar } from "../ui/avatar"
import { CandidateStatusBadge, ScoreBar } from "../ui/status"
import { CoverCard } from "../cards/CoverCard"
import { CandidateRowMenu } from "./CandidateRowMenu"

/** While the listing is selecting (for a PDF export), a click picks the card. */
export function ProfessorCard({
  candidate,
  runId,
  isBest = false,
  isActive,
  onOpen,
  selected,
  preview = false,
  otherMatches = 0,
}: {
  candidate: Candidate
  runId: string
  otherMatches?: number
  isBest?: boolean
  isActive: boolean
  onOpen: () => void
  /** Selection mode: `selected` is this card's pick state. */
  selected?: boolean
  preview?: boolean
}) {
  const selecting = selected !== undefined
  const Check = selected ? CircleCheck : Circle
  return (
    <CoverCard label={`Open ${candidate.professor_name}`} onOpen={onOpen} active={selecting ? selected : isActive} className="h-full">
      <div className="pointer-events-none flex gap-4">
        {selecting && <Check aria-hidden className={cn("size-5 shrink-0 absolute top-2 left-2 inline-block", selected ? "text-primary" : "text-muted-foreground")} />}
        <Avatar name={candidate.professor_name} src={candidate.professor_photo_url} />
        <div className="space-y-1.5">
          <h3 className="pointer-events-none relative g-ecard__title line-clamp-2">{candidate.professor_name}</h3>
          <p className="pointer-events-none relative g-ecard__meta line-clamp-1">
            {candidate.school_name && candidate.school_id && !selecting ? (
              <>
                {candidate.program_name && `${candidate.program_name} at `}
                <Link to={`/schools/${candidate.school_id}`} className="pointer-events-auto relative z-10 hover:text-foreground hover:underline">
                  {candidate.school_name}
                </Link>
              </>
            ) : professorPlace(candidate.program_name, candidate.school_name)}
          </p>
        </div>
      </div>
      <p className="pointer-events-none relative text-sm line-clamp-2">
        {plainText(candidate.rationale) || undefined}
      </p>
      <div className="pointer-events-none relative g-ecard__signal">
        {(notableCandidateStatus(candidate.status) || hasDraft(candidate) || isBest) && (
          <>
            {isBest && <span className="g-best">Best fit</span>}
            <CandidateStatusBadge status={candidate.status} quiet />
          </>
        )}
        <OtherMatches count={otherMatches} className="ml-auto" />
        <ScoreBar className={otherMatches > 0 ? undefined : "ml-auto"} score={candidate.similarity_score} />
      </div>
      {!selecting && !preview && <CandidateRowMenu candidate={candidate} runId={runId} isActive={isActive} />}
    </CoverCard>
  )
}

export function OtherMatches({ count, className }: { count: number; className?: string }) {
  if (count < 1) return null
  return (
    <span className={cn("type-caption whitespace-nowrap", className)} data-tooltip={`Also matched against ${count} other ${count === 1 ? "interest" : "interests"}; the best score is shown`}>
      +{count} more
    </span>
  )
}
