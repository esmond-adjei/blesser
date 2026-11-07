import { describe, expect, it } from "vitest"
import { kept, wordDiff } from "./wordDiff"

describe("wordDiff", () => {
  it("marks a changed word in place, keeping the rest and its spacing", () => {
    expect(wordDiff("Built tools for the lab", "Built three tools for the lab")).toEqual([
      { kind: "same", text: "Built " },
      { kind: "ins", text: "three " },
      { kind: "same", text: "tools for the lab" },
    ])
  })

  it("groups a run of changes as one deletion then one insertion", () => {
    const parts = wordDiff("Led a small team", "Managed four engineers")!
    expect(parts.map((p) => p.kind)).toEqual(["del", "ins"])
    expect(parts[0].text + "|" + parts[1].text).toBe("Led a small team|Managed four engineers")
    expect(kept(parts)).toBe(0)
  })

  it("gives up on very long passages", () => {
    expect(wordDiff("word ".repeat(400), "word ".repeat(401))).toBeNull()
  })
})
