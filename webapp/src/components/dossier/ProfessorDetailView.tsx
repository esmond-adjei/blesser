import * as React from "react"
import {
  BookOpen,
  ExternalLink,
  FlaskConical,
  Globe,
  Landmark,
  Link as LinkIcon,
  Mail,
  Sparkles,
} from "lucide-react"
import { useApplications } from "../../lib/applications"
import { openAlexUrl } from "../../lib/entities"
import type {
  CandidateDetail,
  Paper,
  ProfessorDetail,
  ProfessorMatchRef,
} from "../../lib/types"
import { Link, useNavigate } from "react-router-dom"
import { ApplicationSchoolLink } from "../applications/ApplicationSchoolLink"
import { useRuns } from "../../lib/queries"
import { runTitle } from "../../lib/format"
import { cn } from "../../lib/utils"
import { Markdown } from "../ui/MarkdownLazy"
import {
  EmptyNote,
  ReadingSection,
  ReadingSurface,
} from "../ui/reading"
import {
  ScoreBar,
} from "../ui/status"
import {
  DetailAvatar,
  DetailHeader,
  PaperDialog,
  PaperGrid,
  type DetailSize,
} from "../entity/detail"
import { CardGrid, LinkedApplicationCard } from "../cards/EntityCards"
import { useOpenRecord } from "../layout/openRecord"
import { FactList, type Fact } from "../entity/facts"
import { Button } from "../ui/button"
import { useFindPapers } from "../gradis/useFindPapers"
import { usePreviewParam, useUrlParam } from "../../lib/urlParams"

/** A professor at page or panel width. A scored candidate adds fit,
 * rationale and cited papers; the page adds drafts and applications. */
export function ProfessorDetailView({
  size,
  candidate,
  professor,
  actions,
  draft,
}: {
  size: DetailSize
  candidate?: CandidateDetail | null
  professor?: ProfessorDetail | null
  /** Page only: review toggle, main action, menu. */
  actions?: React.ReactNode
  /** Page only: the draft section's body. */
  draft?: React.ReactNode
}) {
  const page = size === "page"

  // The professor record is edited directly, so its name wins when loaded.
  const name =
    professor?.name ?? candidate?.professor_name ?? ""

  const school =
    candidate?.school_name ?? professor?.school_name

  const program =
    candidate?.program_name ?? professor?.program_name

  const photo =
    professor?.photo_url ?? candidate?.professor_photo_url

  const facts: Array<Fact | null> = [
    professor?.email
      ? {
          icon: Mail,
          value: professor.email,
          href: `mailto:${professor.email}`,
        }
      : null,

    professor?.lab_name
      ? {
          icon: FlaskConical,
          value: professor.lab_name,
        }
      : null,

    professor?.profile_url
      ? {
          icon: LinkIcon,
          value: "Faculty profile",
          href: professor.profile_url,
        }
      : null,

    professor?.openalex_id
      ? {
          icon: Globe,
          value: "OpenAlex",
          href: openAlexUrl(professor.openalex_id),
        }
      : null,

    ...(professor?.socials ?? []).map((s) => ({
      icon: ExternalLink,
      value: s.label,
      href: s.url,
    })),
  ]

  const cited = candidate?.papers ?? []

  const citedTitles = new Set(
    cited.map((p) => p.title.trim().toLowerCase())
  )

  const others = (professor?.papers ?? []).filter(
    (p) => !citedTitles.has(p.title.trim().toLowerCase())
  )

  // ?paper=<id> (a search hit, a Gradis card) opens that paper on the page.
  const [paperId, setPaperId] = useUrlParam("paper")
  const linkedPaper = page && paperId
    ? [...cited, ...(professor?.papers ?? [])].find((p) => p.id === paperId)
    : undefined

  return (
    <ReadingSurface>
      <DetailHeader
        size={size}
        leading={
          <DetailAvatar
            name={name}
            src={photo}
            size={size}
          />
        }
        title={name}
        identity={[
          school && {
            icon: Landmark,
            value: candidate?.school_id ? (
              <Link to={`/schools/${candidate.school_id}`} className="hover:text-foreground hover:underline">{school}</Link>
            ) : <ApplicationSchoolLink name={school} />,
          },
          program && {
            icon: BookOpen,
            value: program,
          },
        ]}
        actions={actions}
      >
        {candidate && (candidate.matches?.length ?? 0) > 1 ? (
          <MatchScores current={candidate.id} matches={candidate.matches ?? []} page={page} />
        ) : candidate ? (
          <ScoreBar
            score={candidate.similarity_score}
            size="lg"
            dataTooltip={candidate.interest ? `Scored against: "${clip(candidate.interest, 300)}"` : undefined}
          />
        ) : (
          professor && (
            <span className="type-meta">
              Not scored as a candidate yet
            </span>
          )
        )}

        <FactList facts={facts} />
      </DetailHeader>

      {professor?.bio && (
        <ReadingSection title="About">
          <p>{professor.bio}</p>
        </ReadingSection>
      )}

      {page && candidate && (
        <ReadingSection
          title="Why this match"
          className="p-4 border border-border rounded-xl"
        >
          {candidate.rationale ? (
            <Markdown text={candidate.rationale} />
          ) : (
            <EmptyNote>
              No rationale recorded.
            </EmptyNote>
          )}
        </ReadingSection>
      )}

      {candidate ? (
        <ReadingSection
          title="Cited papers"
          meta={cited.length || undefined}
        >
          {cited.length === 0 ? (
            <EmptyNote>No papers cited.</EmptyNote>
          ) : (
            <PaperGrid
              papers={cited}
              size={size}
            />
          )}
        </ReadingSection>
      ) : (
        professor && (
          <ReadingSection
            title="Papers"
            meta={professor.papers.length || undefined}
          >
            {professor.papers.length === 0 ? (
              <FindPapers professor={professor} />
            ) : (
              <PaperGrid
                papers={professor.papers}
                size={size}
              />
            )}
          </ReadingSection>
        )
      )}

      {page && draft && (
        <ReadingSection title="Draft">
          {draft}
        </ReadingSection>
      )}

      {candidate && others.length > 0 && (
        <OtherPapers
          papers={others}
          size={size}
        />
      )}

      {page && candidate && (
        <AlsoIn candidateId={candidate.id} />
      )}

      {linkedPaper && (
        <PaperDialog paper={linkedPaper} open onOpenChange={(o) => !o && setPaperId("")} />
      )}
    </ReadingSurface>
  )
}

