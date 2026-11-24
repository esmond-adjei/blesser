import { describe, expect, it } from "vitest"
import { deadlineParts, sectionFor, sectionize } from "./feed"

const item = (over: Partial<Parameters<typeof sectionFor>[0]> = {}) => ({
  rolling: false,
  days_left: 40 as number | null,
  is_open: true,
  is_new: false,
  created_at: "2026-11-01T10:00:00",
  ...over,
})

describe("feed sections", () => {
  it("buckets by deadline", () => {
    const key = (o: ReturnType<typeof item>) => sectionFor(o, "deadline", null)?.title
    expect(key(item({ days_left: 0 }))).toBe("Closing this week")
    expect(key(item({ days_left: 7 }))).toBe("Closing this week")
    expect(key(item({ days_left: 20 }))).toBe("Closing this month")
    expect(key(item({ days_left: 90 }))).toBe("Later")
    expect(key(item({ rolling: true, days_left: null }))).toBe("Rolling or no date")
    expect(key(item({ days_left: -2, is_open: false }))).toBe("Closed")
  })

  it("splits the newest list at the last visit", () => {
    const last = Date.UTC(2026, 10, 20)
    expect(sectionFor(item({ created_at: "2026-11-22T08:00:00" }), "new", last)?.title).toBe("New since your last visit")
    expect(sectionFor(item({ created_at: "2026-11-19T08:00:00", is_new: true }), "new", last)?.title).toBe("This week")
    expect(sectionFor(item({ created_at: "2026-11-22T08:00:00", is_new: true }), "new", null)?.title).toBe("This week")
    expect(sectionFor(item(), "new", last)?.title).toBe("Earlier")
  })

  it("leaves ranked sorts unsectioned", () => {
    expect(sectionFor(item(), "for_you", null)).toBeNull()
    expect(sectionize([item(), item()], "relevance", null)).toEqual([{ key: "all", title: "", items: [item(), item()] }])
  })

  it("groups contiguous runs without reordering", () => {
    const a = item({ days_left: 2 })
    const b = item({ days_left: 5 })
    const c = item({ days_left: 60 })
    const sections = sectionize([a, b, c], "deadline", null)
    expect(sections.map((s) => [s.title, s.items.length])).toEqual([
      ["Closing this week", 2],
      ["Later", 1],
    ])
  })
})

describe("deadlineParts", () => {
  const base = { rolling: false, days_left: 9 as number | null, is_open: true, deadline: "", deadline_date: "2026-11-27" as string | null }
  const now = new Date("2026-11-18T12:00:00Z")

  it("gives the date, and days left only when close", () => {
    expect(deadlineParts(base, now)).toEqual({ date: "closes 27 Nov", daysLeft: 9, urgent: false })
    expect(deadlineParts({ ...base, days_left: 40 }, now)).toEqual({ date: "closes 27 Nov", daysLeft: null, urgent: false })
    expect(deadlineParts({ ...base, days_left: 3 }, now).urgent).toBe(true)
    expect(deadlineParts({ ...base, days_left: 0 }, now)).toEqual({ date: null, daysLeft: 0, urgent: true })
  })

  it("reads rolling, closed and wording-only deadlines", () => {
    expect(deadlineParts({ ...base, rolling: true }, now).date).toBe("rolling")
    expect(deadlineParts({ ...base, is_open: false, days_left: -1 }, now).date).toBe("closed")
    expect(deadlineParts({ ...base, deadline_date: null, days_left: null, deadline: "End of March" }, now).date).toBe("End of March")
  })
})
