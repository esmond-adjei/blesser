import { syntaxTree } from "@codemirror/language"
import { EditorSelection, type EditorState, StateEffect, StateField, type Range, type Text } from "@codemirror/state"
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate, WidgetType } from "@codemirror/view"
import type { SyntaxNode } from "@lezer/common"
import { formatTable, parseTable, splitRow, type TableModel } from "./tableSyntax"

/**
 * GFM pipe tables in the editor: away from the cursor a table shows as a table; with the
 * cursor in it, it is edited as text and every move lines the columns up again.
 */

/** Where a table is: its first and last line numbers (1-based). */
export type TableAt = { from: number; to: number; first: number; last: number }

export function tableAt(state: EditorState, pos: number): TableAt | null {
  const find = (side: -1 | 1) => {
    let node: SyntaxNode | null = syntaxTree(state).resolveInner(pos, side)
    while (node && node.name !== "Table") node = node.parent
    return node
  }
  // Either side: at a row's very start or end the other side is outside.
  const node = find(-1) ?? find(1)
  if (!node) return null
  const first = state.doc.lineAt(node.from)
  const last = state.doc.lineAt(Math.max(node.from, node.to - (state.doc.sliceString(node.to - 1, node.to) === "\n" ? 1 : 0)))
  return { from: first.from, to: last.to, first: first.number, last: last.number }
}

function linesOf(doc: Text, at: TableAt): string[] {
  const out: string[] = []
  for (let n = at.first; n <= at.last; n++) out.push(doc.line(n).text)
  return out
}

/** Which cell a position is in: its row (0 the header, then body rows;
 * the delimiter row counts as the header) and column. */
function cellAt(state: EditorState, at: TableAt, pos: number): { row: number; col: number } {
  const line = state.doc.lineAt(pos)
  const index = line.number - at.first
  const before = line.text.slice(0, pos - line.from).replace(/\\\|/g, "")
  const pipes = (before.match(/\|/g) ?? []).length
  const leading = /^\s*\|/.test(line.text) ? 1 : 0
  const width = splitRow(state.doc.line(at.first).text).length
  return { row: index <= 1 ? 0 : index - 1, col: Math.max(0, Math.min(width - 1, pipes - leading)) }
}

/** Where a cell's text starts and ends in formatted lines. */
function cellRange(lines: string[], row: number, col: number): { line: number; from: number; to: number } {
  const lineIndex = row === 0 ? 0 : row + 1
  const text = lines[lineIndex]
  // Outer pipes are optional: without one, the first cell starts the line.
  let at = /^\s*\|/.test(text) ? text.indexOf("|") + 1 : 0
  for (let c = 0; c < col; c++) {
    let next = at
    while (next < text.length && !(text[next] === "|" && text[next - 1] !== "\\")) next++
    at = next + 1
  }
  let end = at
  while (end < text.length && !(text[end] === "|" && text[end - 1] !== "\\")) end++
  const cell = text.slice(at, end)
  const start = at + (cell.length - cell.trimStart().length)
  const stop = Math.max(start, at + cell.trimEnd().length)
  return { line: lineIndex, from: start, to: stop }
}

/** Replace the table with `model`, formatted, selecting a cell. */
function write(view: EditorView, at: TableAt, model: TableModel, row: number, col: number, select = true): void {
  const lines = formatTable(model)
  const r = Math.max(0, Math.min(row, model.rows.length))
  const c = Math.max(0, Math.min(col, model.header.length - 1))
  const cell = cellRange(lines, r, c)
  let offset = 0
  for (let i = 0; i < cell.line; i++) offset += lines[i].length + 1
  const anchor = at.from + offset + cell.from
  const head = at.from + offset + cell.to
  view.dispatch({
    changes: { from: at.from, to: at.to, insert: lines.join("\n") },
    selection: select ? EditorSelection.range(anchor, head) : EditorSelection.cursor(head),
    scrollIntoView: true,
    userEvent: "input.table",
  })
}

function current(view: EditorView): { at: TableAt; model: TableModel; row: number; col: number } | null {
  const { state } = view
  const head = state.selection.main.head
  const at = tableAt(state, head)
  if (!at) return null
  const { row, col } = cellAt(state, at, head)
  return { at, model: parseTable(linesOf(state.doc, at)), row, col }
}

const blankRow = (width: number) => Array.from({ length: width }, () => "")

/** Tab / Shift-Tab: the next or previous cell, a new row after the last. */
export function moveCell(dir: 1 | -1) {
  return (view: EditorView): boolean => {
    const t = current(view)
    if (!t) return false
    const width = t.model.header.length
    let index = t.row * width + t.col + dir
    if (index < 0) index = 0
    if (index >= (t.model.rows.length + 1) * width) t.model.rows.push(blankRow(width))
    write(view, t.at, t.model, Math.floor(index / width), index % width)
    return true
  }
}

/** Enter in a table: a new row below; on an empty last row, leave the
 * table (the row goes). */
