import { describe, expect, it } from "vitest"
import { parseSources } from "./parseSources"

describe("parseSources", () => {
  it("reads links and bare domains one per line with the words beside them as the note", () => {
    const rows = parseSources(
      ["- UG scholarships: ug.edu.gh/scholarships", "https://mastercardfdn.org/scholars/ - Mastercard scholars", "[Founders Factory](https://foundersfactory.africa/apply)"].join("\n"),
      "startup",
    )
    expect(rows.map((r) => r.url)).toEqual(["ug.edu.gh/scholarships", "https://mastercardfdn.org/scholars/", "https://foundersfactory.africa/apply"])
    expect(rows[0].note).toBe("UG scholarships")
    expect(rows[1].note).toBe("Mastercard scholars")
    expect(rows[2].note).toBe("Founders Factory")
  })

  it("guesses the audience from the words, else uses the fallback", () => {
    const rows = parseSources("Bursary for students https://a.example/x\nResearch grants https://b.example/y\nAccelerator call https://c.example/z\nhttps://d.example", "research")
    expect(rows.map((r) => r.category)).toEqual(["student", "research", "startup", "research"])
  })

  it("uses a line above a bare link as its note", () => {
    const rows = parseSources("GIZ innovation challenges\nhttps://giz.example/calls", "startup")
    expect(rows[0].note).toBe("GIZ innovation challenges")
  })

  it("drops duplicates, emails, files and trailing punctuation", () => {
    const rows = parseSources("see https://x.example/a, and www.x.example/a/ also mail me@x.example or notes.txt https://y.example.", "startup")
    expect(rows.map((r) => r.url)).toEqual(["https://x.example/a", "https://y.example"])
  })

  it("returns nothing when there is no site", () => {
    expect(parseSources("just some words\nand more", "student")).toEqual([])
  })
})
