import { describe, expect, it } from "vitest"
import { describeFilters, filtersToParams, sameFilters, suggestName } from "./matching"

describe("saved search filters", () => {
  it("map to the Opportunities page params", () => {
    expect(filtersToParams({ q: "climate", kind: "grant", category: null, closing_within: 14 }).toString()).toBe(
      "q=climate&kind=grant&soon=1",
    )
    expect(filtersToParams({}).toString()).toBe("")
  })

  it("compare by the params they produce", () => {
    expect(sameFilters({ q: "ai", kind: null }, { q: "ai" })).toBe(true)
    expect(sameFilters({ q: "ai" }, { q: "ai", category: "student" })).toBe(false)
  })

  it("describe themselves in plain words", () => {
    expect(describeFilters({ q: "climate", kind: "call_for_proposals", category: "research" })).toBe(
      '"climate", Call for proposals, Researchers',
    )
    expect(describeFilters({})).toBe("Everything open")
    expect(suggestName({ q: "climate", kind: "grant" })).toBe("climate, Grant")
    expect(suggestName({ q: "x".repeat(80) }).length).toBe(60)
  })
})
