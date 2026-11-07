import * as React from "react"
import { useQueries, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { BookmarkPlus, Layers, LoaderCircle, ScrollText, Target } from "lucide-react"
import * as api from "../../lib/api"
import { useCvDocuments, useRuns } from "../../lib/queries"
import { formatRelativeDate, runTitle } from "../../lib/format"
import { toastError, toastSuccess } from "../../lib/toast"
import type { ProfessorMatch } from "../../lib/types"
import { Button } from "../ui/button"
import { ScoreBar } from "../ui/status"
import { SegmentedControl } from "../ui/form"
import { cn } from "../../lib/utils"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Markdown } from "../ui/MarkdownLazy"
import { PeekCard, PeekSummary } from "../ui/PeekCard"

type Source = "run" | "document"

const PEEK_HIDE_MS = 300

/** Interests scored at once by "Match against all interests". */
const PARALLEL_CHECKS = 3

interface Interest {
  key: string
  source: Source
  id: string
  title: string
  detail: string
}

/** Pick one interest for its breakdown, or score all at once; a good fit can be kept as a match. */
export function MatchProfessorDialog({
  professor,
  open,
  onOpenChange,
  runId,
}: {
  professor: { id: string; name: string }
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The run to select first: a match's own run when recalculating it. */
  runId?: string
}) {
  const { data: runs } = useRuns()
  const { data: documents } = useCvDocuments()
  const [source, setSource] = React.useState<Source>("run")
  const [picked, setPicked] = React.useState<string | null>(runId ? `run:${runId}` : null)
  const [results, setResults] = React.useState<Record<string, ProfessorMatch>>({})
  const [checking, setChecking] = React.useState<Set<string>>(new Set())
  const [saving, setSaving] = React.useState(false)
  const qc = useQueryClient()
  const navigate = useNavigate()

  const interestDocs = (documents ?? []).filter((d) => d.kind === "interest")
  const texts = useQueries({
    queries: interestDocs.map((d) => ({
      queryKey: ["document", d.id],
      queryFn: () => api.getCvDocument(d.id),
      enabled: source === "document",
    })),
  })
  const listed: Interest[] =
    source === "run"
      ? (runs ?? []).map((r) => ({ key: `run:${r.id}`, source, id: r.id, title: runTitle(r), detail: r.interest_statement }))
      : interestDocs.map((d, i) => ({
          key: `document:${d.id}`,
          source,
          id: d.id,
          title: d.title,
          detail: texts[i]?.data?.markdown.trim() || (d.updated_at ? `Edited ${formatRelativeDate(d.updated_at)}` : ""),
        }))
  const selected = listed.find((i) => i.key === picked) ?? listed[0] ?? null

  async function check(interest: Interest) {
    setChecking((prev) => new Set(prev).add(interest.key))
    try {
      const out = await api.matchProfessor(professor.id, interest.source === "run" ? { run_id: interest.id } : { document_id: interest.id })
      setResults((prev) => ({ ...prev, [interest.key]: out }))
    } catch (e) {
      toastError(e, `Couldn't score against ${interest.title}`)
    } finally {
      setChecking((prev) => {
        const next = new Set(prev)
        next.delete(interest.key)
        return next
      })
    }
  }

  async function checkAll() {
    const queue = listed.filter((i) => !results[i.key] && !checking.has(i.key))
    const worker = async () => {
      for (let next = queue.shift(); next; next = queue.shift()) await check(next)
    }
    await Promise.all(Array.from({ length: PARALLEL_CHECKS }, worker))
  }

  async function save(interest: Interest) {
    setSaving(true)
    try {
      const out = await api.matchProfessor(professor.id, interest.source === "run" ? { run_id: interest.id } : { document_id: interest.id }, true)
      await Promise.all(["faculty", "professor", "candidate", "candidates", "candidate-search"].map((key) => qc.invalidateQueries({ queryKey: [key] })))
      toastSuccess(`${professor.name} saved to your matches`)
      onOpenChange(false)
      if (out.candidate_id) navigate(`/dossier/${out.candidate_id}`)
    } catch (e) {
      toastError(e, "Couldn't save the match")
    } finally {
      setSaving(false)
    }
  }

  const unscored = listed.filter((i) => !results[i.key]).length
  const ranked = [...listed].sort((a, b) => (results[b.key]?.score ?? -1) - (results[a.key]?.score ?? -1))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)} className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Check match</DialogTitle>
          <DialogDescription>How well {professor.name}'s papers fit your research interests.</DialogDescription>
        </DialogHeader>
        <DialogBody className="relative grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div className="min-w-0 space-y-3">
            <SegmentedControl
              label="Interests from"
              value={source}
              onChange={setSource}
              options={[
                { value: "run", label: "Runs" },
                { value: "document", label: "Documents" },
              ]}
            />
            {listed.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {source === "run" ? "No runs yet." : "No interest documents yet. Write one in Documents."}
              </p>
            ) : (
                ranked.map((i) => {
                  const result = results[i.key]
                  return (
                    <button
                      key={i.key}
                      type="button"
                      role="radio"
                      aria-checked={i.key === selected?.key}
                      onClick={() => setPicked(i.key)}
                      className={cn(
                        "block w-full cursor-pointer space-y-1 rounded-lg border px-3 py-2 text-left transition-colors",
                        i.key === selected?.key ? "border-tint bg-tint-soft" : "border-border hover:bg-accent",
                      )}
                    >
                      <Markdown className="min-w-0 flex-1 line-clamp-5 text-sm font-medium" text={i.detail}/>
                      <span className="flex items-start justify-between gap-2">
                        {i.detail && <span className="truncate block type-caption">{i.title}</span>}
                        {checking.has(i.key) ? (
                          <LoaderCircle className="size-3.5 shrink-0 animate-spin text-muted-foreground" aria-label="Scoring" />
                        ) : (
                          result && <ScoreBar score={result.score} className="shrink-0" />
                        )}
                      </span>
                    </button>
                  )
                })
            )}
          </div>
          <div className="sticky top-0 h-fit min-w-0 rounded-xl border border-border bg-muted/30 p-4">
            {selected ? (
              <Breakdown
                key={selected.key}
                interest={selected}
                result={results[selected.key]}
                checking={checking.has(selected.key)}
                saving={saving}
                onCheck={() => void check(selected)}
                onSave={() => void save(selected)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Pick an interest to see how well it fits.</p>
            )}
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={() => void checkAll()} disabled={unscored === 0 || checking.size > 0}>
            <Layers /> {checking.size > 0 ? "Scoring…" : unscored === 0 && listed.length > 0 ? "All interests scored" : "Match against all interests"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** A save is always against this one interest, never all of them. */
function Breakdown({
  interest,
  result,
  checking,
  saving,
  onCheck,
  onSave,
}: {
  interest: Interest
  result?: ProfessorMatch
  checking: boolean
  saving: boolean
  onCheck: () => void
  onSave: () => void
}) {
  const list = React.useRef<HTMLUListElement>(null)
  const [peeked, setPeeked] = React.useState<number | null>(null)
  const hideTimer = React.useRef<number | null>(null)
  const keepPeek = () => {
    if (hideTimer.current !== null) window.clearTimeout(hideTimer.current)
    hideTimer.current = null
  }
  const hidePeekSoon = () => {
    keepPeek()
    hideTimer.current = window.setTimeout(() => setPeeked(null), PEEK_HIDE_MS)
  }
  React.useEffect(() => keepPeek, [])
  const peekedPaper = peeked !== null ? result?.top_papers[peeked] : undefined
  if (!result)
    return (
      <div className="flex h-full flex-col gap-3">
        <p className="font-medium">{interest.title}</p>
        {interest.detail && (
          <div className="nice-scroll max-h-96 overflow-y-auto">
            <Markdown text={interest.detail} />
          </div>
        )}
        <div className="mt-auto flex flex-col items-start gap-2 pt-2">
          <p className="type-caption">Not scored against this interest yet.</p>
          <Button size="sm" onClick={onCheck} disabled={checking}>
            {checking ? <LoaderCircle className="animate-spin" /> : <Target />} {checking ? "Calculating…" : "Calculate match"}
          </Button>
        </div>
      </div>
    )
  return (
    <div className="space-y-4">
      <div className="space-y-2 pb-2 mb-4 border-b border-border">
        <p className="truncate font-medium">{interest.title}</p>
        <ScoreBar score={result.score} size="lg" />
        <p>
          Similarity: best of {result.papers_scored} {result.papers_scored === 1 ? "paper" : "papers"}, since one strongly
          aligned paper counts more than several loose ones.
        </p>
      </div>
      {result.fit && <FitJudgment fit={result.fit} />}
      {result.top_papers.length > 0 && (
        <div className="space-y-2">
          <p className="type-caption">Closest papers</p>
          <ul ref={list} className="-mx-2 space-y-1" onMouseEnter={keepPeek} onMouseLeave={hidePeekSoon}>
            {result.top_papers.map((p, i) => (
              <li
                key={p.title}
                onMouseEnter={() => setPeeked(i)}
                data-active={peeked === i || undefined}
                className={cn("flex items-start gap-3 rounded-lg px-2 py-1.5 text-sm transition-colors", peeked === i && "bg-fill-quiet")}
              >
                <ScrollText className="text-muted-foreground size-6" />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2">{p.title}</span>
                  {p.year && <span className="type-caption">{p.year}</span>}
                </span>
                <ScoreBar score={p.score} className="shrink-0" />
              </li>
            ))}
          </ul>
          {peekedPaper && (
            <PeekCard id={String(peeked)} list={list} label={peekedPaper.title} onEnter={keepPeek} onLeave={hidePeekSoon}>
              <PeekSummary
                icon={ScrollText}
                title={peekedPaper.title}
                meta={peekedPaper.year ? String(peekedPaper.year) : null}
                text={peekedPaper.abstract || "No abstract saved for this paper."}
              />
            </PeekCard>
          )}
        </div>
      )}
      {result.run_id ? (
        <Button className="w-full" onClick={onSave} disabled={saving}>
          <BookmarkPlus /> {saving ? "Saving…" : "Save as a match for this interest"}
        </Button>
      ) : (
        <p className="type-caption">No run uses this document yet, so this match can't be saved.</p>
      )}
    </div>
  )
}

const FIT_STEPS = ["Unrelated", "Tangential", "Related", "Strong", "Direct"]

/** Jev's fit reading: five steps, filled up to the one it settled on. */
function FitJudgment({ fit }: { fit: NonNullable<ProfessorMatch["fit"]> }) {
  const reached = Math.round(fit.level)
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{FIT_STEPS[reached] ?? fit.label} fit</span>
        <span className="type-caption tabular-nums">{Math.round(fit.confidence * 100)}% confident</span>
      </div>
      <div className="grid grid-cols-5 gap-1" aria-hidden>
        {FIT_STEPS.map((step, i) => (
          <span key={step} className={cn("h-1.5 rounded-full", i <= reached ? "bg-tint" : "bg-muted-foreground/20")} />
        ))}
      </div>
      <p className="type-caption">Judged from what the papers are about, not the words they share.</p>
    </div>
  )
}

export function CheckMatchButton({ professor }: { professor: { id: string; name: string } }) {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Target /> Check match
      </Button>
      {open && <MatchProfessorDialog professor={professor} open onOpenChange={setOpen} />}
    </>
  )
}
