import { JSDOM } from "jsdom"
import { describe, expect, it } from "vitest"
import { cleanTitle, findDate, pageDetails } from "../src/content/details"

const page = (html: string, title = "") =>
  new JSDOM(`<!doctype html><html><head><title>${title}</title></head><body>${html}</body></html>`, { url: "https://apply.example.org/" }).window.document

describe("findDate", () => {
  it("reads the common ways a date is written", () => {
    expect(findDate("by 30 November 2026.")).toEqual({ text: "30 November 2026", date: "2026-11-30" })
    expect(findDate("on 1st of Dec, 2026")).toEqual({ text: "1st of Dec, 2026", date: "2026-12-01" })
    expect(findDate("November 30, 2026 at noon")).toMatchObject({ date: "2026-11-30" })
    expect(findDate("2026-11-30")).toMatchObject({ date: "2026-11-30" })
    expect(findDate("30/11/2026")).toMatchObject({ date: "2026-11-30" })
  })

  it("refuses dates it can't be sure of", () => {
    expect(findDate("03/04/2026")).toBeNull()
    expect(findDate("31 February 2026")).toBeNull()
    expect(findDate("some time in 2026")).toBeNull()
  })
})

describe("pageDetails", () => {
  it("finds the title, funder and the deadline next to its label", () => {
    const doc = page(
      `<h1>Accra Climate Prize 2026</h1><p>Opens 1 October 2026.</p><dl><dt>Deadline</dt><dd>Nov 30, 2026</dd></dl>`,
      "Apply | Green Ghana",
    )
    doc.head.insertAdjacentHTML("beforeend", '<meta property="og:site_name" content="Green Ghana Fund">')
    expect(pageDetails(doc)).toEqual({
      title: "Accra Climate Prize 2026",
      organization: "Green Ghana Fund",
      deadline: { text: "Nov 30, 2026", date: "2026-11-30", rolling: false },
    })
  })

  it("takes the date after the deadline words, not an earlier one", () => {
    const doc = page("<p>Programme runs 5 January 2027 to 30 June 2027. Applications close on 15th December 2026 at midnight.</p>")
    expect(pageDetails(doc).deadline).toEqual({ text: "15th December 2026", date: "2026-12-15", rolling: false })
  })

  it("notices rolling applications and leaves the deadline empty when nothing is stated", () => {
    expect(pageDetails(page("<h1>Seed fund</h1><p>We review applications on a rolling basis.</p>")).deadline).toEqual({ text: "Rolling", date: null, rolling: true })
    expect(pageDetails(page("<h1>Seed fund</h1><p>Tell us about your team.</p>")).deadline).toBeNull()
  })

  it("skips generic headings and ignores text inside form controls", () => {
    const doc = page('<h1>Application form</h1><textarea>Deadline: 1 January 2027</textarea>', "Kumasi Founders Fund: application")
    expect(pageDetails(doc)).toEqual({ title: "Kumasi Founders Fund", organization: "", deadline: null })
  })
})

describe("cleanTitle", () => {
  it("drops form builder and site suffixes", () => {
    expect(cleanTitle("Siwa Green Grant - Google Forms")).toBe("Siwa Green Grant")
    expect(cleanTitle("Fellowship 2026 | Accra Tech Hub")).toBe("Fellowship 2026")
    expect(cleanTitle("Apply now: Founders Fund")).toBe("Apply now: Founders Fund")
    expect(cleanTitle("Founders Fund - Online application form")).toBe("Founders Fund")
  })
})