export function enterInTable(view: EditorView): boolean {
  const t = current(view)
  if (!t || !view.state.selection.main.empty) return false
  const { model, row } = t
  const width = model.header.length
  const body = row - 1
  if (body === model.rows.length - 1 && body >= 0 && model.rows[body].every((c) => !c)) {
    model.rows.pop()
    const lines = formatTable(model)
    const end = t.at.from + lines.join("\n").length
    view.dispatch({
      changes: { from: t.at.from, to: t.at.to, insert: `${lines.join("\n")}\n\n` },
      selection: EditorSelection.cursor(end + 2),
      scrollIntoView: true,
      userEvent: "input.table",
    })
    return true
  }
  model.rows.splice(row, 0, blankRow(width))
  write(view, t.at, model, row + 1, 0, false)
  return true
}

export type TableAction = "rowAbove" | "rowBelow" | "colLeft" | "colRight" | "deleteRow" | "deleteCol" | "deleteTable"

export function editTable(view: EditorView, action: TableAction): boolean {
  const t = current(view)
  if (!t) return false
  const { at, model } = t
  let { row, col } = t
  const width = model.header.length
  switch (action) {
    case "rowAbove":
      // Above the header: the header moves down into the body.
      if (row === 0) {
        model.rows.unshift(model.header)
        model.header = blankRow(width)
      } else model.rows.splice(row - 1, 0, blankRow(width))
      break
    case "rowBelow":
      model.rows.splice(row, 0, blankRow(width))
      row += 1
      break
    case "colLeft":
    case "colRight": {
      const i = action === "colLeft" ? col : col + 1
      model.header.splice(i, 0, "")
      model.align.splice(i, 0, null)
      for (const r of model.rows) r.splice(i, 0, "")
      col = i
      break
    }
    case "deleteRow":
      if (row === 0) {
        if (!model.rows.length) return editTable(view, "deleteTable")
        model.header = model.rows.shift() ?? blankRow(width)
      } else {
        model.rows.splice(row - 1, 1)
        row = Math.min(row, model.rows.length)
      }
      break
    case "deleteCol":
      if (width === 1) return editTable(view, "deleteTable")
      model.header.splice(col, 1)
      model.align.splice(col, 1)
      for (const r of model.rows) r.splice(col, 1)
      col = Math.min(col, width - 2)
      break
    case "deleteTable": {
      const doc = view.state.doc
      // The blank line after it goes too, so no gap is left.
      const blankAfter = at.last < doc.lines && !doc.line(at.last + 1).text.trim()
      const to = blankAfter ? Math.min(doc.length, doc.line(at.last + 1).to + 1) : at.to
      view.dispatch({ changes: { from: at.from, to }, selection: { anchor: at.from }, userEvent: "delete.table" })
      return true
    }
  }
  write(view, at, model, row, col)
  return true
}

/** A rows × cols table (header included) after the cursor's line. */
export function insertTable(view: EditorView, rows: number, cols: number): void {
  const { state } = view
  const line = state.doc.lineAt(state.selection.main.head)
  const model: TableModel = {
    header: blankRow(cols),
    align: Array.from({ length: cols }, () => null),
    rows: Array.from({ length: Math.max(1, rows - 1) }, () => blankRow(cols)),
  }
  const lines = formatTable(model)
  const empty = !line.text.trim()
  const before = empty ? (line.number > 1 && state.doc.line(line.number - 1).text.trim() ? "\n" : "") : "\n\n"
  const nextLine = line.number < state.doc.lines ? state.doc.line(line.number + 1) : null
  const after = nextLine && nextLine.text.trim() ? "\n" : ""
  const from = empty ? line.from : line.to
  const to = empty ? line.to : line.to
  const insert = `${before}${lines.join("\n")}${after}`
  const cell = cellRange(lines, 0, 0)
  const anchor = from + before.length + cell.from
  view.dispatch({
    changes: { from, to, insert },
    selection: EditorSelection.cursor(anchor),
    scrollIntoView: true,
    userEvent: "input.table",
  })
}


/** Inline Markdown of one cell as safe HTML: bold, italic, code, links,
 * underline. */
function cellHtml(text: string): string {
  const esc = text.replace(/\\\|/g, "|").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  return esc
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, "<strong>$1</strong>")
    .replace(/__(?=\S)(.+?)(?<=\S)__/g, "<strong>$1</strong>")
    .replace(/\*(?=\S)(.+?)(?<=\S)\*/g, "<em>$1</em>")
    .replace(/\b_(?=\S)(.+?)(?<=\S)_\b/g, "<em>$1</em>")
    .replace(/&lt;u&gt;(.+?)&lt;\/u&gt;/g, "<u>$1</u>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<span class="cm-doc-link">$1</span>')
}

class TableWidget extends WidgetType {
  readonly source: string
  readonly from: number
  constructor(source: string, from: number) {
    super()
    this.source = source
    this.from = from
  }

  eq(other: TableWidget) {
    return other.source === this.source && other.from === this.from
  }

