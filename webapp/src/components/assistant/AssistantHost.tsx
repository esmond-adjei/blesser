import { useCallback, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Maximize2, PanelRight, PictureInPicture2, X } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import { useIsMobile } from "../../hooks/use-mobile"
import { assistantHref } from "../../lib/assistant"
import { useAuth } from "../../lib/auth"
import { usePaneSize } from "../../lib/paneSize"
import { useOpenTransition } from "../../lib/useOpenTransition"
import { AssistantChat } from "./AssistantChat"
import { DockContext, useDock, useOpenAssistant, type Layout, type Mode } from "./dockContext"
import { SunMascot } from "./SunMascot"

const LAYOUT_KEY = "blesser.assistant.layout"
const MODE_KEY = "blesser.assistant.mode"
function readMode(): Mode {
  try {
    const saved = localStorage.getItem(MODE_KEY)
    return saved === "dock" || saved === "panel" ? saved : "closed"
  } catch {
    return "closed"
  }
}
function saveMode(mode: Mode) {
  try { localStorage.setItem(MODE_KEY, mode) } catch { /* the window reopens closed */ }
}
function readLayout(): Layout {
  try {
    return localStorage.getItem(LAYOUT_KEY) === "panel" ? "panel" : "dock"
  } catch {
    return "dock"
  }
}

/** Holds the Assistant's window state for the whole app shell. */
export function AssistantDockProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const chatKey = `blesser.assistant.chat.${user?.id ?? ""}`
  const [layout, setLayoutState] = useState<Layout>(readLayout)
  const [mode, setModeState] = useState<Mode>(readMode)
  const [chatId, setChatIdState] = useState<string | undefined>(() => {
    try { return localStorage.getItem(chatKey) ?? undefined } catch { return undefined }
  })
  const setLayout = useCallback((next: Layout) => {
    setLayoutState(next)
    setModeState((current) => {
      if (current === "closed") return current
      saveMode(next)
      return next
    })
    try { localStorage.setItem(LAYOUT_KEY, next) } catch { /* the choice resets on reload */ }
  }, [])
  const setMode = useCallback((next: Mode) => {
    setModeState(next)
    saveMode(next)
    if (next !== "closed") setLayoutState(next)
  }, [])
  const setChatId = useCallback((id?: string) => {
    setChatIdState(id)
    try {
      if (id) localStorage.setItem(chatKey, id)
      else localStorage.removeItem(chatKey)
    } catch { /* the chat is simply not remembered */ }
  }, [chatKey])
  const value = useMemo(() => ({ mode, layout, chatId, setMode, setLayout, setChatId }), [mode, layout, chatId, setMode, setLayout, setChatId])
  return <DockContext.Provider value={value}>{children}</DockContext.Provider>
}

function useOnAssistantPage() {
  const { pathname } = useLocation()
  return pathname === "/assistant" || pathname.startsWith("/assistant/")
}

function WindowActions() {
  const { mode, chatId, setMode, setLayout } = useDock()
  const navigate = useNavigate()
  const floating = mode === "dock"
  return (
    <>
      <Button
        size="sm"
        variant="quiet"
        iconOnly
        aria-label={floating ? "Show as side panel" : "Show as floating window"}
        icon={floating ? <PanelRight /> : <PictureInPicture2 />}
        onClick={() => setLayout(floating ? "panel" : "dock")}
      />
      <Button
        size="sm"
        variant="quiet"
        iconOnly
        aria-label="Open full page"
        icon={<Maximize2 />}
        onClick={() => { setMode("closed"); navigate(chatId ? assistantHref(chatId) : "/assistant") }}
      />
      <Button size="sm" variant="quiet" iconOnly aria-label="Close the Assistant" icon={<X />} onClick={() => setMode("closed")} />
    </>
  )
}

function EmbeddedChat() {
  const { user } = useAuth()
  const { chatId, setChatId } = useDock()
  return <AssistantChat key={user?.id} userId={user?.id ?? ""} chatId={chatId} onChatChange={setChatId} variant="embedded" actions={<WindowActions />} />
}

/** The sun, bottom right: click to open in the last layout, or pick a layout from the buttons beside it. */
export function AssistantMascot() {
  const { mode, setMode } = useDock()
  const open = useOpenAssistant()
  const onPage = useOnAssistantPage()
  const { pathname } = useLocation()
  const t = useOpenTransition(mode === "closed" && !onPage, 150)
  if (!t.render) return null
  const pick = "grid size-8 cursor-pointer place-items-center rounded-full border border-separator bg-surface text-ink-secondary shadow-elevation-2 transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
  return (
    <div
      className={cn(
        "group fixed right-4 z-50 transition-all duration-150 motion-reduce:transition-none sm:right-5",
        pathname.startsWith("/scans") ? "bottom-28 sm:bottom-5" : "bottom-4 sm:bottom-5",
        t.shown ? "scale-100 opacity-100" : "scale-75 opacity-0",
      )}
    >
      <div className="absolute right-0 bottom-full hidden items-center gap-1.5 pb-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 sm:flex">
        <button type="button" aria-label="Open as a floating window" title="Floating window" onClick={() => setMode("dock")} className={pick}><PictureInPicture2 className="size-4" aria-hidden="true" /></button>
        <button type="button" aria-label="Open as a side panel" title="Side panel" onClick={() => setMode("panel")} className={pick}><PanelRight className="size-4" aria-hidden="true" /></button>
      </div>
      <button
        type="button"
        aria-label="Ask the Assistant"
        onClick={open}
        className="grid h-8 w-16 cursor-pointer place-items-end rounded-t-full transition-transform duration-150 hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <SunMascot size={64} className="drop-shadow-md" />
      </button>
    </div>
  )
}

