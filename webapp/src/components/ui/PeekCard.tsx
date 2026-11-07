import * as React from "react"
import { createPortal } from "react-dom"

const CARD_W = 320
const CARD_MAX_H = 440
const GAP = 12

/** A preview card level with the `data-active` row in `list`. Portalled:
 * the dialog's transform would trap a fixed child. */
export function PeekCard({
  id,
  list,
  label,
  onEnter,
  onLeave,
  children,
}: {
  id: string
  list: React.RefObject<HTMLElement | null>
  label: string
  onEnter: () => void
  onLeave: () => void
  children: React.ReactNode
}) {
  const [pos, setPos] = React.useState<{ left: number; top: number } | null>(null)
  const card = React.useRef<HTMLDivElement>(null)
  // Re-run once drawn, to measure the card.
  const drawn = pos !== null
  React.useLayoutEffect(() => {
    const el = list.current
    if (!el) return
    const place = () => {
      const row = el.querySelector('[data-active="true"]')
      const dialog = el.closest('[role="dialog"]')
      if (!row || !dialog) return setPos(null)
      const rowBox = row.getBoundingClientRect()
      let left = dialog.getBoundingClientRect().right + GAP
      if (left + CARD_W + GAP > window.innerWidth) left = rowBox.left - GAP - CARD_W
      if (left < GAP) return setPos(null)
      const height = card.current?.offsetHeight || CARD_MAX_H
      const top = Math.min(rowBox.top - 16, window.innerHeight - height - GAP)
      setPos({ left, top: Math.max(GAP, top) })
    }
    place()
    window.addEventListener("scroll", place, { capture: true, passive: true })
    window.addEventListener("resize", place)
    const ro = new ResizeObserver(place)
    if (card.current) ro.observe(card.current)
    return () => {
      ro.disconnect()
      window.removeEventListener("scroll", place, { capture: true })
      window.removeEventListener("resize", place)
    }
  }, [id, list, drawn])
  if (!pos) return null
  return createPortal(
    <div
      ref={card}
      role="region"
      aria-label={`Preview of ${label}`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      className="pointer-events-auto fixed z-[60] overflow-hidden rounded-xl bg-surface-raised shadow ring-1 ring-separator transition-[top,box-shadow] duration-150 hover:shadow-lg hover:ring-control-border motion-reduce:transition-none"
      style={{ left: pos.left, top: pos.top, width: CARD_W, maxHeight: CARD_MAX_H }}
    >
      <div className="max-h-[inherit] overflow-hidden p-4 pb-6 text-sm [mask-image:linear-gradient(to_bottom,#000_calc(100%-2rem),transparent)]">
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function PeekSummary({
  icon: Icon,
  title,
  meta,
  text,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  meta?: string | null
  text?: string | null
}) {
  return (
    <div className="flex flex-col items-start gap-2">
      <span className="g-icon-tile size-10 rounded-md"><Icon className="size-5" /></span>
      <h2 className="text-[17px] font-semibold leading-snug">{title}</h2>
      {meta && <p className="type-meta">{meta}</p>}
      {text && <p className="line-clamp-6 text-sm leading-relaxed text-label-secondary">{text}</p>}
    </div>
  )
}
