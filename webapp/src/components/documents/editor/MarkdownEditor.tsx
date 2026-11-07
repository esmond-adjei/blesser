import * as React from "react"
import { defaultKeymap, history, historyKeymap, indentWithTab, redoDepth, undoDepth } from "@codemirror/commands"
import { defineLanguageFacet, foldGutter, foldKeymap, Language, LanguageSupport } from "@codemirror/language"
import { GFM, parser as markdownParser } from "@lezer/markdown"
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search"
import { Compartment, EditorState } from "@codemirror/state"
import { EditorView, keymap, placeholder as placeholderExt } from "@codemirror/view"
import { type BlockStyle, blockStyleAt, type EditorCommand, type Marks, marksAt, runCommand } from "./format"
import {
  editorTheme,
  foldMarker,
  foldOnHover,
  headingFolding,
  highlightField,
  livePreview,
  locate,
  pageBreakField,
  setHighlight,
  setPageBreaks,
} from "./livePreview"
import {
  closeSelectionBar,
  markLoading,
  openSelectionBar,
  selectionBar,
  type SelectionBarListener,
  selectionBarListener,
  setReviewMarks,
  suggestionMarks,
  unmarkLoading,
} from "./selectionBar"
import { SHORTCUTS } from "./shortcuts"
import { enterInTable, moveCell, tableAt, tables, tableTheme } from "./tables"

import { minimalChange } from "../documentText"

export type { SelectionBarInfo } from "./selectionBar"

// Plain @lezer/markdown: @codemirror/lang-markdown also bundles HTML, CSS and
// JavaScript parsers, which a document never uses.
const markdownLanguage = new Language(
  defineLanguageFacet({ commentTokens: { block: { open: "<!--", close: "-->" } } }),
  markdownParser.configure([GFM]),
  [],
  "markdown",
)
const markdown = () => new LanguageSupport(markdownLanguage)

const formatKey = (key: string, cmd: EditorCommand) => ({
  key,
  run: (v: EditorView) => {
    runCommand(v, cmd)
    return true
  },
})
const formatKeys = [
  formatKey(SHORTCUTS.bold, { type: "bold" }),
  formatKey(SHORTCUTS.italic, { type: "italic" }),
  formatKey(SHORTCUTS.underline, { type: "underline" }),
  formatKey(SHORTCUTS.bullets, { type: "list", ordered: false }),
  formatKey(SHORTCUTS.numbers, { type: "list", ordered: true }),
  formatKey(SHORTCUTS.normal, { type: "block", style: "normal" }),
  formatKey(SHORTCUTS.h1, { type: "block", style: "h1" }),
  formatKey(SHORTCUTS.h2, { type: "block", style: "h2" }),
  formatKey(SHORTCUTS.h3, { type: "block", style: "h3" }),
]

export type MarkdownEditorHandle = {
  jumpTo: (pos: number) => void
  /** Mark the passage `find` quotes; false when it is not there exactly once. */
  highlight: (find: string | null) => boolean
  /** Mark `quote` on line `line` (0-based); false when it isn't there. */
  highlightOnLine: (line: number, quote: string) => boolean
  focus: () => void
  exec: (cmd: EditorCommand) => void
  selection: () => string
  /** Where the selection's head is on screen, to place a popover under. */
  caretRect: () => { left: number; top: number; bottom: number } | null
  /** The document position at a screen height, for the outline's
   * "you are here". */
  posAtY: (clientY: number) => number | null
  /** Draw the PDF's page breaks before these 1-based lines. */
  setPageBreaks: (breaks: { page: number; line: number }[]) => void
  /** The selection bar: open it (Mod-J does too), or close it. */
  openBar: () => void
  closeBar: () => void
  /** Mark text a suggestion is being made for; it follows edits. */
  markLoading: (id: string, from: number, to: number) => void
  unmarkLoading: (id: string) => void
  loadingRange: (id: string) => { from: number; to: number } | null
  setReviewMarks: (finds: string[]) => void
}

export type EditorStatus = {
  block: BlockStyle | "other"
  marks: Marks
  canUndo: boolean
  canRedo: boolean
  inTable: boolean
}

/**
 * Controlled loosely: `value` replaces the text only when it differs from what the
 * editor holds (a load, an accepted suggestion); typing reports through `onChange`.
 */
export const MarkdownEditor = React.forwardRef<
  MarkdownEditorHandle,
  {
    value: string
    onChange: (text: string) => void
    readOnly?: boolean
    placeholder?: string
    ariaLabel?: string
    onStatus?: (status: EditorStatus) => void
    onBlur?: () => void
    /** Mod-K: the workspace opens its link popover. */
    onLinkRequest?: () => void
    /** The selection bar opened, moved or closed (null). */
    onSelectionBar?: SelectionBarListener
  }
