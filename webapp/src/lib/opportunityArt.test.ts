import { describe, expect, it } from "vitest"
import { opportunityArt } from "@blesser/ui"

describe("opportunityArt", () => {
  it("draws the same picture for the same seed", () => {
    const a = opportunityArt("gates-cambridge-2027", { category: "student", kind: "scholarship" })
    const b = opportunityArt("gates-cambridge-2027", { category: "student", kind: "scholarship" })
    expect(a).toEqual(b)
    expect(opportunityArt("x", { shape: "square" })).toEqual(opportunityArt("x", { shape: "square" }))
  })

  it("varies with the seed and keeps to brand tokens", () => {
    const a = opportunityArt("seed-a", { category: "startup", kind: "grant" })
    const b = opportunityArt("seed-b", { category: "startup", kind: "grant" })
    expect(a).not.toEqual(b)
    const fills = [a.ground, ...[...a.motif, ...a.path].map((e) => ("fill" in e ? e.fill : e.stroke))]
    for (const fill of fills) expect(fill).toMatch(/^var\(--[a-z-]+\)$/)
  })

  it("keeps the path inside the frame", () => {
    for (const shape of ["banner", "square"] as const)
      for (let i = 0; i < 50; i++) {
        const art = opportunityArt(`seed-${i}`, { category: "research", kind: "fellowship", shape })
        for (const e of art.path) {
          const [x0, y0, x1, y1] = e.t === "rect" ? [e.x, e.y, e.x + e.w, e.y + e.h] : [e.cx - e.r, e.cy - e.r, e.cx + e.r, e.cy + e.r]
          expect(x0).toBeGreaterThanOrEqual(0)
          expect(y0).toBeGreaterThanOrEqual(0)
          expect(x1).toBeLessThanOrEqual(art.width)
          expect(y1).toBeLessThanOrEqual(art.height)
        }
      }
  })
})
