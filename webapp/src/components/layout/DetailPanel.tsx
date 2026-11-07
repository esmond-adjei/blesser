/* eslint-disable react/only-export-components -- provider, hook, and rail ship together as one unit */
import * as React from "react"
import { ArrowLeft, PanelRight, Expand } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"
import { useOpenTransition } from "../../lib/transition"
import { fullPageFor, type PreviewRef } from "../../lib/previewRoutes"
import { routeScopedKey, usePaneWidth } from "../../lib/paneWidth"
import { cn } from "../../lib/utils"
import { EmptyState } from "../feedback/EmptyState"

type PanelOptions = {
  onClose?: () => void
  title?: string
  /** What is being previewed. Kinds with a full page get "Open as page". */
  ref?: PreviewRef
  /** Header overflow menu; pass the listing's row menu with variant="header". */
  actions?: React.ReactNode
  /** Keep the current view so the header can go back to it. */
  push?: boolean
}

type PanelState = {
  node: React.ReactNode
  title: string | null
  ref: PreviewRef | null
  actions: React.ReactNode
}

type DetailPanelContextValue = {
  setPanel: (node: React.ReactNode, opts?: PanelOptions) => void
  clearPanel: () => void
  requestClose: () => void
  panel: React.ReactNode
  title: string | null
  previewRef: PreviewRef | null
  actions: React.ReactNode
  railVisible: boolean
  setRailVisible: (visible: boolean) => void
  canGoBack: boolean
  goBack: () => void
}

const DetailPanelContext = React.createContext<DetailPanelContextValue | null>(null)
const InRailContext = React.createContext(false)

/** True inside the rail's content, where opening a record stacks on the current view. */
export function useInDetailRail() {
  return React.useContext(InRailContext)
}

/** Shown when the rail is open with nothing selected, so the toggle always reveals something. */
export function DetailPanelEmptyState() {
    return (
      <EmptyState
        mascot="search-empty"
        title="Nothing to show"
        description="Select an item to preview it here."
      />
    )
  }

/** Pages publish a panel node; the shell renders it as a resizable right rail (drawer on mobile). */
export function DetailPanelProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<PanelState | null>(null)
  const [railVisible, setRailVisible] = React.useState(false)
  const onCloseRef = React.useRef<(() => void) | undefined>(undefined)
  const stateRef = React.useRef<PanelState | null>(null)
  stateRef.current = state
  type Entry = { state: PanelState; onClose?: () => void }
  const historyRef = React.useRef<Entry[]>([])
  const [canGoBack, setCanGoBack] = React.useState(false)
  const setHistory = React.useCallback((h: Entry[]) => {
    historyRef.current = h
    setCanGoBack(h.length > 0)
  }, [])

  const setPanel = React.useCallback((node: React.ReactNode, opts?: PanelOptions) => {
    const next: PanelState = {
      node: node || <DetailPanelEmptyState key="empty" />,
      title: opts?.title ?? "Empty",
      ref: opts?.ref ?? null,
      actions: opts?.actions ?? null,
    }
    const history = historyRef.current
    const base = history[0]?.state.ref
    // A page re-publishing the record the stack started from refreshes it in place.
    if (!opts?.push && base && opts?.ref && base.kind === opts.ref.kind && base.id === opts.ref.id) {
      setHistory([{ state: next, onClose: opts.onClose }, ...history.slice(1)])
      return
    }
    const current = stateRef.current
    setHistory(opts?.push && current ? [...history, { state: current, onClose: onCloseRef.current }] : [])
    onCloseRef.current = opts?.onClose
    setState(next)
    setRailVisible(true)
  }, [setHistory])

  const goBack = React.useCallback(() => {
    const prev = historyRef.current.at(-1)
    if (!prev) return
    setHistory(historyRef.current.slice(0, -1))
    onCloseRef.current = prev.onClose
    setState(prev.state)
  }, [setHistory])

  const clearPanel = React.useCallback(() => {
    setHistory([])
    onCloseRef.current = undefined
    setRailVisible(false)
    setState(null)
  }, [setHistory])

  const requestClose = React.useCallback(() => {
    // The page's handler lives on the view the stack started from.
    const onClose = historyRef.current[0]?.onClose ?? onCloseRef.current
    setHistory([])
    onClose?.()
    onCloseRef.current = undefined
    setState(null)
    setRailVisible(false)
  }, [setHistory])

  const value = React.useMemo(
    () => ({
      setPanel,
      clearPanel,
      requestClose,
      panel: state?.node ?? null,
      title: state?.title ?? null,
      previewRef: state?.ref ?? null,
      actions: state?.actions ?? null,
      railVisible,
      setRailVisible,
      canGoBack,
      goBack,
    }),
    [setPanel, clearPanel, requestClose, state, railVisible, canGoBack, goBack],
  )
  return <DetailPanelContext.Provider value={value}>{children}</DetailPanelContext.Provider>
}

