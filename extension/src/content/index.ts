import type { CollectedField, ExportField, PageDetails, FillInstruction, FillOutcome, PageMessage, ProgressField, WriteResult } from "../shared/types"
import { collectFields, type Collected } from "./collect"
import { applyFills, writeField } from "./fill"
import { clearMarks, flashField, markField, unmarkField } from "./highlight"
import { pageDetails } from "./details"
import { exportOf, frameSection, trackProgress, type ProgressTracker } from "./progress"
import { watchPage, type Watcher } from "./watch"

export interface BlesserContent {
  collect(): CollectedField[]
  fill(instructions: FillInstruction[]): FillOutcome[]
  write(key: string, value: string | string[] | null): WriteResult
  focus(key: string): boolean
  clear(): void
  /** Starts reporting progress (once per page) and returns the count now. */
  track(): ProgressField[]
  /** Every field with what it holds now, for the Word export. */
  snapshot(): ExportField[]
  /** Title, funder and deadline as the page states them. */
  details(): PageDetails
}

declare global {
  interface Window {
    __blesser?: BlesserContent
  }
}

if (!window.__blesser) {
  let state: Collected | null = null
  let watcher: Watcher | null = null
  let tracker: ProgressTracker | null = null
  const notify = (message: PageMessage) => {
    try {
      void chrome.runtime.sendMessage(message).catch(() => {})
    } catch {
      // The extension was reloaded or removed; this copy of the script is orphaned.
      watcher?.stop()
      tracker?.stop()
    }
  }
  const ensureState = () => (state ??= collectFields(document, { layout: true }))

  window.__blesser = {
    collect() {
      state = collectFields(document, { layout: true })
      watcher?.reset()
      return state.fields
    },
    fill(instructions) {
      const outcomes = applyFills(ensureState(), instructions, markField)
      watcher ??= watchPage(document, () => state, notify)
      watcher.reset()
      return outcomes
    },
    write(key, value) {
      const current = ensureState()
      const result = writeField(current, key, value, markField)
      const target = current.targets.get(key)
      const erased = value === null || value === "" || (Array.isArray(value) && !value.length)
      if (result.ok && erased && target) unmarkField(key, target)
      return result
    },
    focus(key) {
      const target = state?.targets.get(key)
      if (!target?.isConnected) return false
      target.scrollIntoView({ block: "center", behavior: "smooth" })
      const control = state?.controls.get(key)?.[0] as HTMLElement | undefined
      control?.focus({ preventScroll: true })
      flashField(target)
      return true
    },
    clear() {
      clearMarks(document)
    },
    track() {
      tracker ??= trackProgress(document, (fields) => notify({ type: "blesser.progress", fields }), { fallbackSection: frameSection(window) })
      return tracker.snapshot()
    },
    details() {
      return pageDetails(document)
    },
    snapshot() {
      return exportOf(collectFields(document, { layout: true }), frameSection(window))
    },
  }
}
