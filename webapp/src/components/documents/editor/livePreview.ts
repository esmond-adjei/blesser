import { syntaxTree, foldService } from "@codemirror/language"
import { type EditorState, RangeSet, RangeSetBuilder, StateEffect, StateField, type Range } from "@codemirror/state"
import {
  Decoration,
  type DecorationSet,
  EditorView,
  GutterMarker,
  gutterLineClass,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from "@codemirror/view"
import { editingTableLines } from "./tables"

/** Obsidian-style live preview: Markdown renders as you type, with marks
 * shown only on the edited line. */

class BulletWidget extends WidgetType {
  eq() {
    return true
  }
  toDOM() {
    const span = document.createElement("span")
    span.className = "cm-doc-bullet"
    span.textContent = "•"
    return span
  }
}

const bullet = Decoration.replace({ widget: new BulletWidget() })
/** A list marker and its space, raw while editing ("1. ", "- "): in the
 * same fixed box as the bullet, so the text starts at the same place. */
const listMark = Decoration.mark({ class: "cm-doc-listmark" })
/** The box a list marker sits in; wrapped lines hang this far in. */
const MARK_EM = 1.5

/** A list item's line: indented by its depth, with wrapped lines lined up
 * under the item's text rather than under the marker. */
function listLine(depth: number) {
  const pad = (depth + 1) * MARK_EM
  return Decoration.line({ attributes: { style: `padding-left: ${pad}em; text-indent: -${MARK_EM}em` } })
}
const hide = Decoration.replace({})
const marks: Record<string, Decoration> = {
  StrongEmphasis: Decoration.mark({ class: "cm-doc-strong" }),
  Emphasis: Decoration.mark({ class: "cm-doc-em" }),
  InlineCode: Decoration.mark({ class: "cm-doc-code" }),
  Link: Decoration.mark({ class: "cm-doc-link" }),
}
const underline = Decoration.mark({ class: "cm-doc-u" })
const rule = Decoration.line({ class: "cm-doc-hr" })
const UNDERLINE = /<u>(.*?)<\/u>/g

function activeLines(state: EditorState): Set<number> {
  const lines = new Set<number>()
  for (const r of state.selection.ranges) {
    const first = state.doc.lineAt(r.from).number
    const last = state.doc.lineAt(r.to).number
    for (let n = first; n <= last; n++) lines.add(n)
  }
  return lines
}

function build(view: EditorView): DecorationSet {
  const { state } = view
  const active = view.hasFocus ? activeLines(state) : new Set<number>()
  // A table being edited shows its marks on every row, so its columns
  // stay lined up.
  if (view.hasFocus) for (const n of editingTableLines(state)) active.add(n)
  const out: Range<Decoration>[] = []
  for (const { from, to } of view.visibleRanges) {
    syntaxTree(state).iterate({
      from,
      to,
      enter(node) {
        const line = state.doc.lineAt(node.from)
        const editing = active.has(line.number)
        const heading = /^ATXHeading(\d)$/.exec(node.name)
        if (heading) {
          out.push(Decoration.line({ class: `cm-doc-h${heading[1]}` }).range(line.from))
          return
        }
        if (node.name in marks) {
          if (node.to > node.from) out.push(marks[node.name].range(node.from, node.to))
          return
        }
        if (node.name === "ListMark") {
          // Its depth shows as padding, so the source's leading spaces go.
          let depth = -1
          for (let p = node.node.parent; p; p = p.parent) if (p.name === "BulletList" || p.name === "OrderedList") depth++
          const end = node.to + (state.doc.sliceString(node.to, node.to + 1) === " " ? 1 : 0)
          out.push(listLine(Math.max(0, depth)).range(line.from))
          if (node.from > line.from && !/\S/.test(state.doc.sliceString(line.from, node.from)))
            out.push(hide.range(line.from, node.from))
          const text = state.doc.sliceString(node.from, node.to)
          out.push(!editing && (text === "-" || text === "*" || text === "+") ? bullet.range(node.from, end) : listMark.range(node.from, end))
          return
        }
        if (editing) return
        if (node.name === "HorizontalRule") {
          out.push(rule.range(line.from), hide.range(node.from, node.to))
          return
        }
        if (node.name === "HeaderMark") {
          // The marks and the space after them: "## " -> "".
          const after = state.doc.sliceString(node.to, node.to + 1) === " " ? 1 : 0
          out.push(hide.range(node.from, node.to + after))
        } else if (node.name === "EmphasisMark" || node.name === "CodeMark" || node.name === "LinkMark") {
          out.push(hide.range(node.from, node.to))
        } else if (node.name === "URL" && node.node.parent?.name === "Link") {
          out.push(hide.range(node.from, node.to))
        }
      },
    })
    // Underline, written <u>…</u> (Markdown has no mark for it): the
    // tags show only on the line being edited.
    for (let pos = from; pos <= to; ) {
      const line = state.doc.lineAt(pos)
      const editing = active.has(line.number)
      for (const m of line.text.matchAll(UNDERLINE)) {
        const start = line.from + (m.index ?? 0)
        const end = start + m[0].length
        if (m[1]) out.push(underline.range(start + 3, end - 4))
        if (!editing) out.push(hide.range(start, start + 3), hide.range(end - 4, end))
      }
      pos = line.to + 1
    }
  }
  return Decoration.set(out, true)
}

export const livePreview = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    constructor(view: EditorView) {
      this.decorations = build(view)
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged || u.selectionSet || u.focusChanged) {
        this.decorations = build(u.view)
      }
    }
  },
  { decorations: (v) => v.decorations },
)

