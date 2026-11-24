/** Sections, deadline wording and last-visit memory for the opportunities feed. */
import * as React from "react"
import { formatDay } from "@blesser/ui"
import { utcMs } from "./format"
import type { Opportunity, OpportunitySort } from "./types"

type FeedItem = Pick<Opportunity, "rolling" | "days_left" | "is_open" | "is_new" | "created_at">

export interface FeedSection<T> {
  key: string
  title: string
  items: T[]
}

const isClosed = (o: FeedItem) => !o.is_open || (o.days_left !== null && o.days_left < 0)

/** Which section an item falls in for this sort; null for ranked sorts. */
export function sectionFor(o: FeedItem, sort: OpportunitySort, lastVisit: number | null): { key: string; title: string } | null {
  if (sort === "deadline") {
    if (isClosed(o)) return { key: "closed", title: "Closed" }
    if (o.rolling || o.days_left === null) return { key: "open", title: "Rolling or no date" }
    if (o.days_left <= 7) return { key: "week", title: "Closing this week" }
    if (o.days_left <= 30) return { key: "month", title: "Closing this month" }
    return { key: "later", title: "Later" }
  }
  if (sort === "new") {
    if (lastVisit !== null && utcMs(o.created_at) > lastVisit) return { key: "since", title: "New since your last visit" }
    if (o.is_new) return { key: "week", title: "This week" }
    return { key: "earlier", title: "Earlier" }
  }
  return null
}

/** Groups contiguous runs in the server's order, so sections never reorder items. */
export function sectionize<T extends FeedItem>(items: T[], sort: OpportunitySort, lastVisit: number | null): FeedSection<T>[] {
  const out: FeedSection<T>[] = []
  for (const item of items) {
    const s = sectionFor(item, sort, lastVisit) ?? { key: "all", title: "" }
    const last = out[out.length - 1]
    if (last && last.key === s.key) last.items.push(item)
    else out.push({ ...s, key: out.some((x) => x.key === s.key) ? `${s.key}-${out.length}` : s.key, items: [item] })
  }
  return out
}

export interface DeadlineParts {
  /** "closes 27 Nov", "rolling", "closed", or the source's wording. */
  date: string | null
  /** Days left when close (14 or fewer). */
  daysLeft: number | null
  urgent: boolean
}

export function deadlineParts(o: Pick<Opportunity, "rolling" | "days_left" | "is_open" | "deadline" | "deadline_date">, now = new Date()): DeadlineParts {
  if (o.rolling) return { date: "rolling", daysLeft: null, urgent: false }
  if (!o.is_open || (o.days_left !== null && o.days_left < 0)) return { date: "closed", daysLeft: null, urgent: false }
  // "Closes today" already says the date.
  const date = o.days_left === 0 ? null : o.deadline_date ? `closes ${formatDay(o.deadline_date, now)}` : o.deadline || null
  const close = o.days_left !== null && o.days_left <= 14
  return { date, daysLeft: close ? o.days_left : null, urgent: close && (o.days_left ?? 99) <= 3 }
}

const LAST_VISIT_KEY = "blesser.opportunities.lastVisit"

function readLastVisit(): number | null {
  try {
    const value = Number(localStorage.getItem(LAST_VISIT_KEY))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

function writeLastVisit() {
  try {
    localStorage.setItem(LAST_VISIT_KEY, String(Date.now()))
  } catch {
    // Blocked storage only loses the divider next time.
  }
}

/** The previous visit's time in this browser; this visit is recorded on leaving. */
export function useLastVisit(): number | null {
  const [last] = React.useState(readLastVisit)
  React.useEffect(() => {
    window.addEventListener("pagehide", writeLastVisit)
    return () => {
      window.removeEventListener("pagehide", writeLastVisit)
      writeLastVisit()
    }
  }, [])
  return last
}
