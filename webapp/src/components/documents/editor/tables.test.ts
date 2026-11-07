// @vitest-environment jsdom
import { defineLanguageFacet, forceParsing, Language, LanguageSupport } from "@codemirror/language"
import { EditorSelection, EditorState } from "@codemirror/state"
import { EditorView } from "@codemirror/view"
import { GFM, parser } from "@lezer/markdown"
import { afterEach, beforeAll, describe, expect, it } from "vitest"
import { toPlainText } from "../documentText"
import { editTable, enterInTable, insertTable, moveCell, tableAt, tables } from "./tables"
import { formatTable, parseTable, splitRow } from "./tableSyntax"

beforeAll(() => {
  // jsdom has no layout: CodeMirror measures ranges, which it lacks.
  const rect = { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) }
  Range.prototype.getBoundingClientRect = () => rect as DOMRect
  Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
})

const language = new Language(defineLanguageFacet({}), parser.configure([GFM]), [], "markdown")
let views: EditorView[] = []
afterEach(() => {
  for (const v of views) v.destroy()
  views = []
})

function editor(doc: string, cursor: number | string): EditorView {
  const at = typeof cursor === "number" ? cursor : doc.indexOf(cursor)
  const v = new EditorView({
    parent: document.body,
    state: EditorState.create({ doc, selection: EditorSelection.cursor(at), extensions: [new LanguageSupport(language), tables] }),
  })
  forceParsing(v, doc.length)
  views.push(v)
  return v
}

const text = (v: EditorView) => v.state.doc.toString()
const selected = (v: EditorView) => v.state.sliceDoc(v.state.selection.main.from, v.state.selection.main.to)

const TABLE = "Intro\n\n| Degree | Year |\n| --- | ---: |\n| BSc | 2024 |\n\nAfter\n"

describe("table syntax", () => {
  it("reads cells, alignment and short rows", () => {
    const t = parseTable(["| a | b \\| c |", "| :-: | --: |", "| x |"])
    expect(t).toEqual({ header: ["a", "b \\| c"], align: ["center", "right"], rows: [["x", ""]] })
    expect(splitRow("a | b")).toEqual(["a", "b"])
  })

  it("writes tables with their columns lined up, keeping alignment", () => {
    expect(formatTable({ header: ["Degree", "Y"], align: [null, "right"], rows: [["BSc", "2024"]] })).toEqual([
      "| Degree | Y    |",
      "| ------ | ---: |",
      "| BSc    | 2024 |",
    ])
  })

  it("copies as text with cells apart by tabs", () => {
    expect(toPlainText(TABLE)).toBe("Intro\n\nDegree\tYear\nBSc\t2024\n\nAfter\n")
  })
})

describe("editing tables", () => {
  it("finds the table at the cursor, from its first to its last row", () => {
    const v = editor(TABLE, "BSc")
    expect(tableAt(v.state, v.state.selection.main.head)).toMatchObject({ first: 3, last: 5 })
    expect(tableAt(v.state, 2)).toBeNull()
  })

  it("Tab moves to the next cell, lining the columns up; past the last it adds a row", () => {
    const v = editor(TABLE, "Degree")
    moveCell(1)(v)
    expect(selected(v)).toBe("Year")
    expect(text(v)).toContain("| Degree | Year |\n| ------ | ---: |\n| BSc    | 2024 |")
    moveCell(1)(v)
    expect(selected(v)).toBe("BSc")
    moveCell(1)(v)
    moveCell(1)(v)
    expect(text(v)).toContain("| BSc    | 2024 |\n|        |      |")
    moveCell(-1)(v)
    expect(selected(v)).toBe("2024")
  })

  it("Enter adds a row below; on an empty last row it leaves the table", () => {
    const v = editor(TABLE, "2024")
    enterInTable(v)
    expect(text(v)).toContain("| BSc    | 2024 |\n|        |      |\n\nAfter")
    enterInTable(v)
    expect(text(v)).toContain("| BSc    | 2024 |\n\n")
    expect(tableAt(v.state, v.state.selection.main.head)).toBeNull()
  })

  it("adds and deletes rows and columns", () => {
    const v = editor(TABLE, "BSc")
    editTable(v, "colRight")
    expect(text(v)).toContain("| Degree |     | Year |")
    editTable(v, "deleteCol")
    expect(text(v)).toContain("| Degree | Year |")
    editTable(v, "rowAbove")
    expect(text(v)).toContain("| ------ | ---: |\n|        |      |\n| BSc    | 2024 |")
    editTable(v, "deleteRow")
    expect(text(v)).toContain("| ------ | ---: |\n| BSc    | 2024 |")
    editTable(v, "deleteTable")
    expect(text(v)).toBe("Intro\n\nAfter\n")
  })

  it("inserts a table set apart from the text around it", () => {
    const v = editor("Intro\nMore\n", "Intro")
    insertTable(v, 2, 2)
    expect(text(v)).toBe("Intro\n\n|     |     |\n| --- | --- |\n|     |     |\nMore\n".replace("|\nMore", "|\n\nMore"))
  })

  it("shows a table as a table away from the cursor", () => {
    const v = editor(TABLE, 0)
    expect(v.dom.querySelector(".cm-doc-table th")?.textContent).toBe("Degree")
    expect(v.dom.querySelectorAll(".cm-doc-table td")).toHaveLength(2)
  })
})
