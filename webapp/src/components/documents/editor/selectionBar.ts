import { EditorSelection, type EditorState, Facet, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state"
import { Decoration, type DecorationSet, EditorView, showTooltip, type TooltipView, ViewPlugin, type ViewUpdate } from "@codemirror/view"
import { locate } from "./livePreview"

/**
 * The bar is a CodeMirror tooltip, so it follows the selection and the scroll; its
 * contents are the workspace's (React renders into `dom`). It opens on a keyboard
 * selection at once, on a pointer selection when the button comes up, and on Mod-J.
 */
export type SelectionBarInfo = {
  dom: HTMLElement
  from: number
  to: number
  text: string
  /** Opened with Mod-J: put the cursor in the request field. */
  focus: boolean
  /** Bumped every time the bar opens. */
  opened: number
}
export type SelectionBarListener = (info: SelectionBarInfo | null) => void

export const selectionBarListener = Facet.define<SelectionBarListener, SelectionBarListener | null>({
  combine: (values) => values[0] ?? null,
})

type BarState = { from: number; to: number; focus: boolean; opened: number } | null

const openBar = StateEffect.define<{ focus: boolean }>()
const closeBar = StateEffect.define<null>()

let openings = 0

const barField = StateField.define<BarState>({
  create: () => null,
  update(value, tr) {
    const r = tr.state.selection.main
    for (const e of tr.effects) {
      if (e.is(closeBar)) return null
      if (e.is(openBar)) return r.empty ? null : { from: r.from, to: r.to, focus: e.value.focus, opened: ++openings }
    }
    if (r.empty) return null
    if (value) {
      if (!tr.selection && !tr.docChanged) return value
      return value.from === r.from && value.to === r.to ? value : { ...value, from: r.from, to: r.to, focus: false }
    }
    // Shift+arrows, select all: at once. A pointer selection waits for
    // the button to come up (pointerOpens).
    if (tr.selection && tr.isUserEvent("select") && !tr.isUserEvent("select.pointer")) {
      return { from: r.from, to: r.to, focus: false, opened: ++openings }
    }
    return null
  },
  provide: (f) =>
    showTooltip.compute([f], (state) => {
      const bar = state.field(f)
      return bar ? { pos: bar.from, above: true, create: createBar } : null
    }),
})

function info(view: EditorView, dom: HTMLElement): SelectionBarInfo | null {
  const bar = view.state.field(barField, false)
  if (!bar) return null
  return { dom, from: bar.from, to: bar.to, text: view.state.sliceDoc(bar.from, bar.to), focus: bar.focus, opened: bar.opened }
}

/** One function for every bar, so CodeMirror keeps the same tooltip (and
 * the workspace its rendered bar) while the selection moves. */
function createBar(view: EditorView): TooltipView {
  const dom = document.createElement("div")
  dom.className = "cm-doc-ask"
  const notify = (v: EditorView) => v.state.facet(selectionBarListener)?.(info(v, dom))
  // Focus leaving both the text and the bar closes it.
  dom.addEventListener("focusout", () => window.setTimeout(() => closeIfAway(view), 0))
  return {
    dom,
    mount: () => notify(view),
    update: (u: ViewUpdate) => {
      if (u.state.field(barField) !== u.startState.field(barField)) notify(u.view)
    },
    destroy: () => view.state.facet(selectionBarListener)?.(null),
  }
}

function closeIfAway(view: EditorView) {
  if (!view.state.field(barField, false)) return
  const active = document.activeElement
  if (view.hasFocus || (active && view.dom.contains(active))) return
  view.dispatch({ effects: closeBar.of(null) })
}

const pointerOpens = EditorView.domEventHandlers({
  mousedown(_e, view) {
    const up = () => {
      window.removeEventListener("mouseup", up, true)
      window.setTimeout(() => {
        if (!view.state.selection.main.empty && !view.state.field(barField)) view.dispatch({ effects: openBar.of({ focus: false }) })
      }, 0)
    }
    window.addEventListener("mouseup", up, true)
    return false
  },
  touchend(_e, view) {
    // Phones: the selection settles after the touch.
    window.setTimeout(() => {
      if (!view.state.selection.main.empty && !view.state.field(barField)) view.dispatch({ effects: openBar.of({ focus: false }) })
    }, 300)
    return false
  },
})

const blurCloses = ViewPlugin.fromClass(
  class {
    update(u: ViewUpdate) {
      if (u.focusChanged && !u.view.hasFocus) window.setTimeout(() => closeIfAway(u.view), 0)
    }
  },
)

const BLOCK_MARK = /^\s*(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)/

/** The text Mod-J works on with nothing selected: the list item or
 * heading under the cursor (without its mark), else its paragraph. */
export function paragraphAt(state: EditorState, pos: number): { from: number; to: number } | null {
  const line = state.doc.lineAt(pos)
  if (!line.text.trim()) return null
  const mark = BLOCK_MARK.exec(line.text)
  if (mark) {
    const from = line.from + mark[0].length
    return line.to > from ? { from, to: line.to } : null
  }
  let first = line.number
  let last = line.number
  const plain = (n: number) => {
    const text = state.doc.line(n).text
    return text.trim() !== "" && !BLOCK_MARK.test(text)
  }
  while (first > 1 && plain(first - 1)) first--
  while (last < state.doc.lines && plain(last + 1)) last++
  return { from: state.doc.line(first).from, to: state.doc.line(last).to }
}

/** Mod-J: the bar on the selection, or on the paragraph under the cursor. */
export function openSelectionBar(view: EditorView): boolean {
  let { from, to } = view.state.selection.main
  if (from === to) {
    const p = paragraphAt(view.state, from)
    if (!p) return true
    ;({ from, to } = p)
  }
  view.dispatch({
    selection: EditorSelection.single(from, to),
    effects: [openBar.of({ focus: true }), EditorView.scrollIntoView(from, { y: "nearest", yMargin: 80 })],
  })
  return true
}

export function closeSelectionBar(view: EditorView): boolean {
  if (!view.state.field(barField, false)) return false
  view.dispatch({ effects: closeBar.of(null) })
  return true
}


/** Text a suggestion is being made for (by request id), and the text
 * pending suggestions would change. Both follow edits. */
export const markLoading = StateEffect.define<{ id: string; from: number; to: number }>()
export const unmarkLoading = StateEffect.define<string>()
export const setReviewMarks = StateEffect.define<string[]>()

type Marks = { loading: Map<string, { from: number; to: number }>; review: DecorationSet }

const loadingMark = Decoration.mark({ class: "cm-doc-loading" })
const reviewMark = Decoration.mark({ class: "cm-doc-pending" })

export const suggestionMarks = StateField.define<Marks>({
  create: () => ({ loading: new Map(), review: Decoration.none }),
  update(value, tr) {
    let { loading, review } = value
    if (tr.docChanged) {
      loading = new Map(
        [...loading].map(([id, r]) => {
          const from = tr.changes.mapPos(r.from, 1)
          return [id, { from, to: Math.max(from, tr.changes.mapPos(r.to, -1)) }]
        }),
      )
      review = review.map(tr.changes)
    }
    for (const e of tr.effects) {
      if (e.is(markLoading)) loading = new Map(loading).set(e.value.id, { from: e.value.from, to: e.value.to })
      else if (e.is(unmarkLoading)) {
        loading = new Map(loading)
        loading.delete(e.value)
      } else if (e.is(setReviewMarks)) {
        const text = tr.state.doc.toString()
        const spans = e.value
          .map((find) => locate(text, find))
          .filter((s): s is { from: number; to: number } => s !== null && s.to > s.from)
          .sort((a, b) => a.from - b.from || a.to - b.to)
        const b = new RangeSetBuilder<Decoration>()
        for (const s of spans) b.add(s.from, s.to, reviewMark)
        review = b.finish()
      }
    }
    return loading === value.loading && review === value.review ? value : { loading, review }
  },
  provide: (f) => [
    EditorView.decorations.from(f, (m) => m.review),
    EditorView.decorations.from(f, (m) =>
      Decoration.set(
        [...m.loading.values()].filter((r) => r.to > r.from).map((r) => loadingMark.range(r.from, r.to)),
        true,
      ),
    ),
  ],
})

export const selectionBar = [barField, pointerOpens, blurCloses, suggestionMarks]
