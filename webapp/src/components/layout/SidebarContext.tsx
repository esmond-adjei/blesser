/* eslint-disable react/only-export-components -- provider, hook, and toggle ship together as one unit */
import * as React from "react"
import { PanelLeft } from "lucide-react"
import { cn } from "../../lib/utils"

const STORAGE_KEY = "graduator.sidebar.open"

type SidebarContextValue = {
  open: boolean
  setOpen: (open: boolean) => void
  toggle: () => void
}

const SidebarContext = React.createContext<SidebarContextValue | null>(null)

function loadOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "0"
  } catch {
    return true
  }
}

/** Mount once in the app shell. */
export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpenState] = React.useState(loadOpen)

  const setOpen = React.useCallback((next: boolean) => {
    try {
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0")
    } catch {
      // Storage may be unavailable.
    }
    setOpenState(next)
  }, [])

  const toggle = React.useCallback(() => {
    setOpenState((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0")
      } catch {
        // Storage may be unavailable.
      }
      return next
    })
  }, [])

  const value = React.useMemo(() => ({ open, setOpen, toggle }), [open, setOpen, toggle])
  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
}

export function useSidebar(): SidebarContextValue {
  const ctx = React.useContext(SidebarContext)
  if (!ctx) throw new Error("useSidebar must be used inside SidebarProvider")
  return ctx
}

/** `open`/`onToggle` override global sidebar state for tests and embeds. */
export function SidebarToggle({
  open,
  onToggle,
  className,
}: {
  open?: boolean
  onToggle?: () => void
  className?: string
}) {
  const ctx = React.useContext(SidebarContext)
  const isOpen = open ?? ctx?.open ?? true
  const handleToggle = onToggle ?? ctx?.toggle
  if (!handleToggle) throw new Error("SidebarToggle must be used inside SidebarProvider or receive onToggle")

  return (
    <button
      type="button"
      onClick={handleToggle}
      aria-pressed={isOpen}
      data-tooltip={isOpen ? "Hide sidebar" : "Show sidebar"}
      className={cn(
        "hidden rounded-md p-1.5 transition-colors md:inline-flex cursor-pointer",
        isOpen ? "text-foreground" : "text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      <PanelLeft className="size-4" />
    </button>
  )
}
