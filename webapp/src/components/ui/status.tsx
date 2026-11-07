import * as React from "react"
import { cn } from "../../lib/utils"
import { sentence } from "../../lib/entities"

const RUN_STATUS: Record<string, { tone: Tone; label: string; live?: boolean }> = {
  running: { tone: "info", label: "Researching", live: true },
  done: { tone: "success", label: "Done" },
  paused: { tone: "warning", label: "Paused" },
  // Stopped on purpose, not a failure.
  cancelled: { tone: "neutral", label: "Cancelled" },
}

/** `live` false stills a running pill whose worker has nothing open (a stall). */
export function RunStatusBadge({ status, live = true }: { status: string; live?: boolean }) {
  const s = RUN_STATUS[status] ?? { tone: "neutral" as Tone, label: sentence(status) }
  return (
    <StatusPill tone={s.tone} className={s.live && live ? "g-pill--live" : undefined}>
      {s.label}
    </StatusPill>
  )
}

type Tone = "neutral" | "info" | "success" | "danger" | "warning"

const TONE: Record<Tone, string> = {
  neutral: "g-pill",
  info: "g-pill g-pill--info",
  success: "g-pill g-pill--positive",
  danger: "g-pill g-pill--critical",
  warning: "g-pill g-pill--caution",
}

/** Status pill: dot plus sentence-case label; counts and facts use plain text instead. */
function StatusPill({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  return <span className={cn(TONE[tone], className)}>{children}</span>
}

const CANDIDATE_TONE: Record<string, Tone> = {
  approved: "success",
  rejected: "danger",
  drafted: "info",
  sent: "success",
}

/** `quiet` hides default states (scored and earlier); only a change earns a pill. */
export function CandidateStatusBadge({ status, quiet = false }: { status: string; quiet?: boolean }) {
  const tone = CANDIDATE_TONE[status]
  if (quiet && !tone) return null
  return <StatusPill tone={tone ?? "neutral"}>{sentence(status)}</StatusPill>
}

const APPLICATION_TONE: Record<string, Tone> = {
  wishlist: "neutral",
  applying: "warning",
  submitted: "info",
  interview: "info",
  offer: "success",
  rejected: "danger",
}

export function ApplicationStatusBadge({ status }: { status: string }) {
  return <StatusPill tone={APPLICATION_TONE[status] ?? "neutral"}>{sentence(status)}</StatusPill>
}

const TASK_TYPE_LABELS: Record<string, string> = {
  discover_programs: "Discover programs",
  research_professor: "Research faculty",
  research_one_professor: "Research professor",
  draft_email: "Draft email",
  discover_opportunities: "Find opportunities",
}

export function TaskTypeLabel({ type }: { type: string }) {
  return <span className="font-medium">{TASK_TYPE_LABELS[type] ?? type}</span>
}

/** Same cut-offs as api/candidates/scoring.py SCORE_BANDS (embeddings). */
function scoreBand(score: number): "strong" | "moderate" | "weak" | "unrelated" {
  const s = score > 1 ? score / 100 : score
  return s >= 0.45 ? "strong" : s >= 0.3 ? "moderate" : s >= 0.15 ? "weak" : "unrelated"
}

/** Fit score bar; `size="lg"` widens it and names the band. */
export function ScoreBar({
  score,
  size = "sm",
  dataTooltip,
  className,
}: {
  score: number | null
  size?: "sm" | "lg"
  dataTooltip?: string | undefined | null
  className?: string
}) {
  if (score == null) return null
  const pct = score <= 1 ? score * 100 : score
  const band = scoreBand(score)
  const lg = size === "lg"
  return (
    <span
      className={cn("g-fit", lg && "g-fit--lg", className)}
      data-band={band === "unrelated" ? "weak" : band}
      data-tooltip={dataTooltip || `${sentence(band)} fit`}
    >
      <span className="g-fit__track">
        <span className="g-fit__bar" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </span>
      <span className="g-fit__value">{Math.round(pct)}%</span>
      {lg && <span className="g-fit__band">{sentence(band)} fit</span>}
    </span>
  )
}
