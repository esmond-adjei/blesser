import { Link } from "react-router-dom"
import { Sparkles, Target } from "lucide-react"
import type { FacultyRow } from "../../lib/types"
import { Avatar } from "../ui/avatar"
import { Button } from "../ui/button"
import { ScoreBar } from "../ui/status"
import { SchoolImage } from "../entity/SchoolImage"
import { useFindPapers } from "../gradis/useFindPapers"
import { ApplicationSchoolLink } from "../applications/ApplicationSchoolLink"

export function ProfessorCard({ professor: p, onCheck, showSchool = true, onOpen }: { professor: FacultyRow; onCheck: () => void; showSchool?: boolean; onOpen?: () => void }) {
  const { findPapers, sending } = useFindPapers()
  const to = p.candidate_id ? `/dossier/${p.candidate_id}` : `/professors/${p.id}`
  return (
    <li className="relative flex h-44 min-w-0 items-start gap-3 overflow-hidden rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent/50">
      <Avatar name={p.name} src={p.photo_url} size="lg" className="size-14 text-lg" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex min-w-0 items-center gap-3">
          <h3 className="min-w-0 flex-1 truncate font-semibold">
            {/* Stretched over the card, so the whole card opens the page. */}
            <Link to={to} onClick={(event) => {
              if (onOpen && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
                event.preventDefault()
                onOpen()
              }
            }} className="after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring">
              {p.name}
            </Link>
          </h3>
          {p.similarity_score != null ? (
            <ScoreBar score={p.similarity_score} className="shrink-0" />
          ) : p.papers === 0 ? (
            // Nothing to score yet: get the papers first.
            <Button
              size="sm"
              variant="outline"
              className="relative z-10 h-7 shrink-0 rounded-full"
              disabled={sending}
              data-tooltip="No papers yet. Gradis finds them on OpenAlex and saves them"
              onClick={() => findPapers(p)}
            >
              <Sparkles /> Find papers
            </Button>
          ) : (
            <Button size="sm" variant="secondary" className="relative z-10 h-7 shrink-0 rounded-full" onClick={onCheck}>
              <Target /> Check match
            </Button>
          )}
        </div>
        {showSchool && p.school && (
          <p className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
            <SchoolImage src={p.school_image_url} name={p.school} variant="thumb-xs" />
            {p.school_id ? (
              <Link to={`/schools/${p.school_id}`} className="relative z-10 truncate hover:text-foreground hover:underline">
                {p.school}
              </Link>
            ) : <span className="truncate"><ApplicationSchoolLink name={p.school} /></span>}
          </p>
        )}
        {p.program && <p className="truncate type-caption" title={p.program}>{p.program}</p>}
        {p.bio && <p className="line-clamp-3 pt-1 text-sm text-muted-foreground">{p.bio}</p>}
      </div>
    </li>
  )
}
