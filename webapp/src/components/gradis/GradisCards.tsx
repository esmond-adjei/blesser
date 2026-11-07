import type * as React from "react"
import { useMatch } from "react-router-dom"
import type { TaskLogEvent } from "../../lib/types"
import type { CitationSource } from "../../lib/citations"
import type { PreviewRef } from "../../lib/previewRoutes"
import { useDetailPanelOptional } from "../layout/DetailPanel"
import { artifactPreview } from "./GradisArtifactPreview"
import { cn } from "../../lib/utils"
import { RecordCard, type RecordKind } from "../cards/RecordCard"

type SavedKind = Exclude<RecordKind, "suggestions">

const SAVED_KINDS = new Set<string>(["program", "application", "draft", "candidate", "school", "run", "professor", "document", "paper"])

type SavedCard = {
  key: string
  kind: RecordKind
  label: string
  /** Overrides the kind's name over the label. */
  eyebrow?: string
  sublabel: string | null
  to: string
  /** What the detail rail can preview; null opens the page (a document, a paper). */
  preview: PreviewRef | null
}

/** An update carries the record's id in its arguments; a create only in what it returned. */
type ArtifactSpec = {
  kind: SavedKind
  idIn?: string
  idOut?: string
  labelIn?: string
  labelOut?: string
  /** A second detail for the subline (the programme an application is for). */
  detailIn?: string
  detailOut?: string
  /** The run a programme hangs off, which its page needs. */
  runIn?: string
  runOut?: string
}

const ARTIFACTS: Record<string, ArtifactSpec> = {
  save_program: {
    kind: "program",
    idOut: "program_id",
    labelIn: "program_name",
    detailIn: "school_name",
    runIn: "run_id",
  },
  create_program: {
    kind: "program",
    idOut: "id",
    labelIn: "name",
    detailOut: "school_name",
    runOut: "run_id",
  },
  update_program: {
    kind: "program",
    idIn: "program_id",
    labelIn: "name",
    detailOut: "school_name",
    runOut: "run_id",
  },
  save_application: {
    kind: "application",
    idOut: "application_id",
    labelIn: "school",
    detailIn: "program",
  },
  create_application: {
    kind: "application",
    idOut: "id",
    labelIn: "school",
    detailIn: "program",
  },
  update_application: {
    kind: "application",
    idIn: "application_id",
    labelOut: "school",
    detailOut: "program",
  },
  save_email_draft: {
    kind: "draft",
    idOut: "draft_id",
    labelIn: "subject",
  },
  update_draft: {
    kind: "draft",
    idIn: "draft_id",
    labelOut: "subject",
  },
  create_school: { kind: "school", idOut: "id", labelIn: "name" },
  update_school: { kind: "school", idIn: "school_id", labelIn: "name" },
  create_professor: { kind: "professor", idOut: "id", labelIn: "name", labelOut: "name", detailOut: "school_name" },
  update_professor: { kind: "professor", idIn: "professor_id", labelOut: "name", detailOut: "school_name" },
  save_professor_papers: { kind: "professor", idIn: "professor_id", labelOut: "name", detailOut: "school_name" },
  create_run: { kind: "run", idOut: "run_id" },
  update_run: { kind: "run", idIn: "run_id" },
  set_run_status: { kind: "run", idIn: "run_id" },
  update_candidate: { kind: "candidate", idIn: "candidate_id" },
  review_candidate: { kind: "candidate", idIn: "candidate_id" },
}

/** What a record is called when it has no name of its own. */
const KIND_FALLBACKS: Record<SavedKind, string> = {
  professor: "Professor",
  document: "Document",
  paper: "Paper",
  program: "Programme",
  application: "Application updated",
  draft: "Draft updated",
  candidate: "Candidate",
  school: "School",
  run: "Run",
}

/** Labels the tool's own words carry, when they say more than the name. */
const SPECIAL_LABELS: Record<string, string> = {
  review_candidate: "Match review",
  save_professor_papers: "Papers saved",
}

/** The one read that shows a card: Gradis calls it when the student asks
 * to see a record, or when it suggests looking at one. Other reads
 * and citations stay in the trace. */
const SHOW_TOOL = "show_record"

function arg(event: TaskLogEvent, key: string): unknown {
  const input = event.input
  if (!input || typeof input !== "object") return undefined
  return (input as Record<string, unknown>)[key]
}

function inputText(event: TaskLogEvent, key: string): string | null {
  const v = arg(event, key)
  return typeof v === "string" && v.trim() ? v : null
}

function previewValue(preview: unknown, key: string): string | null {
  if (typeof preview !== "string") return null
  try {
    const obj = JSON.parse(preview) as Record<string, unknown>
    const v = obj?.[key]
    if (typeof v === "string" && v) return v
  } catch {
    /* truncated preview is not valid JSON — fall through to the regex */
  }
  const m = preview.match(new RegExp(`"${key}"\\s*:\\s*"([^"]+)"`))
  return m ? m[1] : null
}

function pick(event: TaskLogEvent, keys: (string | undefined)[]): string | null {
  for (const key of keys) {
    if (!key) continue
    const v = inputText(event, key) ?? previewValue(event.result_preview, key)
    if (v) return v
  }
  return null
}

