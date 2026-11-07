import * as React from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { cn } from "../../lib/utils"

/** Anchored popover portalled to body (a bottom sheet under 640px). Handles initial focus, Escape, outside click, and focus return. */
export function Popover({
  trigger,
  children,
  label,
  align = "start",
  side = "bottom",
  className,
  open: openProp,
  onOpenChange,
  anchor,
  initialFocus = true,
  panelProps,
}: {
  trigger: (props: {
    ref: React.Ref<HTMLButtonElement>
    id: string
    onClick: () => void
    "aria-expanded": boolean
    "aria-haspopup": "dialog"
    "aria-controls": string | undefined
  }) => React.ReactNode
  children: (close: () => void) => React.ReactNode
  label: string
  align?: "start" | "end"
  side?: "bottom" | "top"
  className?: string
  /** Controlled open state, for a popover more than one control opens. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  /** Place under this element at its width instead of under the trigger. */
  anchor?: React.RefObject<HTMLElement | null>
  /** Off for a hover card, which must not pull focus from what the pointer is over. */
  initialFocus?: boolean
  /** Pointer handlers for the panel (a hover card stays open while hovered). */
  panelProps?: Pick<React.HTMLAttributes<HTMLDivElement>, "onMouseEnter" | "onMouseLeave">
}) {
  const [innerOpen, setInnerOpen] = React.useState(false)
  const open = openProp ?? innerOpen
  const setOpen = React.useCallback(
    (next: boolean) => {
      if (openProp === undefined) setInnerOpen(next)
      onOpenChange?.(next)
    },
    [openProp, onOpenChange],
  )
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)
  const panelRef = React.useRef<HTMLDivElement | null>(null)
  const id = React.useId()
  const headerId = React.useId()
  const triggerId = React.useId()
  const narrow = useNarrow()

  // By id rather than ref: `close` is handed to children during render.
  const close = React.useCallback(() => {
    setOpen(false)
    document.getElementById(triggerId)?.focus()
  }, [triggerId, setOpen])

  // Written straight to the panel: placement measures the DOM and stays in sync on scroll/resize.
  const place = React.useCallback(() => {
    const panel = panelRef.current
    if (!panel) return
    if (narrow) {
      // Drop stale placement writes so the bottom sheet doesn't keep an old top/width.
      panel.style.cssText = ""
      return
    }
    const set = (box: { left: number; top?: number; bottom?: number; width?: number }) => {
      panel.style.left = `${box.left}px`
      panel.style.top = box.top == null ? "" : `${box.top}px`
      panel.style.bottom = box.bottom == null ? "" : `${box.bottom}px`
      if (box.width != null) panel.style.width = `${box.width}px`
    }
    const a = rectOf(anchor)
    if (a) {
      set({ left: a.left, top: a.bottom + 8, width: a.width })
      return
    }
    const r = triggerRef.current?.getBoundingClientRect()
    if (!r) return
    const width = panel.offsetWidth
    const left = align === "end" ? Math.max(8, r.right - width) : Math.min(r.left, window.innerWidth - width - 8)
    set(side === "top" ? { left, bottom: window.innerHeight - r.top + 6 } : { left, top: r.bottom + 6 })
  }, [align, side, anchor, narrow])

  React.useLayoutEffect(() => {
    if (!open) return
    place()
    if (!initialFocus) return
    const panel = panelRef.current
    // Skip the mobile sheet's close button when the body has a control.
    const body = panel?.querySelector<HTMLElement>("[data-popover-body]") ?? panel
    const first = body?.querySelector<HTMLElement>(
      "input, button, [tabindex]:not([tabindex='-1']), select, textarea",
    )
    first?.focus()
  }, [open, place, initialFocus])

  React.useEffect(() => {
    if (!open) return
    function onDown(e: PointerEvent) {
      const t = e.target as Node
      if (panelRef.current?.contains(t) || triggerRef.current?.contains(t)) return
      // Other controls that open this popover handle their own click.
      if (t instanceof Element && t.closest("[data-popover-keep]")) return
      setOpen(false)
    }
    window.addEventListener("pointerdown", onDown)
    window.addEventListener("resize", place)
    window.addEventListener("scroll", place, true)
    return () => {
      window.removeEventListener("pointerdown", onDown)
      window.removeEventListener("resize", place)
      window.removeEventListener("scroll", place, true)
    }
  }, [open, place, setOpen])

  return (
    <>
      {trigger({
        ref: triggerRef,
        id: triggerId,
        onClick: () => setOpen(!open),
        "aria-expanded": open,
        "aria-haspopup": "dialog",
        "aria-controls": open ? id : undefined,
      })}
      {open &&
        createPortal(
          <>
            {narrow && <div aria-hidden className="fixed inset-0 z-[60] bg-scrim" onClick={close} />}
            <div
              ref={panelRef}
              {...panelProps}
              id={id}
              role="dialog"
              aria-label={narrow ? undefined : label}
              aria-labelledby={narrow ? headerId : undefined}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation()
                  close()
                }
                // Enter inside a popover picks there; it never submits the run.
                if (e.key === "Enter") e.stopPropagation()
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  // Up/down walk the options (and the filter box above them).
                  const scope = panelRef.current?.querySelector<HTMLElement>("[data-popover-body]") ?? panelRef.current
                  const items = Array.from(
                    scope?.querySelectorAll<HTMLElement>("input, [role=checkbox], [role=radio], button") ?? [],
                  )
                  const at = items.indexOf(document.activeElement as HTMLElement)
                  if (items.length) {
                    e.preventDefault()
                    const step = e.key === "ArrowDown" ? 1 : -1
                    items[(at + step + items.length) % items.length]?.focus()
                  }
                }
              }}
              // Off-screen until placed (see `place`).
              style={narrow ? undefined : { left: -9999 }}
              className={cn(
                "z-[61] border border-border bg-popover text-popover-foreground shadow-lg outline-none",
                narrow
                  ? "fixed inset-x-0 bottom-0 flex max-h-[80vh] flex-col overflow-hidden rounded-t-2xl"
                  : "fixed w-72 max-h-[70vh] overflow-y-auto rounded-xl p-1.5",
                className,
              )}
            >
              {narrow && (
                <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
                  <span id={headerId} className="min-w-0 flex-1 truncate type-panel-title">
                    {label}
                  </span>
                  <button
                    type="button"
                    onClick={close}
                    aria-label="Close"
                    className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              )}
              {narrow ? (
                <div data-popover-body className="min-h-0 flex-1 overflow-y-auto p-3 pb-6">
                  {children(close)}
                </div>
              ) : (
                children(close)
              )}
            </div>
          </>,
          document.body,
        )}
    </>
  )
}