function MatchScores({ current, matches, page }: { current: string; matches: ProfessorMatchRef[]; page: boolean }) {
  const { data: runs } = useRuns()
  const navigate = useNavigate()
  const { openPreview } = usePreviewParam()
  const titles = new Map((runs ?? []).map((r) => [r.id, runTitle(r)]))
  return (
    <ul className="w-full max-w-xl space-y-0.5" aria-label="Scores by interest">
      {matches.map((m) => {
        const active = m.id === current
        const label = titles.get(m.run_id) ?? (m.interest ? clip(m.interest, 60) : "Run")
        return (
          <li key={m.id}>
            <button
              type="button"
              aria-current={active || undefined}
              disabled={active}
              onClick={() => (page ? navigate(`/dossier/${m.id}`) : openPreview(m.id))}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-2 py-1 text-left transition-colors",
                active ? "bg-tint-soft" : "cursor-pointer hover:bg-accent",
              )}
            >
              <span className={cn("min-w-0 flex-1 truncate text-sm", active ? "font-medium" : "text-muted-foreground")}>{label}</span>
              <ScoreBar
                score={m.similarity_score}
                className="shrink-0"
                dataTooltip={m.interest ? `Scored against: "${clip(m.interest, 300)}"` : undefined}
              />
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function clip(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim()
  return flat.length <= max ? flat : `${flat.slice(0, max).replace(/\s+\S*$/, "")}…`
}

function OtherPapers({
  papers,
  size,
}: {
  papers: Paper[]
  size: DetailSize
}) {
  return (
    <ReadingSection
      title="Other papers"
      meta={papers.length}
    >
      <PaperGrid
        papers={papers}
        size={size}
      />
    </ReadingSection>
  )
}

function AlsoIn({
  candidateId,
}: {
  candidateId: string
}) {
  const { apps } = useApplications()
  const { open, isOpen } = useOpenRecord()

  const linked = apps.filter((a) =>
    a.professors.some(
      (p) => p.candidateId === candidateId
    )
  )

  if (linked.length === 0) return null

  return (
    <ReadingSection title="Also in">
      <CardGrid>
        {linked.map((a) => (
          <LinkedApplicationCard
            key={a.id}
            program={a.program}
            school={a.school}
            schoolImage={a.schoolImageUrl}
            status={a.status}
            deadline={a.deadline}
            active={isOpen({ kind: "application", id: a.id })}
            onOpen={() => open({ kind: "application", id: a.id }, a.program || a.school)}
          />
        ))}
      </CardGrid>
    </ReadingSection>
  )
}

/** No papers yet: Gradis can find the professor on OpenAlex in a chat it opens. */
function FindPapers({ professor }: { professor: ProfessorDetail }) {
  const { findPapers, sending } = useFindPapers()
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-dashed border-border bg-muted/30 p-5">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-tint-soft text-tint">
        <BookOpen className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 basis-48 space-y-1">
        <p className="font-medium">No papers yet</p>
        <p className="text-sm text-muted-foreground">
          Papers show what {professor.name} works on, and they're what a match is scored against. Gradis can find
          them on OpenAlex and save them here.
        </p>
      </div>
      <Button
        className="shrink-0"
        disabled={sending}
        onClick={() =>
          findPapers({ ...professor, program: professor.program_name, school: professor.school_name })
        }
      >
        <Sparkles /> Find papers with Gradis
      </Button>
    </div>
  )
}
