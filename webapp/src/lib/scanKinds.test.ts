import { describe, expect, it } from "vitest"
import { kindsPhrase, scanKinds } from "./scanKinds"

describe("scan kinds", () => {
  it("prefers the picked types, else reads them from the focus", () => {
    expect(scanKinds(["grant"], "jobs")).toEqual(["grant"])
    expect(scanKinds([], "job applications in software engineering")).toEqual(["job"])
    expect(scanKinds(undefined, "anything new")).toEqual([])
  })
  it("names them in plain English", () => {
    expect(kindsPhrase(["scholarship"])).toBe("scholarships")
    expect(kindsPhrase(["scholarship", "job", "grant"])).toBe("scholarships, jobs and grants")
  })
})