>(function MarkdownEditor({ value, onChange, readOnly = false, placeholder, ariaLabel, onStatus, onBlur, onLinkRequest, onSelectionBar }, ref) {
  const host = React.useRef<HTMLDivElement | null>(null)
  const view = React.useRef<EditorView | null>(null)
  const onChangeRef = React.useRef(onChange)
  onChangeRef.current = onChange
  const onStatusRef = React.useRef(onStatus)
  onStatusRef.current = onStatus
  const onBlurRef = React.useRef(onBlur)
  onBlurRef.current = onBlur
  const onLinkRef = React.useRef(onLinkRequest)
  onLinkRef.current = onLinkRequest
  const onBarRef = React.useRef(onSelectionBar)
  onBarRef.current = onSelectionBar
  const lastStatus = React.useRef("")
  const readOnlyConf = React.useRef(new Compartment())

  React.useEffect(() => {
    if (!host.current) return
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          markdown(),
          EditorView.lineWrapping,
          foldGutter({ markerDOM: foldMarker }),
          foldOnHover,
          headingFolding,
          livePreview,
          tables,
          tableTheme,
          highlightField,
          pageBreakField,
          selectionBar,
          selectionBarListener.of((bar) => onBarRef.current?.(bar)),
          highlightSelectionMatches(),
          editorTheme,
          keymap.of([
            ...formatKeys,
            {
              key: SHORTCUTS.link,
              run: () => {
                if (!onLinkRef.current) return false
                onLinkRef.current()
                return true
              },
            },
            { key: SHORTCUTS.suggest, run: openSelectionBar },
            { key: "Escape", run: closeSelectionBar },
            // In a table: Tab and Shift-Tab move between cells, Enter adds a row.
            { key: "Tab", run: moveCell(1) },
            { key: "Shift-Tab", run: moveCell(-1) },
            { key: "Enter", run: enterInTable },
            indentWithTab,
            ...defaultKeymap,
            ...historyKeymap,
            ...foldKeymap,
            ...searchKeymap,
          ]),
          readOnlyConf.current.of(EditorState.readOnly.of(readOnly)),
          placeholder ? placeholderExt(placeholder) : [],
          EditorView.contentAttributes.of({ "aria-label": ariaLabel ?? "Document text", spellcheck: "true" }),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) onChangeRef.current(u.state.doc.toString())
            if (u.docChanged || u.selectionSet || u.transactions.length) {
              const status: EditorStatus = {
                block: blockStyleAt(u.state),
                marks: marksAt(u.state),
                canUndo: undoDepth(u.state) > 0,
                canRedo: redoDepth(u.state) > 0,
                inTable: tableAt(u.state, u.state.selection.main.head) !== null,
              }
              const key = JSON.stringify(status)
              if (key !== lastStatus.current) {
                lastStatus.current = key
                onStatusRef.current?.(status)
              }
            }
            if (u.focusChanged && !u.view.hasFocus) onBlurRef.current?.()
          }),
        ],
      }),
    })
    view.current = v
    return () => {
      v.destroy()
      view.current = null
    }
    // Created once; value and readOnly are synced below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  React.useEffect(() => {
    const v = view.current
    if (!v) return
    const change = minimalChange(v.state.doc.toString(), value)
    if (change) v.dispatch({ changes: change, effects: setHighlight.of(null) })
  }, [value])

  React.useEffect(() => {
    view.current?.dispatch({ effects: readOnlyConf.current.reconfigure(EditorState.readOnly.of(readOnly)) })
  }, [readOnly])

  React.useImperativeHandle(ref, () => ({
    jumpTo(pos) {
      const v = view.current
      if (!v) return
      const at = Math.min(pos, v.state.doc.length)
      v.dispatch({ selection: { anchor: at }, effects: EditorView.scrollIntoView(at, { y: "start", yMargin: 24 }) })
      v.focus()
    },
    highlight(find) {
      const v = view.current
      if (!v) return false
      const span = find ? locate(v.state.doc.toString(), find) : null
      v.dispatch({
        effects: [
          setHighlight.of(span),
          ...(span ? [EditorView.scrollIntoView(span.from, { y: "center" })] : []),
        ],
      })
      return span !== null
    },
    highlightOnLine(line, quote) {
      const v = view.current
      if (!v || line + 1 > v.state.doc.lines) return false
      const l = v.state.doc.line(line + 1)
      const at = l.text.indexOf(quote)
      const span = at < 0 ? null : { from: l.from + at, to: l.from + at + quote.length }
      v.dispatch({
        effects: [setHighlight.of(span), ...(span ? [EditorView.scrollIntoView(span.from, { y: "center" })] : [])],
      })
      return span !== null
    },
    focus() {
      view.current?.focus()
    },
    exec(cmd) {
      if (view.current) runCommand(view.current, cmd)
    },
    selection() {
      const v = view.current
      if (!v) return ""
      const { from, to } = v.state.selection.main
      return v.state.sliceDoc(from, to)
    },
    caretRect() {
      const v = view.current
      if (!v) return null
      const { from, head } = v.state.selection.main
      const start = v.coordsAtPos(from)
      const end = v.coordsAtPos(head)
      if (!start || !end) return null
      return { left: start.left, top: Math.min(start.top, end.top), bottom: Math.max(start.bottom, end.bottom) }
    },
    posAtY(clientY) {
      const v = view.current
      if (!v) return null
      return v.lineBlockAtHeight(clientY - v.documentTop).from
    },
    setPageBreaks(breaks) {
      view.current?.dispatch({ effects: setPageBreaks.of(breaks) })
    },
    openBar() {
      const v = view.current
      if (!v) return
      v.focus()
      openSelectionBar(v)
    },
    closeBar() {
      if (view.current) closeSelectionBar(view.current)
    },
    markLoading(id, from, to) {
      view.current?.dispatch({ effects: markLoading.of({ id, from, to }) })
    },
    unmarkLoading(id) {
      view.current?.dispatch({ effects: unmarkLoading.of(id) })
    },
    loadingRange(id) {
      return view.current?.state.field(suggestionMarks).loading.get(id) ?? null
    },
    setReviewMarks(finds) {
      view.current?.dispatch({ effects: setReviewMarks.of(finds) })
    },
  }))

  return <div ref={host} className="doc-editor h-full" />
})
