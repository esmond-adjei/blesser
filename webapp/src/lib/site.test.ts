import { describe, expect, it } from "vitest"
import { resolveSiteUrl } from "./site"

describe("resolveSiteUrl", () => {
  it("defaults to the dev site when unset", () => {
    expect(resolveSiteUrl(undefined)).toBe("http://localhost:4321")
  })

  it("means no site (sign-in instead) when empty", () => {
    expect(resolveSiteUrl("")).toBeNull()
    expect(resolveSiteUrl("  ")).toBeNull()
  })

  it("trims trailing slashes", () => {
    expect(resolveSiteUrl("https://blesser.org/")).toBe("https://blesser.org")
  })
})