/** The anchor's box, read when placing (not during render). */
function rectOf(anchor: React.RefObject<HTMLElement | null> | undefined): DOMRect | undefined {
  return anchor?.current?.getBoundingClientRect()
}

function useNarrow(): boolean {
  const query = "(max-width: 639px)"
  const [narrow, setNarrow] = React.useState(() => typeof window !== "undefined" && window.matchMedia?.(query).matches)
  React.useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return
    const on = () => setNarrow(mq.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])
  return !!narrow
}

export function PopoverOption({
  selected,
  onSelect,
  children,
  hint,
  multi = true,
  active,
}: {
  selected: boolean
  onSelect: () => void
  children: React.ReactNode
  hint?: React.ReactNode
  multi?: boolean
  active?: boolean
}) {
  return (
    <button
      type="button"
      role={multi ? "checkbox" : "radio"}
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "flex w-full cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none",
        active && "bg-accent",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "mt-0.5 flex size-4 shrink-0 items-center justify-center border",
          multi ? "rounded-[4px]" : "rounded-full",
          selected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40",
        )}
      >
        {selected && <span className={cn("bg-current", multi ? "size-2 rounded-[1px]" : "size-1.5 rounded-full")} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block">{children}</span>
        {hint && <span className="mt-0.5 block type-caption">{hint}</span>}
      </span>
    </button>
  )
}