const DOCK = { w: [340, 640, 400], h: [420, 820, 600] } as const

/** The floating window, anchored bottom right and resized from its top left corner. */
export function AssistantDock() {
  const { mode } = useDock()
  const onPage = useOnAssistantPage()
  const t = useOpenTransition(mode === "dock" && !onPage, 180)
  const [width, setWidth] = usePaneSize("blesser.assistant.dock.width", DOCK.w[2], DOCK.w[0], DOCK.w[1])
  const [height, setHeight] = usePaneSize("blesser.assistant.dock.height", DOCK.h[2], DOCK.h[0], DOCK.h[1])
  const start = useRef<{ x: number; y: number; w: number; h: number } | null>(null)
  if (!t.render) return null
  const down = (event: ReactPointerEvent<HTMLDivElement>) => {
    start.current = { x: event.clientX, y: event.clientY, w: width, h: height }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const move = (event: ReactPointerEvent<HTMLDivElement>) => {
    const from = start.current
    if (!from) return
    setWidth(from.w - (event.clientX - from.x))
    setHeight(from.h - (event.clientY - from.y))
  }
  return (
    <section
      aria-label="Assistant"
      style={{ "--dock-w": `${width}px`, "--dock-h": `${height}px` } as CSSProperties}
      className={cn(
        "fixed z-50 flex flex-col overflow-hidden border border-separator bg-surface shadow-elevation-3 transition-all duration-200 motion-reduce:transition-none",
        "max-sm:inset-0 sm:right-5 sm:bottom-5 sm:h-[min(var(--dock-h),calc(100dvh-6rem))] sm:w-[min(var(--dock-w),calc(100vw-2.5rem))] sm:rounded-xl",
        t.shown ? "translate-y-0 scale-100 opacity-100" : "translate-y-3 scale-95 opacity-0",
      )}
    >
      <EmbeddedChat />
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize the Assistant window"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={() => { start.current = null }}
        onPointerCancel={() => { start.current = null }}
        className="absolute top-0 left-0 hidden size-5 cursor-nwse-resize touch-none sm:block"
      />
    </section>
  )
}

const PANEL = [340, 720, 420] as const

/** The Assistant as a column beside the page, resized from its left edge. */
export function AssistantPanel() {
  const { mode } = useDock()
  const onPage = useOnAssistantPage()
  const phone = useIsMobile()
  const t = useOpenTransition(mode === "panel" && !onPage, 200)
  const [width, setWidth] = usePaneSize("blesser.assistant.panel.width", PANEL[2], PANEL[0], PANEL[1])
  const [active, setActive] = useState(false)
  const aside = useRef<HTMLElement>(null)
  if (!t.render) return null
  const move = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!active) return
    const right = aside.current?.getBoundingClientRect().right ?? window.innerWidth
    setWidth(right - event.clientX)
  }
  const nudge = (event: React.KeyboardEvent) => {
    const step = event.shiftKey ? 64 : 16
    if (event.key === "ArrowLeft") setWidth(width + step)
    else if (event.key === "ArrowRight") setWidth(width - step)
    else return
    event.preventDefault()
  }
  return (
    <aside
      ref={aside}
      aria-label="Assistant"
      style={phone ? undefined : { width: t.shown ? width : 0 }}
      className={cn(
        "relative flex min-h-0 shrink-0 overflow-hidden border-separator bg-canvas motion-reduce:transition-none",
        active ? "transition-none" : "transition-[width,opacity] duration-200",
        phone ? "fixed inset-0 z-50" : "border-l",
        t.shown ? "opacity-100" : "opacity-0",
      )}
    >
      {phone ? null : (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize the Assistant panel"
          aria-valuemin={PANEL[0]}
          aria-valuemax={PANEL[1]}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={(event) => { setActive(true); event.currentTarget.setPointerCapture(event.pointerId) }}
          onPointerMove={move}
          onPointerUp={() => setActive(false)}
          onPointerCancel={() => setActive(false)}
          onDoubleClick={() => setWidth(PANEL[2])}
          onKeyDown={nudge}
          className="group absolute inset-y-0 left-0 z-10 flex w-2 -translate-x-1 cursor-col-resize touch-none items-center justify-center focus:outline-none"
        >
          <span className={cn("h-10 w-0.5 rounded-full transition-colors", active ? "bg-focus" : "bg-transparent group-hover:bg-separator group-focus-visible:bg-focus")} />
        </div>
      )}
      <div style={phone ? undefined : { width }} className="flex min-h-0 min-w-0 flex-1 flex-col">
        <EmbeddedChat />
      </div>
    </aside>
  )
}
