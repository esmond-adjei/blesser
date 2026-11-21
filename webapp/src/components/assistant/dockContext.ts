import { createContext, useCallback, useContext } from "react"

export type Layout = "dock" | "panel"
export type Mode = Layout | "closed"

export interface DockState {
  mode: Mode
  layout: Layout
  chatId: string | undefined
  setMode: (mode: Mode) => void
  setLayout: (layout: Layout) => void
  setChatId: (id?: string) => void
}

export const DockContext = createContext<DockState | null>(null)

export function useDock() {
  const value = useContext(DockContext)
  if (!value) throw new Error("AssistantDockProvider is missing")
  return value
}

/** Opens the Assistant window in whichever layout was used last. */
export function useOpenAssistant() {
  const { layout, setMode } = useDock()
  return useCallback(() => setMode(layout), [layout, setMode])
}

