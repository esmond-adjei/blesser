import { formatDay } from "../../lib/format"

export type CalendarView = "month" | "week" | "day" | "schedule"

export const SWATCH = { deadline: "bg-sun", todo: "bg-forest" } as const

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

export const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

/** A yyyy-mm-dd as local midnight; today when missing or junk. */
export function parseIso(value: string | null | undefined): Date {
  const m = value ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null
  if (!m) {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), now.getDate())
  }
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}

export const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)

export function startOfWeek(d: Date): Date {
  return addDays(d, -((d.getDay() + 6) % 7))
}

export function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor)
  return Array.from({ length: 7 }, (_, i) => addDays(start, i))
}

/** Monday-first weeks covering the whole month. */
export function monthDays(month: Date): Date[] {
  const start = startOfWeek(new Date(month.getFullYear(), month.getMonth(), 1))
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0)
  const days: Date[] = []
  for (let d = start; d <= last || days.length % 7; d = addDays(d, 1)) days.push(d)
  return days
}

/** First and last visible day (inclusive) for a view. */
export function visibleRange(view: CalendarView, anchor: Date): [string, string] {
  if (view === "day") return [iso(anchor), iso(anchor)]
  if (view === "week") {
    const days = weekDays(anchor)
    return [iso(days[0]), iso(days[6])]
  }
  if (view === "schedule") return [iso(new Date(anchor.getFullYear(), anchor.getMonth(), 1)), iso(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0))]
  const days = monthDays(anchor)
  return [iso(days[0]), iso(days[days.length - 1])]
}

export function shiftAnchor(view: CalendarView, anchor: Date, n: number): Date {
  if (view === "day") return addDays(anchor, n)
  if (view === "week") return addDays(anchor, 7 * n)
  return new Date(anchor.getFullYear(), anchor.getMonth() + n, 1)
}

export const monthTitle = (d: Date) => d.toLocaleDateString("en-GB", { month: "long", year: "numeric" })
export const weekday = (d: Date, width: "long" | "short" = "long") => d.toLocaleDateString("en-GB", { weekday: width })

export function periodTitle(view: CalendarView, anchor: Date): string {
  if (view === "day") return `${weekday(anchor)} ${formatDay(iso(anchor))}`
  if (view === "week") {
    const days = weekDays(anchor)
    const [a, b] = [days[0], days[6]]
    const mon = (d: Date) => d.toLocaleDateString("en-GB", { month: "short" })
    return a.getMonth() === b.getMonth()
      ? `${a.getDate()} - ${b.getDate()} ${mon(b)} ${b.getFullYear()}`
      : `${a.getDate()} ${mon(a)} - ${b.getDate()} ${mon(b)} ${b.getFullYear()}`
  }
  return monthTitle(anchor)
}
