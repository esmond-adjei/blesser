import { describe, expect, it } from "vitest"
import { accountName, formatAgo, formatDate, formatDay, initials } from "./format"

describe("accountName", () => {
  it("prefers the display name, else the email's local part", () => {
    expect(accountName({ display_name: " Ama Mensah ", email: "ama@x.org" })).toBe("Ama Mensah")
    expect(accountName({ display_name: null, email: "kofi.boateng@x.org" })).toBe("kofi.boateng")
    expect(accountName(null)).toBe("")
  })
})

describe("initials", () => {
  it("takes the first and last word", () => {
    expect(initials("Ama Serwaa Mensah")).toBe("AM")
    expect(initials("kofi.boateng")).toBe("KB")
    expect(initials("ama")).toBe("A")
    expect(initials("Ama Probe 22")).toBe("AP")
    expect(initials("")).toBe("?")
  })
})

describe("dates", () => {
  const now = new Date(2026, 10, 18, 12)
  it("drops the year for this year and keeps it otherwise", () => {
    expect(formatDay("2026-11-23", now)).toBe("23 Nov")
    expect(formatDay("2027-03-15", now)).toBe("15 Mar 2027")
  })
  it("writes older timestamps as a day, not numbers", () => {
    expect(formatAgo("2026-11-09T10:00:00Z", now.getTime())).toBe("9 Nov")
    expect(formatAgo("2025-12-30T10:00:00Z", now.getTime())).toBe("30 Dec 2025")
    expect(formatDate("2026-11-09T10:00:00Z", now)).toMatch(/^9 Nov, \d\d:\d\d$/)
  })
})