/** Null where no detail rail exists (the standalone CV page), so callers degrade to plain links. */
export function useDetailPanelOptional() {
  return React.useContext(DetailPanelContext)
}

export function useDetailPanel() {
  const ctx = React.useContext(DetailPanelContext)
  if (!ctx) throw new Error("useDetailPanel must be used inside DetailPanelProvider")
  return ctx
}

export function DetailPanelToggle({ onClick }: { onClick?: () => void }) {
  const { setRailVisible, railVisible } = useDetailPanel()
  const label = railVisible ? "Hide detail panel" : "Show detail panel"
  return (
      <button
        type="button"
        onClick={onClick ?? (() => setRailVisible(!railVisible))}
        data-tooltip={label}
        aria-label={label}
        aria-pressed={railVisible}
        className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <PanelRight className="size-4" />
      </button>
  )
}

const RAIL_MIN = 360
/** Share of its row past which the rail floats over the page instead of
 * squeezing it: a run view under ~30% wide breaks its tabs. */
const LAYER_AT = 0.7
/** Resize-handle width (w-3). Lives outside the content box. */
const RAIL_HANDLE_W = 12
/** Horizontal card margins on desktop (m-2 on both sides). */
const RAIL_CARD_MARGIN_X = 16

/** Width of the row the rail docks into (its parent), kept current. */
function useRowWidth(el: React.RefObject<HTMLElement | null>, active: boolean) {
  const [w, setW] = React.useState<number | null>(null)
  React.useEffect(() => {
    const row = el.current?.parentElement
    if (!active || !row) return
    const observer = new ResizeObserver(([entry]) => setW(entry.contentRect.width))
    observer.observe(row)
    return () => observer.disconnect()
  }, [el, active])
  return w
}

function useViewportWidth() {
  const [w, setW] = React.useState(() =>
    typeof window === "undefined" ? 1280 : window.innerWidth,
  )
  React.useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])
  return w
}