/** A heading folds everything up to the next heading of its level or higher. */
export const headingFolding = foldService.of((state, lineStart) => {
  const line = state.doc.lineAt(lineStart)
  const m = /^(#{1,6})\s/.exec(line.text)
  if (!m) return null
  const level = m[1].length
  let end = state.doc.length
  for (let n = line.number + 1; n <= state.doc.lines; n++) {
    const next = /^(#{1,6})\s/.exec(state.doc.line(n).text)
    if (next && next[1].length <= level) {
      end = state.doc.line(n - 1).to
      break
    }
  }
  return end > line.to ? { from: line.to, to: end } : null
})

/** Fold arrows show only where they're wanted: the line under the
 * pointer, the cursor's line, and folded headings (the marker itself
 * carries that). Keyboard folding (Ctrl-Shift-[ / ]) is unaffected. */
const setHover = StateEffect.define<number | null>()
const hoverField = StateField.define<number | null>({
  create: () => null,
  update(value, tr) {
    for (const e of tr.effects) if (e.is(setHover)) return e.value
    return value === null || !tr.docChanged ? value : tr.changes.mapPos(value)
  },
})
class LineClass extends GutterMarker {
  elementClass: string
  constructor(elementClass: string) {
    super()
    this.elementClass = elementClass
  }
}
const hoverClass = new LineClass("cm-doc-hover")
const cursorClass = new LineClass("cm-doc-cursorline")
const revealLines = gutterLineClass.compute([hoverField, "selection"], (state) => {
  const hover = state.field(hoverField)
  const cursor = state.doc.lineAt(state.selection.main.head).from
  const marks = [cursorClass.range(cursor)]
  if (hover !== null && hover <= state.doc.length) marks.push(hoverClass.range(state.doc.lineAt(hover).from))
  return RangeSet.of(marks, true)
})
const trackHover = EditorView.domEventHandlers({
  mousemove(e, view) {
    const pos = view.posAtCoords({ x: e.clientX, y: e.clientY }, false)
    const line = view.state.doc.lineAt(pos).from
    if (line !== view.state.field(hoverField)) view.dispatch({ effects: setHover.of(line) })
  },
  mouseleave(_e, view) {
    if (view.state.field(hoverField) !== null) view.dispatch({ effects: setHover.of(null) })
  },
})
export const foldOnHover = [hoverField, revealLines, trackHover]

/** The fold gutter's marker: hidden by CSS until its line is revealed. */
export function foldMarker(open: boolean): HTMLElement {
  const el = document.createElement("span")
  el.className = open ? "cm-doc-fold" : "cm-doc-fold cm-doc-folded"
  el.textContent = open ? "▾" : "▸"
  el.title = open ? "Fold section (Ctrl+Shift+[)" : "Unfold section (Ctrl+Shift+])"
  return el
}

/** Page breaks: a band before each line that starts a page of the
 * PDF, from the server's layout of the same text (POST /cv/layout). Above
 * the band, `fill` pads out the page it ends, so every page is a whole
 * sheet however much text it holds (see `pageFill`). */
class PageBreakWidget extends WidgetType {
  page: number
  fill: number
  constructor(page: number, fill: number) {
    super()
    this.page = page
    this.fill = fill
  }
  eq(other: PageBreakWidget) {
    return other.page === this.page && other.fill === this.fill
  }
  toDOM() {
    const el = document.createElement("div")
    el.className = "cm-doc-pagebreak"
    el.setAttribute("aria-label", `Page ${this.page}`)
    el.style.setProperty("--doc-page-fill", `${this.fill}px`)
    const label = document.createElement("span")
    label.textContent = `Page ${this.page}`
    el.appendChild(label)
    return el
  }
  updateDOM(dom: HTMLElement, _view: EditorView, from: this) {
    if (from.page !== this.page) return false
    dom.style.setProperty("--doc-page-fill", `${this.fill}px`)
    return true
  }
  ignoreEvent() {
    return true
  }
}

/** The band between two pages, in px (border-box). */
const PAGE_BAND = 28

interface PageBreaks {
  breaks: { page: number; line: number }[]
  fills: number[]
  deco: DecorationSet
}

function pageDecorations(state: EditorState, breaks: { page: number; line: number }[], fills: number[]) {
  const doc = state.doc
  return Decoration.set(
    breaks
      .map((b, i) => ({ ...b, fill: fills[i] ?? 0 }))
      .filter((b) => b.line >= 1 && b.line <= doc.lines)
      .map((b) => Decoration.widget({ widget: new PageBreakWidget(b.page, b.fill), block: true, side: -1 }).range(doc.line(b.line).from)),
    true,
  )
}

/** Every page a whole sheet. The sheet (`[data-doc-sheet]`) gives the
 * page height as `--doc-page-h` (0 on a phone: no sheets there); each
 * break pads out the page above it so its band starts where that page
 * ends, and the sheet is at least as tall as its pages. */
const pageFill = ViewPlugin.fromClass(
  class {
    pending = false
    view: EditorView
    constructor(view: EditorView) {
      this.view = view
      this.schedule()
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.geometryChanged || u.viewportChanged || u.startState.field(pageBreakField) !== u.state.field(pageBreakField)) this.schedule()
    }
    schedule() {
      if (this.pending) return
      this.pending = true
      this.view.requestMeasure({
        key: this,
        read: (view) => {
          this.pending = false
          const sheet = view.dom.closest<HTMLElement>("[data-doc-sheet]")
          if (!sheet) return null
          const css = getComputedStyle(sheet)
          const pageH = parseFloat(css.getPropertyValue("--doc-page-h")) || 0
          const pageY = parseFloat(css.getPropertyValue("--doc-page-y")) || 0
          const { breaks, fills } = view.state.field(pageBreakField)
          const doc = view.state.doc
          const top = view.documentTop - sheet.getBoundingClientRect().top
          let shift = 0
          const next = breaks.map((b, i) => {
            if (!pageH || b.line < 1 || b.line > doc.lines) return 0
            // Where the page above ends now, before this break's own fill
            // and with the earlier breaks' new fills.
            const at = top + view.lineBlockAt(doc.line(b.line).from).top + shift
            const end = (b.page - 1) * pageH + (b.page - 2) * PAGE_BAND - pageY
            const fill = Math.max(0, Math.round(end - at))
            shift += fill - (fills[i] ?? 0)
            return fill
          })
          const pages = breaks.length ? Math.max(...breaks.map((b) => b.page)) : 1
          return { sheet, next, minHeight: pageH ? pages * pageH + (pages - 1) * PAGE_BAND : 0 }
        },
        write: (m, view) => {
          if (!m) return
          m.sheet.style.minHeight = m.minHeight ? `${m.minHeight}px` : ""
          const { fills } = view.state.field(pageBreakField)
          const changed = m.next.length !== fills.length || m.next.some((f, i) => Math.abs(f - (fills[i] ?? 0)) > 1)
          // Not from inside the measure cycle: right after it.
          if (changed) queueMicrotask(() => view.dispatch({ effects: setPageFills.of(m.next) }))
        },
      })
    }
  },
)

/** Page starts as 1-based line numbers of the current text. */
export const setPageBreaks = StateEffect.define<{ page: number; line: number }[]>()
/** How far each break pads out the page it ends, in px. */
const setPageFills = StateEffect.define<number[]>()
export const pageBreakField = StateField.define<PageBreaks>({
  create: () => ({ breaks: [], fills: [], deco: Decoration.none }),
  update(value, tr) {
    let next: PageBreaks = { ...value, deco: value.deco.map(tr.changes) }
    if (tr.docChanged) {
      // Lines move with the text until the next layout says otherwise.
      const breaks: { page: number; line: number }[] = []
      next.deco.between(0, tr.state.doc.length, (from, _to, d) => {
        const widget = d.spec.widget as PageBreakWidget
        breaks.push({ page: widget.page, line: tr.state.doc.lineAt(from).number })
      })
      next = { ...next, breaks }
    }
    for (const e of tr.effects) {
      if (e.is(setPageBreaks)) next = { breaks: e.value, fills: next.fills, deco: pageDecorations(tr.state, e.value, next.fills) }
      if (e.is(setPageFills)) next = { ...next, fills: e.value, deco: pageDecorations(tr.state, next.breaks, e.value) }
    }
    return next
  },
  provide: (f) => [EditorView.decorations.from(f, (v) => v.deco), pageFill],
})

export const setHighlight = StateEffect.define<{ from: number; to: number } | null>()
const highlightMark = Decoration.mark({ class: "cm-doc-highlight" })

export const highlightField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    let next = value.map(tr.changes)
    for (const e of tr.effects) {
      if (e.is(setHighlight)) {
        const b = new RangeSetBuilder<Decoration>()
        if (e.value && e.value.to > e.value.from) b.add(e.value.from, e.value.to, highlightMark)
        next = b.finish()
      }
    }
    return next
  },
  provide: (f) => EditorView.decorations.from(f),
})

