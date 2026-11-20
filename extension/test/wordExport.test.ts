// @vitest-environment jsdom
import { inflateRawSync } from "node:zlib"
import { describe, expect, it } from "vitest"
import type { ExportField, FormExport } from "../src/shared/types"
import { buildFormDocx, documentXml, docxName, formatDate } from "../src/sidepanel/wordExport"
import { crc32, zip } from "../src/sidepanel/zip"

/** Reads a ZIP through its central directory, as Word does. */
function unzip(bytes: Uint8Array): Map<string, string> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  let end = bytes.length - 22
  while (view.getUint32(end, true) !== 0x06054b50) end--
  const count = view.getUint16(end + 10, true)
  let at = view.getUint32(end + 16, true)
  const out = new Map<string, string>()
  for (let i = 0; i < count; i++) {
    expect(view.getUint32(at, true)).toBe(0x02014b50)
    const method = view.getUint16(at + 10, true)
    const crc = view.getUint32(at + 16, true)
    const size = view.getUint32(at + 20, true)
    const nameLength = view.getUint16(at + 28, true)
    const local = view.getUint32(at + 42, true)
    const name = new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLength))
    const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true)
    const raw = bytes.subarray(start, start + size)
    const data = method === 8 ? inflateRawSync(raw) : raw
    expect(crc32(data)).toBe(crc)
    out.set(name, new TextDecoder().decode(data))
    at += 46 + nameLength
  }
  return out
}

const field = (over: Partial<ExportField>): ExportField => ({
  key: "0:0", tag: "input", type: "text", name: "", id: "", autocomplete: "", label: "Field", placeholder: "", help_text: "",
  section: "", options: [], required: false, max_length: null, word_limit: null, accept: "", value: null, ...over,
})

const FORM: FormExport = {
  title: "Kumasi Founders Fund: application",
  url: "https://apply.example.org/form?a=1&b=2",
  fields: [
    field({ label: "First name", section: "About you", required: true, value: "Ama" }),
    field({ label: "Pronouns", section: "About you" }),
    field({ label: "What problem are you solving?", tag: "textarea", type: "textarea", section: "Your venture", help_text: "Maximum 120 words.", value: "Heat <spoils> 40% of stock & more\nSecond line" }),
    field({ label: "Stage", tag: "select", type: "select", section: "Your venture", options: [{ value: "Idea", label: "Idea" }, { value: "Prototype", label: "Prototype" }], value: "Prototype" }),
    field({ label: "Country", tag: "select", type: "select", section: "Your venture", options: Array.from({ length: 20 }, (_, i) => ({ value: `c${i}`, label: `Country ${i}` })) }),
    field({ label: "Founder CV", type: "file", section: "Documents", accept: ".pdf,.docx", required: true }),
    field({ label: "I confirm the information is accurate", type: "checkbox", options: [{ value: "on", label: "I confirm the information is accurate" }], section: "Documents" }),
  ],
}

const parse = (xml: string) => new DOMParser().parseFromString(xml, "application/xml")
const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

describe("zip", () => {
  it("computes the standard CRC-32", () => {
    expect(crc32(new TextEncoder().encode("123456789"))).toBe(0xcbf43926)
  })

  it("writes entries a reader can list and check", () => {
    const files = unzip(zip([{ name: "a.txt", data: "hello" }, { name: "dir/ü.xml", data: "<x/>" }]))
    expect([...files]).toEqual([["a.txt", "hello"], ["dir/ü.xml", "<x/>"]])
  })
})

describe("buildFormDocx", () => {
  const date = new Date(2026, 10, 21, 9, 30)

  it("packages a well-formed Word document", () => {
    const files = unzip(buildFormDocx(FORM, date))
    expect([...files.keys()].sort()).toEqual(["[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "word/_rels/document.xml.rels", "word/document.xml", "word/styles.xml"])
    for (const [name, xml] of files) expect(parse(xml).getElementsByTagName("parsererror"), name).toHaveLength(0)
    expect(files.get("docProps/core.xml")).toContain("<dc:title>Kumasi Founders Fund: application</dc:title>")
  })

  it("lays out sections, answers, choices and boxes to write in", () => {
    const doc = parse(documentXml(FORM, date))
    const paragraphs = Array.from(doc.getElementsByTagNameNS(W, "p"))
    const text = (p: Element) => Array.from(p.getElementsByTagNameNS(W, "t")).map((t) => t.textContent).join("")
    const styled = (style: string) => paragraphs.filter((p) => p.getElementsByTagNameNS(W, "pStyle")[0]?.getAttribute("w:val") === style).map(text)

    expect(styled("Title")).toEqual(["Kumasi Founders Fund: application"])
    expect(styled("Heading1")).toEqual(["About you", "Your venture", "Documents"])
    const all = paragraphs.map(text)
    expect(all).toContain("Saved 21 Nov 2026 from https://apply.example.org/form?a=1&b=2")
    expect(all).toContain("3 of 7 fields have an answer. Write yours in the boxes, then copy them into the online form.")
    expect(all).toContain("First name (required)")
    expect(all).toContain("Ama")
    expect(all).toContain("Heat <spoils> 40% of stock & moreSecond line")
    expect(all).toContain("☐  Idea")
    expect(all).toContain("☒  Prototype")
    expect(all).toContain("Tick one.")
    expect(all.some((t) => t.startsWith("Choose one of: Country 0, Country 1"))).toBe(true)
    expect(all).toContain("Attach a file (.pdf, .docx).")
    expect(all).toContain("☐  I confirm the information is accurate")
    expect(all).not.toContain("I confirm the information is accurate")
    expect(doc.getElementsByTagNameNS(W, "tbl")).toHaveLength(5)
    const heights = Array.from(doc.getElementsByTagNameNS(W, "trHeight")).map((h) => h.getAttribute("w:val"))
    expect(heights).toEqual(["480", "480", "2400", "480", "480"])
  })

  it("drops characters XML can't hold", () => {
    const xml = documentXml({ ...FORM, title: "Bad\u0001title", fields: [field({ label: "A\u000bB" })] }, date)
    expect(parse(xml).getElementsByTagName("parsererror")).toHaveLength(0)
    expect(xml).toContain("Badtitle")
  })
})

describe("names and dates", () => {
  it("formats dates day month year", () => {
    expect(formatDate(new Date(2026, 0, 5))).toBe("5 Jan 2026")
  })

  it("makes a safe file name", () => {
    expect(docxName("Kumasi Founders Fund: application")).toBe("kumasi-founders-fund-application.docx")
    expect(docxName("Bourse d'études Côte d'Ivoire")).toBe("bourse-d-etudes-cote-d-ivoire.docx")
    expect(docxName("")).toBe("application-form.docx")
    expect(docxName("::")).toBe("application-form.docx")
  })
})