export function DetailRail() {
  const { panel, title, previewRef, actions, requestClose, railVisible, canGoBack, goBack } = useDetailPanel()
  const navigate = useNavigate()
  // Default ~half the shell, max 90%. Stored per route: a run view's width isn't the outbox's.
  const viewportW = useViewportWidth()
  const railMax = Math.max(RAIL_MIN + 1, Math.floor(viewportW * 0.9))
  const railDefault = Math.max(RAIL_MIN, Math.min(Math.round(viewportW * 0.4), railMax))
  const { pathname } = useLocation()
  const { width, setWidth } = usePaneWidth(
    routeScopedKey("graduator.detailRail.width.v2", pathname),
    railDefault,
    RAIL_MIN,
    railMax,
  )
  // Keep a stored width inside the new max when the viewport shrinks.
  React.useEffect(() => {
    if (width > railMax) setWidth(railMax)
  }, [width, railMax, setWidth])
  const dragging = React.useRef(false)
  const asideRef = React.useRef<HTMLElement | null>(null)
  const [active, setActive] = React.useState(false)

  // Same open/close choreography as the sidebar: stay mounted through the
  // exit so width and opacity animate. Visibility and content both feed it.
  const open = !!panel && railVisible
  const t = useOpenTransition(open, 200)
  // Retain the last panel through the exit so the animation plays over content.
  type Shown = { node: React.ReactNode; title: string | null; ref: PreviewRef | null; actions: React.ReactNode }
  const [stale, setStale] = React.useState<Shown | null>(null)
  React.useEffect(() => {
    if (panel) setStale({ node: panel, title, ref: previewRef, actions })
  }, [panel, title, previewRef, actions])
  // Gate on t.render, not just `panel`: the toggle keeps the panel node
  // around, and a mounted aside would keep catching clicks and scrolls.
  const shown: Shown | null = t.render
    ? panel
      ? { node: panel, title, ref: previewRef, actions }
      : stale
    : null
  const fullPage = fullPageFor(shown?.ref)
  const rowW = useRowWidth(asideRef, !!shown)
  // Floating, not docked, once the rail would leave the page too little room.
  const layered = rowW != null && width + RAIL_HANDLE_W + RAIL_CARD_MARGIN_X >= rowW * LAYER_AT

  if (!shown) return null

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragging.current = true
    setActive(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    // Anchor to the rail's own right edge so only the left rail moves.
    // window.innerWidth drifts when the rail isn't flush (flex layout, borders).
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
      setWidth(RAIL_MIN)
    } else if (e.key === "End") {
      e.preventDefault()
      setWidth(railMax)
    }
  }

  return (
    <>
      {t.render && (
        <div
          aria-hidden
          onClick={requestClose}
          className={cn(
            "fixed inset-0 z-40 bg-scrim transition-opacity duration-200 motion-reduce:transition-none lg:hidden",
            t.shown ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        />
      )}
      <aside
        ref={asideRef}
        data-context-source
        style={
          {
            "--rail-w": `${t.shown ? width + RAIL_HANDLE_W + RAIL_CARD_MARGIN_X : 0}px`,
            "--rail-content-w": `${width}px`,
          } as React.CSSProperties
        }
        className={cn(
          "flex overflow-hidden motion-reduce:transition-none",
          active ? "transition-none" : "transition-all duration-200",
          // Never intercept input while hidden or mid-exit.
          t.shown ? "opacity-100" : "pointer-events-none opacity-0",
          "fixed inset-y-0 right-0 z-40 m-2 w-[92%] max-w-[480px] rounded-xl lg:m-0 lg:w-(--rail-w) lg:shrink-0",
          layered ? "lg:fixed lg:z-40 lg:max-w-[92vw]" : "lg:static lg:z-auto lg:max-w-[80vw]",
        )}
      >
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize detail panel"
          aria-valuemin={RAIL_MIN}
          aria-valuemax={railMax}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onKeyDown}
          onDoubleClick={() => setWidth(railDefault)}
          className="group hidden w-3 shrink-0 cursor-col-resize touch-none items-center justify-center focus:outline-none lg:flex"
        >
          <span
            className={cn(
              "h-10 w-1 rounded-full transition-colors",
              active ? "bg-ring" : "bg-border group-hover:bg-ring group-focus-visible:bg-ring",
            )}
          />
        </div>
        <div className="flex h-full w-full min-w-0 flex-1 flex-col border border-separator bg-(--app-detail) lg:my-2 lg:h-auto lg:w-(--rail-content-w) lg:flex-none lg:rounded-lg">
            <div className={cn("z-10 flex h-12 flex-none shrink-0 items-center gap-1 border-b border-sidebar-border pr-3", fullPage || canGoBack ? "pl-2" : "pl-4")}>
              {canGoBack && (
                <button
                  type="button"
                  onClick={goBack}
                  data-tooltip="Back"
                  aria-label="Back"
                  className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <ArrowLeft className="size-4" />
                </button>
              )}
              <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                {shown.title ?? "Details"}
              </span>

              {shown.actions}
              <DetailPanelToggle />
              {/* Hidden, not disabled, when the kind has no full page. */}
              {fullPage && (
                <button
                  type="button"
                  onClick={() => navigate(fullPage)}
                  data-tooltip="Open as page"
                  aria-label="Open as page"
                  className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Expand className="size-4" />
                </button>
              )}
            </div>
            <div className="nice-scroll min-h-0 min-w-0 flex-1 overflow-y-auto p-4 lg:p-6">
              <div className="h-fit w-full pb-10 text-sm">
                <InRailContext.Provider value>{shown.node}</InRailContext.Provider>
              </div>
            </div>
        </div>
      </aside>
    </>
  )
}
