import * as React from "react"
import { cn } from "../../lib/utils"

/** Lightweight controlled tabs in shadcn/ui style; no Radix dependency. */
interface TabsContextValue {
  value: string
  onValueChange: (v: string) => void
}
const TabsContext = React.createContext<TabsContextValue | null>(null)

export function Tabs({
  value,
  onValueChange,
  defaultValue,
  children,
  className,
}: {
  value?: string
  onValueChange?: (v: string) => void
  defaultValue?: string
  children: React.ReactNode
  className?: string
}) {
  const [internal, setInternal] = React.useState(defaultValue ?? "")
  const current = value ?? internal
  const handle = React.useCallback(
    (v: string) => {
      setInternal(v)
      onValueChange?.(v)
    },
    [onValueChange],
  )
  return (
    <TabsContext.Provider value={{ value: current, onValueChange: handle }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      role="tablist"
      className={cn(
        "g-seg",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  children,
  className,
}: {
  value: string
  children: React.ReactNode
  className?: string
}) {
  const ctx = React.useContext(TabsContext)
  const active = ctx?.value === value
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => ctx?.onValueChange(value)}
      className={cn(
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string
  children: React.ReactNode
  className?: string
}) {
  const ctx = React.useContext(TabsContext)
  if (ctx?.value !== value) return null
  return <div role="tabpanel" className={cn("mt-4", className)}>{children}</div>
}
