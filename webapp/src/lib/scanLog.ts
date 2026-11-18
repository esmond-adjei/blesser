import { utcMs } from "./format"
import type { Scan, ScanTaskEvent } from "./types"

export type LineKind = "search" | "read" | "save" | "update" | "note" | "other"

export interface LogLine {
  kind: LineKind
  text: string
  /** Link target: an external page for reads, an opportunity id for saves. */
  href?: string
  opportunityId?: string
  failed: boolean
  reason?: string
  at?: string
}

function parse(preview: string | undefined): Record<string, unknown> {
  if (!preview) return {}
  try {
    const value = JSON.parse(preview)
    return value && typeof value === "object" ? (value as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

/** "gea.gov.gh/youstart" from a URL; the input when it isn't one. */
export function shortUrl(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.replace(/\/$/, "")
    const short = u.hostname.replace(/^www\./, "") + path
    return short.length > 72 ? `${short.slice(0, 71)}…` : short
  } catch {
    return url
  }
}

/** First sentence of a tool error, without the tool-name prefix. */
export function errorReason(preview: string | undefined): string {
  const raw = parse(preview).error
  const text = typeof raw === "string" ? raw : preview ?? ""
  const clean = text.replace(/^[a-z_]+ failed:\s*/i, "").trim()
  const first = clean.match(/^.*?[.!?](\s|$)/)?.[0]?.trim() ?? clean
  return first.length > 160 ? `${first.slice(0, 159)}…` : first
}

export function describeEvent(event: ScanTaskEvent): LogLine {
  const input = event.input ?? {}
  const failed = event.ok === false
  const at = event.at
  if (event.kind === "turn") return { kind: "note", text: (event.note ?? "").trim(), failed: false, at }
  if (event.tool === "search_web") {
    const query = String(input.query ?? "")
    return failed
      ? { kind: "search", text: `Search for “${query}” didn't run`, failed, reason: errorReason(event.result_preview), at }
      : { kind: "search", text: `Searched “${query}”`, failed, at }
  }
  if (event.tool === "fetch_page") {
    const url = String(input.url ?? "")
    return { kind: "read", text: `${failed ? "Couldn't read" : "Read"} ${shortUrl(url)}`, href: url || undefined, failed, reason: failed ? errorReason(event.result_preview) : undefined, at }
  }
  if (event.tool === "crawl_candidate") {
    const url = typeof input.url === "string" ? input.url : ""
    return { kind: "read", text: url ? `Checked ${shortUrl(url)}` : "Checked a candidate", href: url || undefined, failed: false, at }
  }
  if (event.tool === "save_opportunity") {
    const title = String(input.title ?? "an opportunity")
    if (failed) return { kind: "save", text: `Not saved: ${title}`, failed, reason: errorReason(event.result_preview), at }
    const result = parse(event.result_preview)
    const id = typeof result.opportunity_id === "string" && result.status !== "in_review" ? result.opportunity_id : undefined
    const created = result.created !== false
    return { kind: created ? "save" : "update", text: `${created ? "Saved" : "Updated"} ${title}`, opportunityId: id, failed, at }
  }
  return { kind: "other", text: event.tool ? `Used ${event.tool.replaceAll("_", " ")}` : "Step", failed, at }
}

/** Milliseconds a task or scan ran; up to now while it is still going. */
export function elapsedMs(start: string | null | undefined, end: string | null | undefined, now = Date.now()): number | null {
  const s = utcMs(start)
  if (Number.isNaN(s)) return null
  const e = end ? utcMs(end) : now
  return Number.isNaN(e) ? null : Math.max(0, e - s)
}

export function scanElapsedMs(scan: Scan, now = Date.now()): number | null {
  const tasks = scan.tasks ?? []
  const starts = tasks.map((t) => utcMs(t.started_at)).filter((n) => !Number.isNaN(n))
  const ends = tasks.map((t) => utcMs(t.finished_at)).filter((n) => !Number.isNaN(n))
  const start = starts.length ? Math.min(...starts) : utcMs(scan.started_at ?? scan.created_at)
  if (Number.isNaN(start)) return null
  if (scan.status === "running") return Math.max(0, now - start)
  const finished = scan.finished_at ? utcMs(scan.finished_at) : ends.length ? Math.max(...ends) : NaN
  return Number.isNaN(finished) ? null : Math.max(0, finished - start)
}

/** "45s", "4m", "1h 12m". */
export function formatDuration(ms: number | null): string {
  if (ms == null) return ""
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

/** Local "14:05" for a log line. */
export function clock(iso: string | undefined): string {
  const ms = utcMs(iso)
  if (Number.isNaN(ms)) return ""
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })
}
