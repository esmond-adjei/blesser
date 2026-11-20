import { daysUntil, formatDay } from "@blesser/ui"
import type { PublicOpportunity, ShareFormat, SharedTeaser } from "../api"
import { categoryLabel, kindLabel } from "../format"

export type { ShareFormat, SharedTeaser }
export const SIZES: Record<ShareFormat, { width: number; height: number }> = {
  square: { width: 1080, height: 1080 },
  wide: { width: 1200, height: 630 },
  story: { width: 1080, height: 1920 },
}
export const isFormat = (v: string | undefined): v is ShareFormat => !!v && Object.hasOwn(SIZES, v)

export type ShareCard = {
  label: string
  title: string
  offer: string
  organization: string
  deadline: string
  closed: boolean
  seed: string
  category: string
  kind: string
  host: string
}

const squash = (s: string) => (s || "").replace(/\s+/g, " ").trim()

/** Cut at a word boundary, ending in an ellipsis. */
export function clip(text: string, limit: number): string {
  const s = squash(text)
  if (s.length <= limit) return s
  let cut = s.slice(0, limit - 1)
  const space = cut.lastIndexOf(" ")
  if (space > limit / 2) cut = cut.slice(0, space)
  return cut.replace(/[\s,;:.\-–—(/]+$/, "") + "…"
}

function deadlineLabel(t: Pick<SharedTeaser, "status" | "rolling" | "deadline_date" | "deadline">, now: Date): string {
  if (t.status === "archived") return "Closed"
  if (t.rolling) return "Rolling, apply any time"
  if (t.deadline_date) return daysUntil(t.deadline_date, now) < 0 ? "Closed" : `Closes ${formatDay(t.deadline_date)}`
  const raw = squash(t.deadline)
  return raw && raw.length <= 40 ? `Deadline: ${raw}` : ""
}

/** "Scholarship for students"; just the kind when the audience is unknown. */
export function shareLabel(kind: string, category: string): string {
  const k = kindLabel(kind)
  const c = category ? categoryLabel(category) : ""
  if (!k) return c
  return c ? `${k} for ${c.toLowerCase()}` : k
}

export function cardFromTeaser(t: SharedTeaser, host: string, now = new Date()): ShareCard {
  const deadline = deadlineLabel(t, now)
  return {
    label: shareLabel(t.kind, t.category),
    title: clip(t.title, 160),
    offer: clip(t.benefits.split("\n")[0] ?? "", 220),
    organization: clip(t.organization, 120),
    deadline,
    closed: deadline === "Closed",
    seed: t.seed,
    category: t.category,
    kind: t.kind,
    host,
  }
}

export function teaserFromPublic(o: PublicOpportunity): SharedTeaser {
  return {
    slug: o.slug,
    audience: "public",
    status: o.closed ? "archived" : "published",
    title: o.title,
    organization: o.organization,
    category: o.category,
    kind: o.kind,
    benefits: o.benefits,
    deadline: o.deadline,
    deadline_date: o.deadline_date,
    rolling: o.rolling,
    seed: o.slug,
  }
}
