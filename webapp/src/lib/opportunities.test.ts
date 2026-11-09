import { describe, expect, it } from "vitest"
import { countdownFor, deadlineLabel, googleCalendarUrl } from "./opportunities"
import type { Opportunity } from "./types"

const base = { rolling: false, deadline: "", is_open: true, days_left: null } as const

describe("deadline labels", () => {
  it("reads the days left, today and closed", () => {
    expect(deadlineLabel({ ...base, days_left: 12 })).toBe("12 days left")
    expect(deadlineLabel({ ...base, days_left: 1 })).toBe("1 day left")
    expect(deadlineLabel({ ...base, days_left: 0 })).toBe("Closes today")
    expect(deadlineLabel({ ...base, days_left: -3, is_open: false })).toBe("Closed")
    expect(deadlineLabel({ ...base, rolling: true })).toBe("Rolling")
    expect(deadlineLabel({ ...base, deadline: "End of March" })).toBe("End of March")
  })

  it("feeds the countdown: days left, rolling, closed and wording-only deadlines", () => {
    const day = { ...base, deadline_date: "2027-03-14" }
    expect(countdownFor({ ...day, days_left: 12 })).toEqual({ daysLeft: 12, date: "2027-03-14", label: undefined })
    expect(countdownFor({ ...day, rolling: true })).toEqual({ rolling: true })
    expect(countdownFor({ ...day, days_left: -2, is_open: false }).daysLeft).toBe(-1)
    expect(countdownFor({ ...base, deadline_date: null, deadline: "End of March" })).toEqual({
      daysLeft: null,
      date: null,
      label: "End of March",
    })
  })
})

describe("googleCalendarUrl", () => {
  it("makes an all-day event ending the next day, across a month end", () => {
    const opp = { title: "Seed Grant", organization: "Fund", deadline_date: "2027-01-31", summary: "", link: "https://x.example", source_url: "" } as Opportunity
    const url = new URL(googleCalendarUrl(opp) as string)
    expect(url.searchParams.get("dates")).toBe("20270131/20270201")
    expect(url.searchParams.get("text")).toBe("Deadline: Seed Grant (Fund)")
  })

  it("has nothing to add without a date", () => {
    expect(googleCalendarUrl({ deadline_date: null } as Opportunity)).toBeNull()
  })
})
