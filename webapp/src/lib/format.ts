import type { AuthUser } from "./types"

/** Server timestamps without a zone are UTC. NaN for none or junk. */
export function utcMs(iso: string | null | undefined): number {
  if (!iso) return NaN
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime()
}

/** Human date-time, falling back to the raw string when unparseable. */
export function formatDate(iso: string): string {
  const ms = utcMs(iso)
  return Number.isNaN(ms) ? iso : new Date(ms).toLocaleString()
}

/** "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function formatAgo(iso: string, now: number = Date.now()): string {
  const ms = utcMs(iso)
  if (Number.isNaN(ms)) return iso
  const seconds = Math.max(0, Math.round((now - ms) / 1000))
  if (seconds < 60) return "just now"
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)}d ago`
  return new Date(ms).toLocaleDateString()
}

/** A calendar day (yyyy-mm-dd) in the reader's words: "15 Mar 2027". */
export function formatDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

export function identityName(user: Pick<AuthUser, "display_name" | "email"> | null): string {
  return user?.display_name?.trim() || user?.email || ""
}