function hrefFor(kind: SavedKind, id: string, runId: string | null): string | null {
  switch (kind) {
    case "professor":
      return `/professors/${id}`
    case "document":
      return `/documents/${id}`
    case "paper":
      return null
    case "application":
      return `/applications/${id}`
    case "candidate":
      return `/dossier/${id}`
    case "draft":
      return `/outbox/${id}`
    case "program":
      // A programme's page hangs off its run.
      return runId ? `/runs/${runId}/programmes/${id}` : null
    case "school":
      return `/schools/${id}`
    case "run":
      return `/runs/${id}`
  }
}

function previewFor(
  kind: SavedKind,
  id: string,
  runId: string | null,
): PreviewRef | null {
  switch (kind) {
    case "professor":
      return { kind: "professor", id }
    case "document":
    case "paper":
      return null
    case "application":
      return { kind: "application", id }
    case "candidate":
      return { kind: "candidate", id }
    case "draft":
      return { kind: "draft", id }
    case "program":
      return runId ? { kind: "program", id, runId } : null
    case "school":
      return { kind: "school", id }
    case "run":
      return { kind: "run", id }
  }
}

/** Whether two previews point at the same record; a programme also needs
 * the run its page hangs off. */
function samePreview(a: PreviewRef | null | undefined, b: PreviewRef | null | undefined): boolean {
  if (!a || !b || a.kind !== b.kind) return false
  if (a.kind === "program" && b.kind === "program") return a.id === b.id && a.runId === b.runId
  return a.id === b.id
}

/** Records the turn created, edited or showed, as deep-link cards that
 * mirror TaskCard saved items. */
function savedCards(events: TaskLogEvent[]): SavedCard[] {
  const cards: SavedCard[] = []
  const seen = new Set<string>()
  const push = (c: SavedCard) => {
    if (!seen.has(c.key)) {
      seen.add(c.key)
      cards.push(c)
    }
  }
  const pushSource = (source: CitationSource) => {
    if (!source.id || !source.href || !SAVED_KINDS.has(source.kind)) return
    const kind = source.kind as SavedKind
    const runId = source.href.match(/^\/runs\/([^/]+)\/programmes\//)?.[1] ?? null
    push({
      key: `${kind}:${source.id}`,
      kind,
      label: source.title,
      sublabel: source.subtitle || null,
      to: source.href,
      preview: previewFor(kind, source.id, runId),
    })
  }
  for (const t of events) {
    // Text entries of the turn log are not tool calls.
    if (!t.tool) continue
    if (!t.ok) continue
    if (t.tool === "cv_suggest_changes" || t.tool === "suggest_changes") {
      const documentId = inputText(t, "document_id")
      const versionId = inputText(t, "version_id")
      if (documentId) {
        const suggestions = arg(t, "suggestions")
        const count = Array.isArray(suggestions) ? suggestions.length : 0
        push({
          key: `cv_suggestions:${documentId}:${versionId ?? "base"}:${t.turn}`,
          kind: "suggestions",
          label: `${count} suggested change${count === 1 ? "" : "s"}`,
          sublabel: "Accept or reject them in the editor",
          to: `/documents/${documentId}${versionId ? `?version=${versionId}` : ""}`,
          preview: null,
        })
      }
      continue
    }
    if (t.tool === SHOW_TOOL) {
      for (const source of t.sources ?? []) pushSource(source)
    }
    const spec = ARTIFACTS[t.tool]
    if (!spec) continue
    const id = pick(t, [spec.idIn, spec.idOut])
    if (!id) continue
    const runId = pick(t, [spec.runIn, spec.runOut])
    const to = hrefFor(spec.kind, id, runId)
    if (!to) continue
    const detail = pick(t, [spec.detailIn, spec.detailOut])
    const label =
      t.tool === "review_candidate"
        ? arg(t, "approved") === true
          ? "Candidate approved"
          : "Candidate rejected"
        : (pick(t, [spec.labelIn, spec.labelOut]) ?? KIND_FALLBACKS[spec.kind])
    push({
      key: `${spec.kind}:${id}`,
      kind: spec.kind,
      label,
      eyebrow: SPECIAL_LABELS[t.tool],
      sublabel: detail,
      to,
      preview: previewFor(spec.kind, id, runId),
    })
  }
  return cards
}

export function GradisSavedCards({ tools }: { tools: TaskLogEvent[] }) {
  const cards = savedCards(tools)
  // On the full chat page a card opens in the detail rail; elsewhere it
  // stays a plain deep link.
  const chatPage = useMatch("/chat/*") !== null
  // Absent on the standalone CV page, where cards stay plain deep links.
  const detailPanel = useDetailPanelOptional()
  const openPreview = detailPanel?.previewRef ?? null
  if (cards.length === 0) return null

  function onOpen(e: React.MouseEvent, card: SavedCard) {
    if (!chatPage || !card.preview || !detailPanel) return
    // Modified clicks still open the full page (new tab, new window).
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
    const preview = artifactPreview(card.preview)
    if (!preview) return
    e.preventDefault()
    detailPanel.setPanel(preview.node, { title: card.label, ref: card.preview, actions: preview.actions })
  }

  return (
    <div className={cn("mt-2 grid gap-2", cards.length > 5 ? "grid-cols-2" : "grid-cols-1")}>
      {cards.map((c) => (
        <RecordCard
          key={c.key}
          kind={c.kind}
          eyebrow={c.eyebrow}
          label={c.label}
          sublabel={c.sublabel}
          to={c.to}
          onClick={(e) => onOpen(e, c)}
          active={samePreview(c.preview, openPreview)}
          className="max-w-[80%]"
        />
      ))}
    </div>
  )
}
