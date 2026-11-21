import { createContext, useContext } from "react"
import type { ContextChip, UiContext } from "../../lib/assistant"

export interface ChipView extends ContextChip {
  added: boolean
}

export interface PageContextValue {
  chips: ChipView[]
  toggle: (key: string) => void
  dismiss: (key: string) => void
  attachSelection: (text: string) => void
  /** The context for the next question, then clears what was a one-off. */
  take: () => UiContext | undefined
  hasRecord: boolean
}

export const PageContext = createContext<PageContextValue | null>(null)

export function usePageContext() {
  const value = useContext(PageContext)
  if (!value) throw new Error("PageContextProvider is missing")
  return value
}
