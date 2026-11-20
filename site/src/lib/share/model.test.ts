import { describe, expect, it } from "vitest"
import { shareLabel } from "./model"

describe("shareLabel", () => {
  it("reads as a phrase, not a list", () => {
    expect(shareLabel("scholarship", "student")).toBe("Scholarship for students")
    expect(shareLabel("call_for_proposals", "research")).toBe("Call for proposals for researchers")
  })
  it("falls back to whichever part is known", () => {
    expect(shareLabel("grant", "")).toBe("Grant")
    expect(shareLabel("", "startup")).toBe("Startups")
  })
})