/** Where `find` occurs exactly once: exact match, else ignoring whitespace
 * between words (the server's rule in api/cv/service.py:locate). */
export function locate(text: string, find: string): { from: number; to: number } | null {
  if (!find) return null
  const first = text.indexOf(find)
  if (first !== -1) {
    return text.indexOf(find, first + 1) === -1 ? { from: first, to: first + find.length } : null
  }
  const words = find.split(/\s+/).filter(Boolean)
  if (!words.length) return null
  const pattern = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "g")
  const found = [...text.matchAll(pattern)]
  if (found.length !== 1) return null
  const start = found[0].index ?? 0
  return { from: start, to: start + found[0][0].length }
}

export const editorTheme = EditorView.theme({
  "&": { backgroundColor: "transparent", color: "inherit", fontSize: "15px" },
  "&.cm-focused": { outline: "none" },
  // The editor grows with its text and the canvas scrolls, so the scroller
  // never scrolls itself; visible, it lets a page break reach the sheet's
  // edges (the sheet does the clipping).
  ".cm-scroller": { fontFamily: "inherit", lineHeight: "1.65", overflow: "visible" },
  // The page (DocumentWorkspace) sets the margins: wide on a desktop page,
  // narrow on a phone.
  ".cm-content": { padding: "var(--doc-page-y, 24px) 0 calc(var(--doc-page-y, 24px) * 2)", caretColor: "currentColor" },
  ".cm-line": { padding: "0 var(--doc-page-x, 24px) 0 0" },
  // The fold arrows sit in the left margin.
  ".cm-gutters": {
    backgroundColor: "transparent",
    border: "none",
    color: "var(--muted-foreground, #64748b)",
    paddingLeft: "max(0px, calc(var(--doc-page-x, 24px) - 22px))",
  },
  ".cm-foldGutter .cm-gutterElement": { cursor: "pointer", padding: "0 4px" },
  // Hidden until the line is hovered or holds the cursor; a folded
  // heading keeps its arrow (index.css adds the fade, minus reduced motion).
  ".cm-doc-fold": { opacity: "0" },
  ".cm-doc-hover .cm-doc-fold, .cm-doc-cursorline .cm-doc-fold, .cm-doc-fold.cm-doc-folded, .cm-gutterElement:hover .cm-doc-fold": {
    opacity: "1",
  },
  ".cm-doc-u": { textDecoration: "underline", textUnderlineOffset: "2px" },
  // A horizontal line ("---"), drawn across the text column.
  ".cm-doc-hr": {
    backgroundImage: "linear-gradient(color-mix(in oklab, currentColor 30%, transparent), color-mix(in oklab, currentColor 30%, transparent))",
    backgroundSize: "calc(100% - var(--doc-page-x, 24px)) 1px",
    backgroundPosition: "left center",
    backgroundRepeat: "no-repeat",
  },
  // A gap in the sheet where the PDF starts a new page: the canvas shows
  // through, edge to edge, with the page number.
  ".cm-doc-pagebreak": {
    position: "relative",
    height: `${PAGE_BAND}px`,
    // Past both sheet edges: the sheet clips the overshoot a pixel outside itself, so the
    // gap also covers its outline. Above and below, the page's own margins, as on page one.
    margin: "calc(var(--doc-page-y, 24px) + var(--doc-page-fill, 0px)) -16px var(--doc-page-y, 24px) calc(-1 * var(--doc-page-x, 24px) - 16px)",
    boxSizing: "border-box",
    backgroundColor: "var(--doc-canvas, transparent)",
    borderTop: "1px solid var(--border, #e5e7eb)",
    borderBottom: "1px solid var(--border, #e5e7eb)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "11px",
    letterSpacing: "0.04em",
    color: "var(--muted-foreground, #64748b)",
    userSelect: "none",
  },
  ".cm-doc-h1": { fontSize: "1.75em", fontWeight: "700", lineHeight: "1.3", paddingTop: "0.2em" },
  ".cm-doc-h2": {
    fontSize: "1.25em",
    fontWeight: "700",
    paddingTop: "0.6em",
    // A rule under it that stops at the right margin, as a border would
    // run on through the line's padding to the page's edge.
    backgroundImage: "linear-gradient(color-mix(in oklab, currentColor 15%, transparent), color-mix(in oklab, currentColor 15%, transparent))",
    backgroundSize: "calc(100% - var(--doc-page-x, 24px)) 1px",
    backgroundPosition: "left bottom",
    backgroundRepeat: "no-repeat",
  },
  ".cm-doc-h3": { fontSize: "1.08em", fontWeight: "650", paddingTop: "0.3em" },
  ".cm-doc-h4, .cm-doc-h5, .cm-doc-h6": { fontWeight: "650" },
  ".cm-doc-strong": { fontWeight: "700" },
  ".cm-doc-em": { fontStyle: "italic" },
  ".cm-doc-code": { fontFamily: "ui-monospace, monospace", fontSize: "0.9em" },
  ".cm-doc-link": { textDecoration: "underline", textUnderlineOffset: "2px" },
  // The marker's box (MARK_EM wide). Its own text-indent is reset, as an
  // inline block inherits the line's negative one.
  ".cm-doc-bullet, .cm-doc-listmark": { display: "inline-block", minWidth: "1.5em", textIndent: "0", whiteSpace: "pre" },
  ".cm-doc-bullet": { opacity: "0.7" },
  // The selection bar is the workspace's own popover: no tooltip chrome.
  ".cm-tooltip.cm-doc-ask": { border: "none", backgroundColor: "transparent", zIndex: "30" },
  // Text a suggestion is on its way for, and text a pending one would change.
  ".cm-doc-loading": { backgroundColor: "color-mix(in oklab, #3b82f6 16%, transparent)", borderRadius: "2px" },
  ".cm-doc-pending": {
    textDecoration: "underline dotted color-mix(in oklab, #eda41d 85%, transparent)",
    textDecorationThickness: "2px",
    textUnderlineOffset: "4px",
  },
  ".cm-doc-highlight": { backgroundColor: "color-mix(in oklab, #eda41d 35%, transparent)", borderRadius: "2px" },
  // Find and replace (Ctrl+F, or the toolbar), in the app's colours.
  ".cm-panels": { backgroundColor: "var(--popover)", color: "var(--popover-foreground)" },
  ".cm-panels.cm-panels-top": { borderBottom: "1px solid var(--border)" },
  ".cm-panel.cm-search": { padding: "6px 8px", fontSize: "13px" },
  ".cm-panel.cm-search input, .cm-panel.cm-search button": {
    color: "inherit",
    backgroundColor: "var(--background)",
    border: "1px solid var(--input)",
    borderRadius: "6px",
    padding: "2px 8px",
    backgroundImage: "none",
  },
  ".cm-panel.cm-search label": { fontSize: "12px" },
  ".cm-searchMatch": { backgroundColor: "color-mix(in oklab, #eda41d 30%, transparent)" },
  ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "color-mix(in oklab, #eda41d 60%, transparent)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection": {
    backgroundColor: "color-mix(in oklab, #3b82f6 25%, transparent) !important",
  },
})
