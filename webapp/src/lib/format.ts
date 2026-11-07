import { API_BASE } from "./api"
import type { AuthUser, RunListItem } from "./types"

/** Display title for a run: field, region, or the preselected-list label. */
export function runTitle(run: RunListItem): string {
  if (run.region === "(preselected list)") return "Preselected programs"
  // The composer may leave the field to the interest text.
  const field = run.field.trim() || run.interest_statement.split(/[.,;:\n]/)[0].trim().slice(0, 48)
  // Joined with words, not a separator dot: "Computer Science in Canada".
  return run.region ? `${field} in ${run.region}` : `${field}, anywhere`
}

const DEGREE_LABELS: Record<string, string> = {
  phd: "PhD",
  masters: "Master's",
  mba: "MBA",
  jd: "JD",
  md: "MD",
  pharmd: "PharmD",
  mph: "MPH",
  dds: "DDS",
  either: "PhD or Master's",
}

/** "phd, masters" -> "PhD and Master's"; custom degrees stay as typed. */
export function formatDegrees(degreeLevel: string): string {
  const parts = degreeLevel
    .split(",")
    .map((d) => d.trim())
    .filter(Boolean)
    .map((d) => DEGREE_LABELS[d.toLowerCase()] ?? d)
  if (parts.length === 0) return "PhD/MS"
  if (parts.length === 1) return parts[0]
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`
}

/** Human date-time, falling back to the raw string when unparseable. */
export function formatDate(iso: string): string {
  const ms = utcMs(iso)
  return Number.isNaN(ms) ? iso : new Date(ms).toLocaleString()
}

/** Compact duration: 45s, 2m 5s, 3h 12m, 2d 4h. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

/** Server timestamps without a zone are UTC. NaN for none or junk. */
export function utcMs(iso: string | null | undefined): number {
  if (!iso) return NaN
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime()
}

/** Execution seconds from started_at to finished_at; duration_seconds includes queue time. */
export function taskDurationSeconds(
  t: {
    started_at?: string | null
    finished_at?: string | null
    duration_seconds?: number | null
  },
  now: number = Date.now(),
): number | null {
  const start = utcMs(t.started_at)
  if (!Number.isNaN(start)) {
    const end = t.finished_at ? utcMs(t.finished_at) : now
    if (!Number.isNaN(end)) return Math.max(0, (end - start) / 1000)
  }
  return t.duration_seconds ?? null
}

function localDayStart(ms: number): number {
  const d = new Date(ms)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

// Calendar-day difference on the viewer's clock: 11pm viewed at 2am is
// "yesterday". Timestamps without a zone are UTC.
export function formatRelativeDate(iso: string, now: number = Date.now()): string {
  const ms = utcMs(iso)
  if (Number.isNaN(ms)) return iso
  // Rounded: a day across a DST change is 23 or 25 hours long.
  const dayDiff = Math.round((localDayStart(now) - localDayStart(ms)) / 86_400_000)
  if (dayDiff <= 0) return "today"
  if (dayDiff === 1) return "yesterday"
  if (dayDiff < 30) return `${dayDiff} days ago`
  if (dayDiff < 60) return "last month"
  if (dayDiff < 365) return `${Math.floor(dayDiff / 30)} months ago`
  if (dayDiff < 730) return "last year"
  if (dayDiff < 3650) return `${Math.floor(dayDiff / 365)} years ago`
  return "older"
}

/** Minutes and hours for recent times ("just now", "5m ago", "3h ago"),
 * calendar days after that (formatRelativeDate). */
export function formatAgo(iso: string, now: number = Date.now()): string {
  const ms = utcMs(iso)
  if (Number.isNaN(ms)) return iso
  const minutes = Math.floor((now - ms) / 60_000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)}h ago`
  return formatRelativeDate(iso, now)
}

/** The one identity label: chosen name, else the email. */
export function identityName(user: Pick<AuthUser, "display_name" | "email"> | null): string {
  return user?.display_name?.trim() || user?.email || ""
}

/** Absolute URL for an API-served asset path (avatars), honouring VITE_API_URL. */
export function apiAssetUrl(path: string | null | undefined): string | null {
  return path ? `${API_BASE}${path}` : null
}

export const fmt = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 10_000 ? `${Math.round(n / 1000)}k` : n.toLocaleString()
