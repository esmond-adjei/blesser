import { describe, expect, it } from "vitest"
import { countryName, sameDay } from "./format"

describe("countryName", () => {
  it("names two-letter region codes", () => {
    expect(countryName("GH")).toBe("Ghana")
    expect(countryName("gb")).toBe("United Kingdom")
  })
  it("keeps anything else as given", () => {
    expect(countryName("West Africa")).toBe("West Africa")
    expect(countryName(" Anywhere ")).toBe("Anywhere")
  })
})

describe("sameDay", () => {
  it("matches the ISO date and common written forms of it", () => {
    expect(sameDay("2026-12-02", "2026-12-02")).toBe(true)
    expect(sameDay("02 Dec 2026", "2026-12-02")).toBe(true)
    expect(sameDay("December 2, 2026", "2026-12-02")).toBe(true)
  })
  it("keeps wording that adds something or names another day", () => {
    expect(sameDay("2 Dec 2026, 5pm GMT", "2026-12-02")).toBe(false)
    expect(sameDay("03 Dec 2026", "2026-12-02")).toBe(false)
    expect(sameDay("End of the year", "2026-12-02")).toBe(false)
  })
})
