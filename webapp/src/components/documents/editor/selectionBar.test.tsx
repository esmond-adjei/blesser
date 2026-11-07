// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { EditorState, StateEffect } from "@codemirror/state"
import { EditorView } from "@codemirror/view"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { minimalChange } from "../documentText"
import { MarkdownEditor, type MarkdownEditorHandle, type SelectionBarInfo } from "./MarkdownEditor"
import { paragraphAt } from "./selectionBar"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

beforeAll(() => {
  // jsdom has no layout: CodeMirror measures ranges, which it lacks.
  const rect = { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) }
  Range.prototype.getBoundingClientRect = () => rect as DOMRect
  Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
})

const CV = "# Jane Doe\n\n## Skills\n\n- Built tools in Python.\n- Taught Python to 30 students.\n"

let host: HTMLDivElement
let root: Root
let handle: MarkdownEditorHandle | null
let bars: (SelectionBarInfo | null)[]

function Harness({ value }: { value: string }) {
  return (
    <MarkdownEditor
      ref={(h) => {
        handle = h
      }}
      value={value}
      onChange={() => {}}
      onSelectionBar={(b) => bars.push(b)}
    />
  )
}

function view(): EditorView {
  const dom = host.querySelector(".cm-content") as HTMLElement
  const v = EditorView.findFromDOM(dom)
  if (!v) throw new Error("no editor")
  return v
}

const lastBar = () => bars[bars.length - 1] ?? null

beforeEach(() => {
  bars = []
  handle = null
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => root.render(<Harness value={CV} />))
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

describe("selection bar", () => {
  it("opens over a selection and closes when it empties", () => {
    const from = CV.indexOf("Built")
    act(() => view().dispatch({ selection: { anchor: from, head: from + 11 }, userEvent: "select" }))
    const bar = lastBar()
    expect(bar?.text).toBe("Built tools")
    expect(bar?.from).toBe(from)
    expect(bar?.focus).toBe(false)
    expect(bar?.dom.isConnected).toBe(true)

    act(() => view().dispatch({ selection: { anchor: from }, userEvent: "select" }))
    expect(lastBar()).toBeNull()
  })

  it("waits for the pointer to come up before opening", () => {
    const from = CV.indexOf("Taught")
    act(() => view().dispatch({ selection: { anchor: from, head: from + 6 }, userEvent: "select.pointer" }))
    expect(lastBar()).toBeNull()
  })

  it("opens with Mod-J on the list item under the cursor, then Escape closes it", () => {
    const at = CV.indexOf("Taught") + 3
    act(() => view().dispatch({ selection: { anchor: at } }))
    act(() => {
      view().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "j", ctrlKey: true, bubbles: true, cancelable: true }))
    })
    const bar = lastBar()
    // The item's text, without its "- " mark.
    expect(bar?.text).toBe("Taught Python to 30 students.")
    expect(bar?.focus).toBe(true)

    act(() => {
      view().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }))
    })
    expect(lastBar()).toBeNull()
  })

  it("picks a paragraph, a heading's text, or nothing on a blank line", () => {
    const state = EditorState.create({ doc: "## Summary\n\nFirst line\nsecond line\n\n- item" })
    const doc = state.doc.toString()
    expect(paragraphAt(state, 3)).toEqual({ from: 3, to: 10 })
    expect(paragraphAt(state, doc.indexOf("second"))).toEqual({ from: doc.indexOf("First"), to: doc.indexOf("line\n\n-") + 4 })
    expect(paragraphAt(state, 11)).toBeNull()
  })
})

describe("applying a suggestion", () => {
  it("edits exactly its range: the cursor and other marks stay put", () => {
    const first = CV.indexOf("Built")
    const second = CV.indexOf("Taught")
    // Cursor in the first bullet; a request on its way for its text.
    act(() => view().dispatch({ selection: { anchor: first + 2 } }))
    act(() => handle?.markLoading("r1", first, first + 5))
    // Watch the edit the new value makes.
    const changes = vi.fn()
    const v = view()
    const listener = EditorView.updateListener.of((u) => {
      if (u.docChanged) u.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => changes(fromA, toA, inserted.toString()))
    })
    act(() => v.dispatch({ effects: StateEffect.appendConfig.of(listener) }))

    const accepted = CV.replace("Taught Python", "Mentored Python")
    act(() => root.render(<Harness value={accepted} />))

    expect(v.state.doc.toString()).toBe(accepted)
    expect(changes).toHaveBeenCalledTimes(1)
    expect(changes).toHaveBeenCalledWith(second, second + "Taught".length, "Mentored")
    expect(v.state.selection.main.head).toBe(first + 2)
    expect(handle?.loadingRange("r1")).toEqual({ from: first, to: first + 5 })
  })

  it("finds the one change between two texts", () => {
    expect(minimalChange("abc", "abc")).toBeNull()
    expect(minimalChange("a Python b Python c", "a Python b Rust c")).toEqual({ from: 11, to: 17, insert: "Rust" })
    expect(minimalChange("aaa", "aaaa")).toEqual({ from: 3, to: 3, insert: "a" })
    expect(minimalChange("abc", "")).toEqual({ from: 0, to: 3, insert: "" })
  })
})
