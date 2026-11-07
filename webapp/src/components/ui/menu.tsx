import * as React from "react"
import { createPortal } from "react-dom"
import { cn } from "../../lib/utils"

const MENU_GAP = 4
const VIEWPORT_MARGIN = 8

/** Portalled to body so scroll containers never clip it; flips up when short on room. */
export function Menu({
  trigger,
  label,
  children,
  align = "end",
  maxHeight = 320,
  className,
}: {
  trigger: React.ReactNode
  label: string
  children: React.ReactNode
  /** Line the popover up with the trigger's right edge (end) or left (start). */
  align?: "start" | "end"
  /** Cap the popover height (px) — overflow scrolls within the menu. */
  maxHeight?: number
  className?: string
}) {
  const [open, setOpen] = React.useState(false)
  const [pos, setPos] = React.useState<{ top: number; left: number } | null>(null)
  const rootRef = React.useRef<HTMLDivElement | null>(null)
  const contentRef = React.useRef<HTMLDivElement | null>(null)

  const place = React.useCallback(() => {
    const anchor = rootRef.current
    const content = contentRef.current
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    const w = content?.offsetWidth ?? 192
    const h = content?.offsetHeight ?? 0
    const left = Math.max(VIEWPORT_MARGIN, Math.min(align === "start" ? r.left : r.right - w, vw - w - VIEWPORT_MARGIN))
    const below = r.bottom + MENU_GAP
    const above = Math.max(VIEWPORT_MARGIN, r.top - MENU_GAP - h)
    const top = h > 0 && r.bottom + MENU_GAP + h > vh - VIEWPORT_MARGIN ? above : below
    setPos((prev) => (prev && prev.top === top && prev.left === left ? prev : { top, left }))
  }, [align])

  // Measure before paint so neither the initial placement nor a flip flashes.
  React.useLayoutEffect(() => {
    if (open) place()
  }, [open, children, place])

  // Async content changes size without changing `children`, so re-place on
  // resize; observer callbacks run after layout but before paint.
  React.useLayoutEffect(() => {
    const content = contentRef.current
    if (!open || !content || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver(() => place())
    ro.observe(content)
    return () => ro.disconnect()
  }, [open, place])

  React.useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (rootRef.current?.contains(t)) return
      if (contentRef.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return
      setOpen(false)
      // Back to the trigger, so keyboard users don't lose their place.
      rootRef.current?.querySelector<HTMLElement>("button, [tabindex]")?.focus()
    }
    document.addEventListener("pointerdown", onPointerDown)
    document.addEventListener("keydown", onKey)
    // Capture: nested scroll containers don't bubble scroll events.
    document.addEventListener("scroll", place, true)
    window.addEventListener("resize", place)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown)
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("scroll", place, true)
      window.removeEventListener("resize", place)
    }
  }, [open, place])

  return (
    // data-open lets a hover-revealed trigger stay visible while its menu is open.
    <div ref={rootRef} data-open={open || undefined} className="relative shrink-0">
      <div onClick={() => setOpen((o) => !o)}>{trigger}</div>
      {open &&
        createPortal(
          <div
            ref={contentRef}
            role="menu"
            aria-label={label}
            style={{
              position: "fixed",
              top: pos?.top ?? 0,
              left: pos?.left ?? 0,
              visibility: pos ? "visible" : "hidden",
              // Short viewports shrink the cap rather than push the popover off-screen.
              maxHeight: Math.max(160, Math.min(maxHeight, window.innerHeight - 2 * VIEWPORT_MARGIN)),
            }}
            className={cn("nice-scroll z-50 w-56 overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md", className)}
          >
            {React.Children.map(children, (child) =>
              React.isValidElement<MenuItemProps>(child)
                ? React.cloneElement(child, {
                    onSelect: () => {
                      setOpen(false)
                      child.props.onSelect?.()
                    },
                  })
                : child,
            )}
          </div>,
          document.body,
        )}
    </div>
  )
}

interface MenuItemProps {
  onSelect?: () => void
  disabled?: boolean
  destructive?: boolean
  children: React.ReactNode
}

export function MenuItem({ onSelect, disabled, destructive, children }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => onSelect?.()}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
        destructive && "text-destructive hover:text-destructive",
      )}
    >
      {children}
    </button>
  )
}

export function MenuSeparator() {
  return <div role="separator" className="mx-1 my-1 h-px bg-border" />
}
