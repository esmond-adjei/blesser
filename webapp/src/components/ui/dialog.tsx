import * as React from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { cn } from "../../lib/utils"
import { useOpenTransition } from "../../lib/transition"

const ShownContext = React.createContext(false)

/** Portals to body because an ancestor transform would capture fixed descendants. Only DialogBody scrolls, so the close button and actions stay in view. */
export function Dialog({
  open,
  onOpenChange,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}) {
  const { render, shown } = useOpenTransition(open)

  React.useEffect(() => {
    if (!render) return
    const onKey = (e: KeyboardEvent) => {
      // Nested popovers (combobox, menus) mark Escape handled; let them
      // close themselves without taking the whole dialog down.
      if (e.key === "Escape" && !e.defaultPrevented) onOpenChange(false)
    }
    document.addEventListener("keydown", onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prev
    }
  }, [render, onOpenChange])

  if (!render) return null
  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pb-4 pt-[12dvh] transition-opacity duration-200 motion-reduce:transition-none",
        shown ? "opacity-100" : "opacity-0",
      )}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false)
      }}
    >
      <ShownContext.Provider value={shown}>{children}</ShownContext.Provider>
    </div>,
    document.body,
  )
}

export function DialogContent({
  className,
  children,
  onClose,
}: {
  className?: string
  children: React.ReactNode
  onClose: () => void
}) {
  const shown = React.useContext(ShownContext)
  return (
    <div
      role="dialog"
      aria-modal="true"
      className={cn(
        "relative flex max-h-[calc(88dvh-1rem)] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-surface p-0 text-label shadow-xl transition-[opacity,translate] duration-[320ms] ease-out motion-reduce:transform-none motion-reduce:transition-none",
        // Dialogs rise 8px and fade; no scale.
        shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        className,
      )}
    >
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute right-4 top-4 z-20 flex size-7 cursor-pointer items-center justify-center rounded-full bg-fill-quiet text-label-secondary transition-colors hover:bg-fill hover:text-label"
      >
        <X className="size-4" />
      </button>
      {children}
    </div>
  )
}

/** Fixed top section: title, optional subtitle, and room for the close button. */
export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex shrink-0 flex-col gap-1.5 px-6 pr-14 pt-6 text-left",
        className,
      )}
      {...props}
    />
  )
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("type-panel-title", className)} {...props} />
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("type-meta", className)} {...props} />
}

/** The only scrolling region in a dialog. */
export function DialogBody({ className, ...props }: React.ComponentPropsWithRef<"div">) {
  return (
    <div
      className={cn(
        "nice-scroll min-h-0 flex-auto overflow-y-auto overscroll-contain px-6 py-5",
        className,
      )}
      {...props}
    />
  )
}

/** Fixed bottom section. Sits outside DialogBody, so actions never scroll away. */
export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex shrink-0 flex-col-reverse gap-2 px-6 pt-1 pb-6 sm:flex-row sm:justify-end",
        className,
      )}
      {...props}
    />
  )
}
