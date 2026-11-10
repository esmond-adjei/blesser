import type { CollectedField, FillInstruction, FillOutcome } from "../shared/types"
import { collectFields, type Collected } from "./collect"
import { applyFills } from "./fill"
import { clearMarks, flashField, markField } from "./highlight"

export interface BlesserContent {
  collect(): CollectedField[]
  fill(instructions: FillInstruction[]): FillOutcome[]
  focus(key: string): boolean
  clear(): void
}

declare global {
  interface Window {
    __blesser?: BlesserContent
  }
}

if (!window.__blesser) {
  let state: Collected | null = null
  window.__blesser = {
    collect() {
      state = collectFields(document, { layout: true })
      return state.fields
    },
    fill(instructions) {
      if (!state) state = collectFields(document, { layout: true })
      return applyFills(state, instructions, markField)
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
  }
}
