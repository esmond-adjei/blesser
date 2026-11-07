import { redo, undo } from "@codemirror/commands"
import { syntaxTree } from "@codemirror/language"
import { openSearchPanel } from "@codemirror/search"
import { EditorSelection, type EditorState, type Line } from "@codemirror/state"
import type { EditorView } from "@codemirror/view"
import type { SyntaxNode } from "@lezer/common"
import { editTable, insertTable, type TableAction } from "./tables"

/**
 * Toolbar actions as Markdown edits. Paragraph styles follow the import's mapping
 * (api/cv/markdown.py): Title is "#", Heading n is n + 1 "#"s. Underline has no
 * Markdown mark, so it is written <u>…</u>, which every export renders.
 */

export type BlockStyle = "normal" | "title" | "h1" | "h2" | "h3"

export type EditorCommand =
  | { type: "undo" }
  | { type: "redo" }
  | { type: "block"; style: BlockStyle }
  | { type: "bold" }
  | { type: "italic" }
  | { type: "underline" }
  | { type: "link"; url: string }
  | { type: "list"; ordered: boolean }
  | { type: "find" }
  | { type: "table"; rows: number; cols: number }
  | { type: "tableEdit"; action: TableAction }
  | { type: "rule" }

const LEVEL: Record<BlockStyle, number> = { normal: 0, title: 1, h1: 2, h2: 3, h3: 4 }
const HEADING = /^(#{1,6})\s+/
const BULLET = /^(\s*)[-*+]\s+/
const NUMBERED = /^(\s*)\d+[.)]\s+/
const UNDERLINE = /<u>(.*?)<\/u>/g

function selectedLines(state: EditorState): Line[] {
  const seen = new Set<number>()
  const lines: Line[] = []
  for (const r of state.selection.ranges) {
    const last = state.doc.lineAt(r.to).number
    for (let n = state.doc.lineAt(r.from).number; n <= last; n++) {
      if (!seen.has(n)) {
        seen.add(n)
        lines.push(state.doc.line(n))
      }
    }
  }
  return lines
}

export function blockStyleAt(state: EditorState): BlockStyle | "other" {
  const m = HEADING.exec(state.doc.lineAt(state.selection.main.head).text)
  if (!m) return "normal"
  const found = (Object.keys(LEVEL) as BlockStyle[]).find((k) => LEVEL[k] === m[1].length)
  return found ?? "other"
}

export type Marks = { bold: boolean; italic: boolean; underline: boolean; link: boolean }

export function marksAt(state: EditorState): Marks {
  const head = state.selection.main.head
  const marks: Marks = { bold: false, italic: false, underline: false, link: false }
  let node: SyntaxNode | null = syntaxTree(state).resolveInner(head, -1)
  while (node) {
    if (node.name === "StrongEmphasis") marks.bold = true
    else if (node.name === "Emphasis") marks.italic = true
    else if (node.name === "Link") marks.link = true
    node = node.parent
  }
  const line = state.doc.lineAt(head)
  const at = head - line.from
  for (const m of line.text.matchAll(UNDERLINE)) {
    const start = m.index ?? 0
    if (at >= start + 3 && at <= start + m[0].length - 4) marks.underline = true
  }
  return marks
}

function setBlock(view: EditorView, style: BlockStyle) {
  const level = LEVEL[style]
  const changes = selectedLines(view.state)
    .filter((line) => line.text.trim() !== "" || level === 0)
    .map((line) => {
      // A heading is never a list item: drop either mark first.
      const strip = HEADING.exec(line.text) ?? BULLET.exec(line.text) ?? NUMBERED.exec(line.text)
      const removeTo = line.from + (strip ? strip[0].length : 0)
      return { from: line.from, to: removeTo, insert: level ? `${"#".repeat(level)} ` : "" }
    })
  view.dispatch({ changes, scrollIntoView: true, userEvent: "input.format" })
}

/** Wrap (or unwrap) each selection in `open`…`close`; with nothing
 * selected, the word at the cursor, else an empty pair with the cursor
 * inside. */
