import type { CountdownProps } from "@blesser/ui"
import type { PublicOpportunity } from "./api"

export const CATEGORY_LABELS: Record<string, string> = {
  startup: "Startups",
  research: "Researchers",
  student: "Students",
}

export const KIND_LABELS: Record<string, string> = {
  grant: "Grant",
  fellowship: "Fellowship",
  scholarship: "Scholarship",
  accelerator: "Accelerator",
  incubator: "Incubator",
  competition: "Competition",
  internship: "Internship",
  call_for_proposals: "Call for proposals",
  training: "Training",
  conference: "Conference",
  job: "Job",
  other: "Other",
}

export const CLOSING_WITHIN = [7, 14, 30, 60]

export const kindLabel = (kind: string) => KIND_LABELS[kind] ?? kind
export const categoryLabel = (category: string) => CATEGORY_LABELS[category] ?? category

export function countdownFor(opp: PublicOpportunity): CountdownProps {
  if (opp.rolling && !opp.closed) return { rolling: true }
  const closed = opp.closed || !opp.is_open || (opp.days_left !== null && opp.days_left < 0)
  return { daysLeft: closed ? -1 : opp.days_left, date: opp.deadline_date, label: opp.deadline || undefined }
}

/** "Checked today", "Checked 3 days ago"; null when never verified. */
export function checkedAgo(verifiedAt: string | null, now = new Date()): string | null {
  if (!verifiedAt) return null
  const then = Date.parse(verifiedAt)
  if (Number.isNaN(then)) return null
  const days = Math.max(0, Math.floor((now.getTime() - then) / 86_400_000))
  if (days === 0) return "Checked today"
  if (days === 1) return "Checked yesterday"
  return `Checked ${days} days ago`
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return ""
  }
}

export function isHttpUrl(url: string): boolean {
  try {
    return ["http:", "https:"].includes(new URL(url).protocol)
  } catch {
    return false
  }
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n.toLocaleString("en-GB")} ${n === 1 ? one : many}`
}
