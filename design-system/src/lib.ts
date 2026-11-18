import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

const TYPE_STYLES = ["hero", "title-1", "title-2", "numeral", "title-3", "headline", "body", "callout", "footnote", "caption", "code"]

// Without these, tailwind-merge reads text-callout as a colour and drops text-ink beside it.
const twMerge = extendTailwindMerge({
  extend: {
    theme: { text: TYPE_STYLES, shadow: ["elevation-1", "elevation-2", "elevation-3"] },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "21 Nov" from a yyyy-mm-dd day, adding the year only when it isn't this year. */
export function formatDay(day: string, now: Date = new Date()): string {
  const [y, m, d] = day.split("-").map(Number)
  if (!y || !m || !d) return day
  return y === now.getFullYear() ? `${d} ${MONTHS[m - 1]}` : `${d} ${MONTHS[m - 1]} ${y}`
}

/** Whole days from today to a yyyy-mm-dd day, counted in Africa/Accra (UTC, no DST). */
export function daysUntil(day: string, now: Date = new Date()): number {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return Math.round((Date.parse(`${day}T00:00:00Z`) - today) / 86_400_000)
}