function toggleWrap(view: EditorView, open: string, close: string = open) {
  const { state } = view
  const a = open.length
  const b = close.length
  const tx = state.changeByRange((range) => {
    let { from, to } = range
    if (from === to) {
      const word = state.wordAt(from)
      if (word) ({ from, to } = word)
    }
    const before = state.sliceDoc(from - a, from)
    const after = state.sliceDoc(to, to + b)
    // "**" also reads as two "*": italic around bold text is "*", not a
    // half of "**".
    const wrapped =
      before === open && after === close &&
      !(open === "*" && state.sliceDoc(from - 2, from) === "**" && state.sliceDoc(to, to + 2) === "**" && state.sliceDoc(from - 3, from) !== "***")
    if (wrapped) {
      return {
        changes: [{ from: from - a, to: from }, { from: to, to: to + b }],
        range: EditorSelection.range(from - a, to - a),
      }
    }
    const inner = state.sliceDoc(from, to)
    if (inner.length >= a + b && inner.startsWith(open) && inner.endsWith(close)) {
      return {
        changes: { from, to, insert: inner.slice(a, inner.length - b) },
        range: EditorSelection.range(from, to - a - b),
      }
    }
    return {
      changes: [{ from, insert: open }, { from: to, insert: close }],
      range: from === to ? EditorSelection.cursor(from + a) : EditorSelection.range(from + a, to + a),
    }
  })
  view.dispatch(state.update(tx, { scrollIntoView: true, userEvent: "input.format" }))
}

function insertLink(view: EditorView, url: string) {
  const { state } = view
  const tx = state.changeByRange((range) => {
    let { from, to } = range
    if (from === to) {
      const word = state.wordAt(from)
      if (word) ({ from, to } = word)
    }
    const label = state.sliceDoc(from, to) || url
    const insert = `[${label}](${url})`
    return { changes: { from, to, insert }, range: EditorSelection.cursor(from + insert.length) }
  })
  view.dispatch(state.update(tx, { scrollIntoView: true, userEvent: "input.format" }))
}

/** Make the selected lines a bulleted or numbered list, or plain lines
 * again when they all already are. */
function toggleList(view: EditorView, ordered: boolean) {
  const lines = selectedLines(view.state).filter((l) => l.text.trim() !== "")
  if (!lines.length) {
    const at = view.state.selection.main.head
    const line = view.state.doc.lineAt(at)
    const insert = ordered ? "1. " : "- "
    view.dispatch({
      changes: { from: line.from, insert },
      selection: { anchor: at + insert.length },
      userEvent: "input.format",
    })
    return
  }
  const own = ordered ? NUMBERED : BULLET
  const all = lines.every((l) => own.test(l.text))
  let n = 0
  const changes = lines.map((line) => {
    const mark = NUMBERED.exec(line.text) ?? BULLET.exec(line.text) ?? HEADING.exec(line.text)
    const indent = mark && !mark[0].startsWith("#") ? (mark[1] ?? "") : ""
    const to = line.from + (mark ? mark[0].length : 0)
    if (all) return { from: line.from, to, insert: indent }
    n += 1
    return { from: line.from, to, insert: `${indent}${ordered ? `${n}. ` : "- "}` }
  })
  view.dispatch({ changes, scrollIntoView: true, userEvent: "input.format" })
}

/** A horizontal line after the cursor's line, set apart by blank lines
 * (right under text, "---" would make that text a heading). */
function insertRule(view: EditorView) {
  const { state } = view
  const line = state.doc.lineAt(state.selection.main.head)
  const empty = !line.text.trim()
  const prev = line.number > 1 ? state.doc.line(line.number - 1) : null
  const next = line.number < state.doc.lines ? state.doc.line(line.number + 1) : null
  const before = empty ? (prev && prev.text.trim() ? "\n" : "") : "\n\n"
  const after = next && next.text.trim() ? "\n\n" : "\n"
  const from = empty ? line.from : line.to
  const insert = `${before}---${after}`
  view.dispatch({
    changes: { from, to: line.to, insert },
    selection: { anchor: from + insert.length },
    scrollIntoView: true,
    userEvent: "input.format",
  })
}

export function runCommand(view: EditorView, cmd: EditorCommand) {
  switch (cmd.type) {
    case "undo":
      undo(view)
      break
    case "redo":
      redo(view)
      break
    case "block":
      setBlock(view, cmd.style)
      break
    case "bold":
      toggleWrap(view, "**")
      break
    case "italic":
      toggleWrap(view, "*")
      break
    case "underline":
      toggleWrap(view, "<u>", "</u>")
      break
    case "link":
      insertLink(view, cmd.url)
      break
    case "list":
      toggleList(view, cmd.ordered)
      break
    case "find":
      openSearchPanel(view)
      return
    case "table":
      insertTable(view, cmd.rows, cmd.cols)
      break
    case "tableEdit":
      editTable(view, cmd.action)
      break
    case "rule":
      insertRule(view)
      break
  }
  view.focus()
}