  toDOM(view: EditorView) {
    const lines = this.source.split("\n")
    const model = parseTable(lines)
    const wrap = document.createElement("div")
    wrap.className = "cm-doc-table"
    const table = document.createElement("table")
    const addRow = (parent: HTMLElement, cells: string[], row: number, tag: "th" | "td") => {
      const tr = document.createElement("tr")
      cells.forEach((text, col) => {
        const cell = document.createElement(tag)
        cell.innerHTML = cellHtml(text) || "&#8203;"
        const align = model.align[col]
        if (align) cell.style.textAlign = align
        cell.addEventListener("mousedown", (e) => {
          e.preventDefault()
          // The cell's text in the source, as it stands now.
          const range = cellRange(lines, row, col)
          let offset = 0
          for (let i = 0; i < range.line; i++) offset += lines[i].length + 1
          view.dispatch({ selection: EditorSelection.cursor(this.from + offset + range.to), scrollIntoView: true })
          view.focus()
        })
        tr.appendChild(cell)
      })
      parent.appendChild(tr)
    }
    const thead = document.createElement("thead")
    addRow(thead, model.header, 0, "th")
    table.appendChild(thead)
    if (model.rows.length) {
      const tbody = document.createElement("tbody")
      model.rows.forEach((cells, i) => addRow(tbody, cells, i + 1, "td"))
      table.appendChild(tbody)
    }
    wrap.appendChild(table)
    return wrap
  }

  ignoreEvent() {
    return true
  }
}

const setFocused = StateEffect.define<boolean>()

function tableDecorations(state: EditorState, focused: boolean): DecorationSet {
  const out: Range<Decoration>[] = []
  const heads = focused ? state.selection.ranges : []
  syntaxTree(state).iterate({
    enter(node) {
      if (node.name !== "Table") return
      const first = state.doc.lineAt(node.from)
      const last = state.doc.lineAt(Math.max(node.from, node.to - (state.doc.sliceString(node.to - 1, node.to) === "\n" ? 1 : 0)))
      const editing = heads.some((r) => r.to >= first.from && r.from <= last.to)
      if (editing) {
        for (let n = first.number; n <= last.number; n++) {
          const line = state.doc.line(n)
          out.push(Decoration.line({ class: n === first.number + 1 ? "cm-doc-tablesrc cm-doc-tabledelim" : "cm-doc-tablesrc" }).range(line.from))
        }
      } else {
        const source = state.doc.sliceString(first.from, last.to)
        out.push(Decoration.replace({ widget: new TableWidget(source, first.from), block: true }).range(first.from, last.to))
      }
      return false
    },
  })
  return Decoration.set(out, true)
}

/** Tables as tables (block widgets must come from state, not a plugin).
 * Shown as text while the cursor is in one and the editor has focus. */
const tableField = StateField.define<{ focused: boolean; deco: DecorationSet }>({
  create: (state) => ({ focused: false, deco: tableDecorations(state, false) }),
  update(value, tr) {
    let focused = value.focused
    for (const e of tr.effects) if (e.is(setFocused)) focused = e.value
    const treeChanged = syntaxTree(tr.state) !== syntaxTree(tr.startState)
    if (!tr.docChanged && !tr.selection && !treeChanged && focused === value.focused) return value
    return { focused, deco: tableDecorations(tr.state, focused) }
  },
  provide: (f) => EditorView.decorations.from(f, (v) => v.deco),
})

const trackFocus = ViewPlugin.fromClass(
  class {
    update(u: ViewUpdate) {
      if (u.focusChanged) {
        const focused = u.view.hasFocus
        // Not inside an update: dispatch after it (unless it's gone).
        queueMicrotask(() => {
          if (u.view.dom.isConnected) u.view.dispatch({ effects: setFocused.of(focused) })
        })
      }
    }
  },
)

/** Lines of the table being edited: the live preview leaves their marks
 * showing, so the columns stay lined up. */
export function editingTableLines(state: EditorState): Set<number> {
  const lines = new Set<number>()
  for (const r of state.selection.ranges) {
    const at = tableAt(state, r.head)
    if (at) for (let n = at.first; n <= at.last; n++) lines.add(n)
  }
  return lines
}

export const tables = [tableField, trackFocus]

export const tableTheme = EditorView.theme({
  // A block widget sits outside .cm-line, so it keeps the page's right
  // margin itself.
  ".cm-doc-table": { padding: "6px 0 10px", marginRight: "var(--doc-page-x, 24px)", overflowX: "auto", cursor: "text" },
  ".cm-doc-table table": { borderCollapse: "collapse", width: "100%", fontSize: "0.95em", lineHeight: "1.45" },
  ".cm-doc-table th, .cm-doc-table td": {
    border: "1px solid color-mix(in oklab, currentColor 18%, transparent)",
    padding: "4px 8px",
    verticalAlign: "top",
    textAlign: "left",
  },
  ".cm-doc-table th": { fontWeight: "650", backgroundColor: "color-mix(in oklab, currentColor 5%, transparent)" },
  ".cm-doc-table td:hover, .cm-doc-table th:hover": { backgroundColor: "color-mix(in oklab, #3b82f6 8%, transparent)" },
  ".cm-doc-table code": { fontFamily: "ui-monospace, monospace", fontSize: "0.9em" },
  ".cm-doc-tablesrc": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.86em" },
  ".cm-doc-tabledelim": { opacity: "0.45" },
})
