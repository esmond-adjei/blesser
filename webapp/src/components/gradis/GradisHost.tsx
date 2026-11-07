import * as React from "react"
import { useMatch } from "react-router-dom"
import { Mascot } from "page-mascot"
import { useGradis } from "./GradisProvider"
import { GradisChat } from "./GradisChat"
import { useOpenTransition } from "../../lib/transition"
import { usePaneWidth } from "../../lib/paneWidth"
import { cn } from "../../lib/utils"

/** The mascot is the button; its own button is the only tab stop. */
function GradisButton() {
  const { mode, setMode } = useGradis()
  const t = useOpenTransition(mode === "closed", 150)
  if (!t.render) return null
  return (
    <button
      type="button"
      aria-label="Open Gradis"
      onClick={() => setMode("floating")}
      className={cn(
        "fixed bottom-5 right-5 z-50 cursor-pointer transition-all duration-150 motion-reduce:transition-none",
        t.shown ? "scale-100 opacity-100" : "scale-75 opacity-0",
      )}
    >
      <Mascot
        directions="/mascots/gradis-directions.webp"
        reactions="/mascots/gradis-reactions.webp"
        size={72}
        label="Gradis"
        className="drop-shadow-lg"
      />
    </button>
  )
}

const FLOAT_MIN_W = 300
const FLOAT_MAX_W = 640
const FLOAT_MIN_H = 400
const FLOAT_MAX_H = 800

function GradisFloating() {
  const { mode, setMode } = useGradis()
  const t = useOpenTransition(mode === "floating", 180)
  const { width, setWidth } = usePaneWidth(
    "graduator.gradis.float.width",
    400,
    FLOAT_MIN_W,
    FLOAT_MAX_W,
  )
  const { width: height, setWidth: setHeight } = usePaneWidth(
    "graduator.gradis.float.height",
    600,
    FLOAT_MIN_H,
    FLOAT_MAX_H,
  )
  const [resizing, setResizing] = React.useState(false)
  const startRef = React.useRef({ x: 0, y: 0, w: 0, h: 0 })

  function onResizeStart(e: React.PointerEvent<HTMLDivElement>) {
    startRef.current = { x: e.clientX, y: e.clientY, w: width, h: height }
    setResizing(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onResizeMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!resizing) return
    const dx = e.clientX - startRef.current.x
    const dy = e.clientY - startRef.current.y
    // The window is anchored bottom-right, so dragging the top-left grip
    // left widens it and dragging up grows it.
    setWidth(startRef.current.w - dx)
    setHeight(startRef.current.h - dy)
  }

  if (!t.render) return null
  return (
    <section
      aria-label="Gradis chat"
      style={{ width, height }}
      className={cn(
        "fixed bottom-5 right-5 z-50 flex max-h-[calc(100dvh-6rem)] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl transition-all duration-200 motion-reduce:transition-none",
        t.shown ? "translate-y-0 scale-100 opacity-100" : "translate-y-3 scale-95 opacity-0",
      )}
    >
      <GradisChat onMinimize={() => setMode("closed")} cornerGrip />
      {/* Top-left grip: the launcher button lives bottom-right, so the
          corner handle stays clear of it. */}
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize chat window"
        onPointerDown={onResizeStart}
        onPointerMove={onResizeMove}
        onPointerUp={() => setResizing(false)}
        onPointerCancel={() => setResizing(false)}
        className="absolute left-0 top-0 size-5 cursor-nwse-resize touch-none"
      >
        <span className="absolute left-1 top-1 h-3 w-3 rounded-tl-md border-l-2 border-t-2 border-muted-foreground/40" />
      </div>
    </section>
  )
}

const DOCK_DEFAULT = 400
const DOCK_MIN = 320
const DOCK_MAX = 640

function GradisDocked() {
  const { mode, setMode } = useGradis()
  const t = useOpenTransition(mode === "docked", 200)
  const { width, setWidth } = usePaneWidth(
    "graduator.gradis.width",
    DOCK_DEFAULT,
    DOCK_MIN,
    DOCK_MAX,
  )
  const [active, setActive] = React.useState(false)
  const dragging = React.useRef(false)
  const asideRef = React.useRef<HTMLElement | null>(null)

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragging.current = true
    setActive(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    // Same anchoring as DetailRail: measure from the rail's own right edge
    // so only the left edge moves.
    const right = asideRef.current?.getBoundingClientRect().right ?? window.innerWidth
    setWidth(right - e.clientX)
  }

  function endDrag() {
    dragging.current = false
    setActive(false)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 64 : 16
    if (e.key === "ArrowLeft") {
      e.preventDefault()
      setWidth(width + step)
    } else if (e.key === "ArrowRight") {
      e.preventDefault()
      setWidth(width - step)
    } else if (e.key === "Home") {
      e.preventDefault()
      setWidth(DOCK_MIN)
    } else if (e.key === "End") {
      e.preventDefault()
      setWidth(DOCK_MAX)
    }
  }

  if (!t.render) return null
  return (
    <>
      {t.render && (
        <div
          aria-hidden
          onClick={() => setMode("closed")}
          className={cn(
            "fixed inset-0 z-40 bg-scrim transition-opacity duration-200 motion-reduce:transition-none lg:hidden",
            t.shown ? "opacity-100" : "opacity-0",
          )}
        />
      )}
      <aside
        ref={asideRef}
        aria-label="Gradis panel"
        className={cn(
          "flex overflow-hidden bg-sidebar motion-reduce:transition-none",
          active ? "transition-none" : "transition-all duration-200",
          t.shown ? "opacity-100" : "opacity-0",
          "fixed inset-y-0 right-0 z-40 m-2 w-[92%] max-w-md rounded-xl border border-border shadow-2xl",
          "lg:static lg:z-auto lg:m-0 lg:h-auto lg:w-auto lg:max-w-[45vw] lg:flex-none lg:rounded-none lg:border-0 lg:border-l lg:shadow-none",
        )}
      >
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize Gradis panel"
          aria-valuemin={DOCK_MIN}
          aria-valuemax={DOCK_MAX}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerMove={onPointerMove}
          onDoubleClick={() => setWidth(DOCK_DEFAULT)}
          onKeyDown={onKeyDown}
          className="group hidden w-3 shrink-0 cursor-col-resize touch-none items-center justify-center focus:outline-none lg:flex"
        >
          <span
            className={cn(
              "h-10 w-1 rounded-full transition-colors",
              active ? "bg-ring" : "bg-border group-hover:bg-ring group-focus-visible:bg-ring",
            )}
          />
        </div>
        <div
          style={{ width: t.shown ? width : 0 }}
          className="flex h-full w-full min-w-0 max-w-full flex-1 flex-col overflow-hidden transition-all duration-200 motion-reduce:transition-none lg:w-auto lg:flex-none"
        >
          <GradisChat onMinimize={() => setMode("closed")} />
        </div>
      </aside>
    </>
  )
}

/** Mount once in the app shell; the chat page renders its own chat, so these stand down there. */
export function GradisHost() {
  const onChatPage = useMatch("/chat/*")
  if (onChatPage) return null
  return (
    <>
      <GradisButton />
      <GradisFloating />
      <GradisDocked />
    </>
  )
}
