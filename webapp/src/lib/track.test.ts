import { describe, expect, it, vi } from "vitest"
import { authHref, trackAfterAuth, trackParam, trackedMessage, trackedTitle } from "./track"
import { ApiError } from "./api"

describe("trackParam", () => {
  it("reads a slug and ignores blanks, paths and oversized values", () => {
    expect(trackParam(new URLSearchParams("track=seed-grant-2027"))).toBe("seed-grant-2027")
    expect(trackParam(new URLSearchParams("track=%20seed%20"))).toBe("seed")
    expect(trackParam(new URLSearchParams("track="))).toBeNull()
    expect(trackParam(new URLSearchParams(""))).toBeNull()
    expect(trackParam(new URLSearchParams("track=../admin"))).toBeNull()
    expect(trackParam(new URLSearchParams(`track=${"a".repeat(301)}`))).toBeNull()
  })
})

describe("authHref", () => {
  it("carries next and track, and drops what is missing", () => {
    expect(authHref("/login", { next: "/todos", track: "seed" })).toBe("/login?next=%2Ftodos&track=seed")
    expect(authHref("/register", { track: "seed" })).toBe("/register?track=seed")
    expect(authHref("/login", { next: null, track: null })).toBe("/login")
  })
})

describe("trackedMessage", () => {
  it("names the opportunity when it can", () => {
    expect(trackedMessage("Seed Grant")).toBe("Tracked Seed Grant")
    expect(trackedMessage(null)).toBe("Tracked")
  })
})

describe("trackAfterAuth", () => {
  it("resolves the slug to an id, tracks it and returns the title", async () => {
    const getOpportunity = vi.fn().mockResolvedValue({ id: "opp-1", title: "Seed Grant" })
    const trackOpportunity = vi.fn().mockResolvedValue({})
    await expect(trackAfterAuth("seed-grant", { getOpportunity, trackOpportunity })).resolves.toBe("Seed Grant")
    expect(getOpportunity).toHaveBeenCalledWith("seed-grant")
    expect(trackOpportunity).toHaveBeenCalledWith("opp-1")
  })

  it("does not track when the slug doesn't resolve", async () => {
    const getOpportunity = vi.fn().mockRejectedValue(new ApiError(404, "", "Not found"))
    const trackOpportunity = vi.fn()
    await expect(trackAfterAuth("gone", { getOpportunity, trackOpportunity })).rejects.toThrow("Not found")
    expect(trackOpportunity).not.toHaveBeenCalled()
  })
})

describe("trackedTitle", () => {
  it("returns the title, or null when the lookup fails", async () => {
    await expect(trackedTitle("seed", { getOpportunity: async () => ({ id: "1", title: "Seed" }) })).resolves.toBe("Seed")
    await expect(trackedTitle("seed", { getOpportunity: () => Promise.reject(new Error("offline")) })).resolves.toBeNull()
  })
})
