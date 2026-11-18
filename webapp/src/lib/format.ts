import { formatDay as dsFormatDay } from "@blesser/ui"
import type { AuthUser } from "./types"

/** Server timestamps without a zone are UTC. NaN for none or junk. */
export function utcMs(iso: string | null | undefined): number {
  if (!iso) return NaN
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime()
}

const localDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

/** "9 Nov, 14:05", with the year only when it isn't this year. Raw string when unparseable. */
export function formatDate(iso: string, now: Date = new Date()): string {
  const ms = utcMs(iso)
  if (Number.isNaN(ms)) return iso
  const d = new Date(ms)
  return `${dsFormatDay(localDay(d), now)}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
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
  return dsFormatDay(localDay(new Date(ms)), new Date(now))
}

/** A calendar day (yyyy-mm-dd): "15 Mar", or "15 Mar 2027" in another year. */
export const formatDay = dsFormatDay

/** Display name, else the email's local part: a short label for avatars and menus. */
export function accountName(user: Pick<AuthUser, "display_name" | "email"> | null): string {
  return user?.display_name?.trim() || user?.email.split("@")[0] || ""
}

export function initials(name: string): string {
  const all = name.split(/[\s._-]+/).filter(Boolean)
  const lettered = all.filter((w) => /^\p{L}/u.test(w))
  const words = lettered.length ? lettered : all
  if (!words.length) return "?"
  const first = words[0][0]
  const last = words.length > 1 ? words[words.length - 1][0] : ""
  return (first + last).toUpperCase()
}
