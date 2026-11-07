import * as React from "react"
import { createPortal } from "react-dom"

const TRIGGERS = "[data-tooltip]"
const OPEN_DELAY = 450
const CLOSE_DELAY = 120

function tooltipText(element: HTMLElement) {
  return element.getAttribute("data-tooltip") ?? ""
}

/** One tooltip layer for native controls, menu triggers and portalled dialogs.
 * Use data-tooltip when a control needs an explanation beyond its label. */
export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const id = React.useId()
  const [active, setActive] = React.useState<{ element: HTMLElement; text: string } | null>(null)
  const tipRef = React.useRef<HTMLDivElement>(null)
  const dismissRef = React.useRef<() => void>(() => {})
  const [position, setPosition] = React.useState<{ left: number; top: number; side: "top" | "bottom"; arrowLeft: number } | null>(null)

  React.useEffect(() => {
    let trigger: HTMLElement | null = null
    let touchInteraction = false
    let openTimer: ReturnType<typeof setTimeout> | undefined
    let closeTimer: ReturnType<typeof setTimeout> | undefined
    const cancelClose = () => clearTimeout(closeTimer)
    const cancelTimers = () => { clearTimeout(openTimer); cancelClose() }
    const close = () => {
      cancelTimers()
      trigger = null
      setActive(null)
    }
    dismissRef.current = close
    const scheduleClose = () => {
      clearTimeout(openTimer)
      cancelClose()
      closeTimer = setTimeout(close, CLOSE_DELAY)
    }
    const open = (element: HTMLElement, immediate: boolean) => {
      cancelClose()
      if (trigger === element && !immediate) return
      close()
      const text = tooltipText(element)
      if (!text || element.getAttribute("aria-expanded") === "true") return
      trigger = element
      openTimer = setTimeout(() => {
        if (element.isConnected) {
          setPosition(null)
          setActive({ element, text: tooltipText(element) })
        }
      }, immediate ? 0 : OPEN_DELAY)
    }
    const findTrigger = (target: EventTarget | null) =>
      target instanceof Element ? target.closest<HTMLElement>(TRIGGERS) : null
    const over = (event: PointerEvent) => {
      if (event.pointerType === "touch") return
      if (event.target instanceof Node && tipRef.current?.contains(event.target)) {
        cancelClose()
        return
      }
      const element = findTrigger(event.target)
      if (element) open(element, false)
    }
    const out = (event: PointerEvent) => {
      if (event.relatedTarget instanceof Node &&
        (trigger?.contains(event.relatedTarget) || tipRef.current?.contains(event.relatedTarget))) return
      if (trigger !== document.activeElement) scheduleClose()
    }
    const focus = (event: FocusEvent) => {
      if (touchInteraction) return
      const element = findTrigger(event.target)
      if (element) open(element, true)
    }
    const blur = () => close()
    const key = (event: KeyboardEvent) => {
      touchInteraction = false
      if (event.key === "Escape") close()
    }
    const down = (event: PointerEvent) => {
      touchInteraction = event.pointerType === "touch"
      close()
    }
    const scroll = (event: Event) => {
      if (event.target instanceof Node && tipRef.current?.contains(event.target)) return
      close()
    }
    document.addEventListener("pointerover", over)
    document.addEventListener("pointerout", out)
    document.addEventListener("focusin", focus)
    document.addEventListener("focusout", blur)
    document.addEventListener("pointerdown", down, true)
    document.addEventListener("click", close, true)
    document.addEventListener("keydown", key)
    document.addEventListener("scroll", scroll, true)
    window.addEventListener("resize", close)
    return () => {
      cancelTimers()
      document.removeEventListener("pointerover", over)
      document.removeEventListener("pointerout", out)
      document.removeEventListener("focusin", focus)
      document.removeEventListener("focusout", blur)
      document.removeEventListener("pointerdown", down, true)
      document.removeEventListener("click", close, true)
      document.removeEventListener("keydown", key)
      document.removeEventListener("scroll", scroll, true)
      window.removeEventListener("resize", close)
    }
  }, [])

  React.useLayoutEffect(() => {
    if (!active || !tipRef.current) return
    const { element } = active
    const anchor = element.getBoundingClientRect()
    const tip = tipRef.current.getBoundingClientRect()
    const gap = 10
    const side = anchor.top >= tip.height + gap * 2 ? "top" : "bottom"
    const center = anchor.left + anchor.width / 2
    const left = Math.max(gap, Math.min(center - tip.width / 2, window.innerWidth - tip.width - gap))
    setPosition({
      left,
      arrowLeft: Math.max(12, Math.min(center - left, tip.width - 12)),
      top: Math.max(gap, Math.min(side === "top" ? anchor.top - tip.height - gap : anchor.bottom + gap, window.innerHeight - tip.height - gap)),
      side,
    })
    const descriptions = (element.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean)
    element.setAttribute("aria-describedby", [...descriptions, id].join(" "))
    const observer = new MutationObserver(() => {
      if (!element.isConnected || tooltipText(element) !== active.text || element.getAttribute("aria-expanded") === "true") dismissRef.current()
    })
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-tooltip", "aria-label", "aria-expanded"] })
    return () => {
      observer.disconnect()
      const remaining = (element.getAttribute("aria-describedby") ?? "").split(/\s+/).filter((value) => value && value !== id)
      if (remaining.length) element.setAttribute("aria-describedby", remaining.join(" "))
      else element.removeAttribute("aria-describedby")
    }
  }, [active, id])

  return <>{children}{active && createPortal(
    <div
      ref={tipRef}
      id={id}
      role="tooltip"
      data-side={position?.side}
      className="app-tooltip"
      style={{ left: position?.left ?? 0, top: position?.top ?? 0, visibility: position ? "visible" : "hidden" }}
    >
      <span className="app-tooltip-content text-left">{active.text}</span>
      <span aria-hidden="true" className="app-tooltip-arrow" style={{ left: position?.arrowLeft ?? 0 }} />
    </div>,
    document.body,
  )}</>
}
