import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription } from "../components/ui/alert-dialog"
import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowUp,
  ArrowUpRight,
  Check,
  CircleAlert,
  CircleDashed,
  Database,
  GripVertical,
  Globe,
  LayoutGrid,
  Loader2,
  PanelRightOpen,
  Radar,
  Plus,
  Square,
  Trash2,
  X,
} from "lucide-react"
import * as api from "../lib/api"
import { formatAgo } from "../lib/format"
import { CATEGORIES, CATEGORY_LABELS, useTrackedOpportunities, useTrackOpportunity } from "../lib/opportunities"
import {
  clock,
  describeEvent,
  elapsedMs,
  formatDuration,
  scanElapsedMs,
  type LogLine,
} from "../lib/scanLog"
import { toastError, toastSuccess } from "../lib/toast"
import { LINEAR_OK, springEasing } from "../lib/motion"
import type { OpportunityCategory, Scan, ScanFind, ScanTask } from "../lib/types"
import { Button, Chip, Countdown, OpportunityArt, buttonVariants, cn, daysUntil } from "@blesser/ui"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { ErrorState } from "../components/feedback/EmptyState"
import { PageHeader } from "../components/layout/PageHeader"
import { useShellHeader } from "../components/layout/shellHeader"
import { CountrySelect } from "../components/ui/country-select"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"

type Status = ScanTask["status"] | Scan["status"]

const STATUS: Record<Status, { label: string; tone: "neutral" | "sun" | "forest" | "caution" }> = {
  running: { label: "Running", tone: "sun" },
  pending: { label: "Queued", tone: "neutral" },
  done: { label: "Finished", tone: "forest" },
  error: { label: "Stopped early", tone: "caution" },
  cancelled: { label: "Stopped", tone: "neutral" },
}

const PANEL = "flex min-w-0 flex-col gap-4 rounded-lg border border-separator bg-surface p-5 shadow-elevation-1"

function audiences(scan: Scan): string {
  return scan.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")
}

function scanTitle(scan: Scan): string {
  return scan.region ? `${audiences(scan)} in ${scan.region}` : audiences(scan)
}

// Early scans stored the agents' default instruction as their focus; it isn't something the member typed.
function scanFocus(scan: Scan): string {
  const focus = scan.focus.trim()
  return focus.startsWith("Find open opportunities eligible") ? "" : focus
}

function useTick(active: boolean, ms = 15_000) {
  const [, setTick] = React.useState(0)
  React.useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setTick((n) => n + 1), ms)
    return () => window.clearInterval(t)
  }, [active, ms])
}

function useAllowance() {
  return useQuery({ queryKey: ["scans", "allowance"], queryFn: api.scanAllowance, staleTime: 30_000 })
}

function AllowanceNote() {
  const allowance = useAllowance()
  const a = allowance.data
  if (!a?.enabled) return null
  const left = Math.min(a.left_this_hour, a.left_today)
  const text = a.left_today === 0 ? "No scans left today" : left === 0 ? "No scans left this hour" : `You have ${a.left_this_hour} / ${a.per_hour} scans left for this hour`
  return <span className="text-footnote text-ink-secondary tabular-nums">{text}</span>
}

const CARD_W = 300
const CARD_H = 172
const GAP = 24
const LAYOUT_KEY = "blesser.scan-canvas"
type Pos = { x: number; y: number }

function loadLayout(): Record<string, Pos> {
  try {
    return JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? "{}") as Record<string, Pos>
  } catch {
    return {}
  }
}

function saveLayout(layout: Record<string, Pos>) {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout))
  } catch {
    // Layout is a per-browser convenience; losing it only resets positions.
  }
}

function freeSlot(taken: Pos[], width: number): Pos {
  const cols = Math.max(1, Math.floor((width - GAP) / (CARD_W + GAP)))
  for (let k = 0; ; k++) {
    const slot = { x: GAP + (k % cols) * (CARD_W + GAP), y: GAP + Math.floor(k / cols) * (CARD_H + GAP) }
    if (!taken.some((p) => Math.abs(p.x - slot.x) < CARD_W && Math.abs(p.y - slot.y) < CARD_H)) return slot
  }
}

export function Scans() {
  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "running") ? 10_000 : 60_000),
  })
  const viewport = React.useRef<HTMLDivElement>(null)
  const [layout, setLayout] = React.useState(loadLayout)
  const [offset, setOffset] = React.useState<Pos>({ x: 0, y: 0 })
  const [front, setFront] = React.useState<string | null>(null)
  const [fresh, setFresh] = React.useState<string | null>(null)
  const [expanded, setExpanded] = React.useState<{ id: string; from: DOMRect } | null>(null)
  const closeMorph = React.useRef<(() => Promise<void>) | null>(null)
  const collapse = () => closeMorph.current?.() ?? Promise.resolve()
  useTick(!!scans.data?.some((s) => s.status === "running"))

  // Oldest first, so a new scan takes the next free spot without moving older cards.
  React.useEffect(() => {
    if (!scans.data) return
    const missing = [...scans.data].reverse().filter((s) => !layout[s.id])
    if (!missing.length) return
    const width = viewport.current?.clientWidth ?? 1200
    const next = { ...layout }
    for (const s of missing) next[s.id] = freeSlot(Object.values(next), width)
    setLayout(next)
    saveLayout(next)
  }, [scans.data, layout])

  const move = React.useCallback((id: string, pos: Pos, commit: boolean) => {
    setLayout((prev) => {
      const next = { ...prev, [id]: { x: Math.max(0, pos.x), y: Math.max(0, pos.y) } }
      if (commit) saveLayout(next)
      return next
    })
  }, [])

  const arrange = React.useCallback(() => {
    saveLayout({})
    setLayout({})
    setOffset({ x: 0, y: 0 })
  }, [])

  const header = React.useMemo(() => ({
    title: "Scans",
    actions: (
      <div className="flex items-center gap-3">
        <AllowanceNote />
        <Button size="sm" variant="quiet" icon={<LayoutGrid />} onClick={arrange}>Auto Arrange</Button>
      </div>
    ),
  }), [arrange])
  useShellHeader(header)

  const onStarted = (scan: Scan) => {
    setFresh(scan.id)
    setFront(scan.id)
    setOffset({ x: 0, y: 0 })
  }

  const pan = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || e.button !== 0) return
    if (expanded) return void collapse()
    const start = { x: e.clientX - offset.x, y: e.clientY - offset.y }
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    el.dataset.panning = "true"
    const onMove = (ev: PointerEvent) => setOffset({ x: Math.min(0, ev.clientX - start.x), y: Math.min(0, ev.clientY - start.y) })
    const onUp = () => {
      delete el.dataset.panning
      el.removeEventListener("pointermove", onMove)
      el.removeEventListener("pointerup", onUp)
    }
    el.addEventListener("pointermove", onMove)
    el.addEventListener("pointerup", onUp)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <div
        ref={viewport}
        role="region"
        aria-label="Scan canvas. Drag empty space to pan, drag a card to move it."
        onPointerDown={pan}
        className="relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden bg-canvas data-[panning=true]:cursor-grabbing"
        style={{
          backgroundImage: "radial-gradient(circle, var(--separator) 1.2px, transparent 1.4px)",
          backgroundSize: "22px 22px",
          backgroundPosition: `${offset.x}px ${offset.y}px`,
        }}
      >
        <div className="pointer-events-none absolute inset-0" style={{ transform: `translate(${offset.x}px, ${offset.y}px)` }}>
          {scans.data?.map((scan) => layout[scan.id] ? (
            <AgentCard
              key={scan.id}
              scan={scan}
              pos={layout[scan.id]}
              onMove={move}
              raised={front === scan.id}
              fresh={fresh === scan.id}
              onRaise={() => setFront(scan.id)}
              hidden={expanded?.id === scan.id}
              onExpand={(from) => {
                if (!expanded) return setExpanded({ id: scan.id, from })
                void collapse().then(() => {
                  const el = document.querySelector(`[data-scan-card="${scan.id}"]`)
                  if (el) setExpanded({ id: scan.id, from: el.getBoundingClientRect() })
                })
              }}
            />
          ) : null)}
        </div>
        {scans.isLoading ? (
          <div className="absolute top-6 left-6 h-[172px] w-[300px] animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
        ) : scans.isError ? (
          <div className="absolute inset-x-4 top-6 mx-auto max-w-md"><ErrorState compact title="Your scans didn't load" description="Try again in a moment." onRetry={() => void scans.refetch()} /></div>
        ) : !scans.data?.length ? (
          <div className="pointer-events-none absolute inset-x-4 top-[28%] mx-auto max-w-sm text-center">
            <Radar className="mx-auto size-8 text-ink-tertiary" strokeWidth={1.5} aria-hidden="true" />
            <p className="mt-3 text-headline text-ink">Send your first agent</p>
            <p className="mt-1 text-callout text-ink-secondary">Each scan is one agent looking for one audience. It appears here as a card you can move around.</p>
          </div>
        ) : null}
      </div>
      {expanded ? <ScanMorph key={expanded.id} id={expanded.id} from={expanded.from} closeRef={closeMorph} onClosed={() => setExpanded(null)} /> : null}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-40 px-4 pb-4 sm:px-6 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
        <ScanComposer onStarted={onStarted} className="pointer-events-auto mx-auto max-w-[760px] shadow-elevation-3" />
      </div>
    </div>
  )
}

function AgentCard({ scan, pos, onMove, raised, fresh, onRaise, hidden, onExpand }: {
  scan: Scan
  pos: Pos
  onMove: (id: string, pos: Pos, commit: boolean) => void
  raised: boolean
  fresh: boolean
  onRaise: () => void
  hidden: boolean
  onExpand: (from: DOMRect) => void
}) {
  const ref = React.useRef<HTMLElement>(null)
  const client = useQueryClient()
  const running = scan.status === "running"
  const cancel = useMutation({
    mutationFn: () => api.cancelScan(scan.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["scans"] }),
    onError: (e) => toastError(e),
  })
  const [dragging, setDragging] = React.useState(false)
  const status = STATUS[scan.status] ?? STATUS.pending
  const duration = formatDuration(scanElapsedMs(scan))
  const focus = scanFocus(scan)
  const open = () => { if (ref.current) onExpand(ref.current.getBoundingClientRect()) }

  const drag = (e: React.PointerEvent<HTMLElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button, a, [role=menuitem]")) return
    onRaise()
    // Details load only once someone reaches for the card, so they arrive while it grows.
    void client.prefetchQuery({ queryKey: ["scan", scan.id], queryFn: () => api.getScan(scan.id), staleTime: 10_000 })
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    const start = { x: e.clientX, y: e.clientY }
    let moved = false
    let last = pos
    const onMovePtr = (ev: PointerEvent) => {
      const dx = ev.clientX - start.x
      const dy = ev.clientY - start.y
      if (!moved && Math.hypot(dx, dy) < 4) return
      moved = true
      setDragging(true)
      last = { x: pos.x + dx, y: pos.y + dy }
      onMove(scan.id, last, false)
    }
    const onUp = () => {
      el.removeEventListener("pointermove", onMovePtr)
      el.removeEventListener("pointerup", onUp)
      setDragging(false)
      if (moved) onMove(scan.id, last, true)
      else open()
    }
    el.addEventListener("pointermove", onMovePtr)
    el.addEventListener("pointerup", onUp)
  }

  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const remove = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      setConfirmDelete(false)
      void client.invalidateQueries({ queryKey: ["scans"] })
      toastSuccess("Scan deleted. What it found stays in the catalog.")
    },
    onError: (e) => toastError(e),
  })
  const actions: MenuAction[] = [
    { label: "Open scan", icon: <PanelRightOpen />, onSelect: open },
    running
      ? { label: "Stop", icon: <Square />, onSelect: () => cancel.mutate() }
      : { label: "Delete scan", icon: <Trash2 />, danger: true, onSelect: () => setConfirmDelete(true) },
  ]

  const nudge = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 64 : 16
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key]
    if (!d) return
    e.preventDefault()
    onMove(scan.id, { x: pos.x + d[0], y: pos.y + d[1] }, true)
  }

  return (
    <>
    <ActionContextMenu actions={actions}>
    <article
      ref={ref}
      data-scan-card={scan.id}
      aria-label={scanTitle(scan)}
      aria-hidden={hidden || undefined}
      onPointerDown={drag}
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)`, width: CARD_W, minHeight: CARD_H }}
      className={cn(
        "pointer-events-auto absolute top-0 left-0 flex cursor-pointer touch-none flex-col gap-3 rounded-lg border bg-surface p-4 shadow-elevation-1 select-none",
        "transition-[box-shadow,border-color] duration-150 hover:border-input-border-hover hover:shadow-elevation-2",
        raised ? "z-20" : "z-10",
        dragging && "cursor-grabbing shadow-elevation-3",
        fresh ? "bl-pop border-focus" : "border-separator",
        hidden && "invisible",
      )}
    >
      <header className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-forest-soft text-link">
          {running ? <Radar className="size-4 motion-safe:animate-pulse" strokeWidth={1.75} aria-hidden="true" /> : <Radar className="size-4" strokeWidth={1.75} aria-hidden="true" />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-callout font-semibold text-ink">{audiences(scan)}</h2>
          <p className="truncate text-caption text-ink-tertiary">{scan.region || "Anywhere"}</p>
        </div>
        <button
          type="button"
          aria-label={`Move ${scanTitle(scan)} with the arrow keys`}
          onKeyDown={nudge}
          className="grid size-7 cursor-grab place-items-center rounded-sm text-ink-tertiary hover:bg-highlight hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
        >
          <GripVertical className="size-4" aria-hidden="true" />
        </button>
        <ActionMenuButton label={`More for ${scanTitle(scan)}`} actions={actions} />
      </header>
      <p className={cn("line-clamp-2 text-footnote", focus ? "text-ink" : "text-ink-tertiary")}>{focus || "Any open opportunity"}</p>
      <div className="mt-auto space-y-2">
        {running ? (
          <div className="h-1 overflow-hidden rounded-full bg-surface-sunk" role="progressbar" aria-label="Scan in progress">
            <div className="bl-indeterminate h-full w-1/3 rounded-full bg-sun" />
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-2">
          <Chip tone={status.tone} icon={running ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : undefined}>
            {duration ? `${status.label} ${running ? "for" : "in"} ${duration}` : status.label}
          </Chip>
          <span className="text-caption text-ink-tertiary tabular-nums">
            {running ? `${scan.opportunities_added} saved so far` : `${scan.opportunities_added} saved, ${formatAgo(scan.created_at)}`}
          </span>
        </div>
      </div>
    </article>
    </ActionContextMenu>
    <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
      <AlertDialogContent className="max-w-sm">
        <DialogHeader>
          <AlertDialogTitle className="type-title-3">Delete this scan?</AlertDialogTitle>
          <AlertDialogDescription className="text-callout text-ink-secondary">Its activity log goes. The opportunities it saved stay in the catalog.</AlertDialogDescription>
        </DialogHeader>
        <DialogFooter className="pt-5">
          <Button variant="quiet" onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Delete scan</Button>
        </DialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  )
}

function ScanComposer({ onStarted, className, showAllowance = false }: { onStarted?: (scan: Scan) => void; className?: string; showAllowance?: boolean }) {
  const client = useQueryClient()
  const allowance = useAllowance()
  const [category, setCategory] = React.useState<OpportunityCategory>("startup")
  const [region, setRegion] = React.useState("Ghana")
  const [focus, setFocus] = React.useState("")
  const start = useMutation({
    mutationFn: () => api.startScan({ categories: [category], region: region.trim(), focus: focus.trim() }),
    onSuccess: (scan) => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      setFocus("")
      toastSuccess(`Agent sent to find ${CATEGORY_LABELS[category].toLowerCase()} opportunities`)
      onStarted?.(scan)
    },
    onError: (err) => toastError(err, "Couldn't start the scan"),
  })
  const a = allowance.data
  const blocked = !!a?.enabled && (a.left_this_hour === 0 || a.left_today === 0)
  const submit = () => { if (!blocked && !start.isPending) start.mutate() }
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); submit() }}
      className={cn("rounded-lg border border-input-border bg-surface p-2.5 pl-4 transition-[border-color,box-shadow] duration-150", className)}
    >
      <label htmlFor="scan-focus" className="sr-only">What should this agent look for?</label>
      <textarea
        id="scan-focus"
        rows={1}
        value={focus}
        maxLength={2000}
        onChange={(e) => setFocus(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }}
        placeholder="What should this agent look for? e.g. climate and agritech grants"
        className="max-h-32 min-h-9 w-full resize-none bg-transparent py-1.5 text-body text-ink outline-none [field-sizing:content] placeholder:text-ink-tertiary"
      />
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Audience" className="flex rounded-full bg-surface-sunk p-0.5">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={category === c}
              onClick={() => setCategory(c)}
              className={cn(
                "h-7 cursor-pointer rounded-full px-3 text-footnote font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-focus",
                category === c ? "bg-surface text-ink shadow-elevation-1" : "text-ink-secondary hover:text-ink",
              )}
            >
              {CATEGORY_LABELS[c]}
            </button>
          ))}
        </div>
        <CountrySelect value={region} onChange={setRegion} side="top" />
        {showAllowance ? <span className="ml-auto"><AllowanceNote /></span> : null}
        <Button
          type="submit"
          size="sm"
          variant="primary"
          iconOnly
          aria-label={blocked ? "No scans left for now" : "Start scan"}
          title={blocked ? "No scans left for now" : undefined}
          disabled={blocked || start.isPending}
          icon={start.isPending ? <Loader2 className="motion-safe:animate-spin" /> : <ArrowUp />}
          className={cn("size-9", !showAllowance && "ml-auto")}
        />
      </div>
    </form>
  )
}

export function ScanDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>New scan</DialogTitle>
          <DialogDescription>One agent looks for one audience, in the catalog first and then across the web.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <ScanComposer showAllowance onStarted={() => { onOpenChange(false); navigate("/scans") }} />
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}

function useScan(id: string) {
  return useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    refetchInterval: ({ state: { data } }) =>
      data?.status === "running" || data?.tasks?.some((task) => task.status === "running") ? 4000 : false,
  })
}

function ScanPanel({ scan, actions }: { scan: Scan; actions?: React.ReactNode }) {
  const running = scan.status === "running"
  const duration = formatDuration(scanElapsedMs(scan))
  const status = STATUS[scan.status] ?? STATUS.pending
  return (
    <section aria-label={scanTitle(scan)} className={PANEL}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-headline text-ink">
            {actions ? (scanFocus(scan) ? `Focus on ${scanFocus(scan)}` : "Tasks") : <Link to={`/scans/${scan.id}`} className="hover:underline">{scanTitle(scan)}</Link>}
          </h2>
        </div>
        <Chip tone={status.tone} icon={running ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : undefined}>
          {duration ? `${status.label} ${running ? "for" : "in"} ${duration}` : status.label}
        </Chip>
        {actions}
      </div>
      {/* <Tasks tasks={scan.tasks ?? []} /> */}
      <Finds finds={scan.finds ?? []} running={running} />
    </section>
  )
}

export function ScanDetail() {
  const { scanId = "" } = useParams<{ scanId: string }>()
  const navigate = useNavigate()
  const scan = useScan(scanId)
  if (scan.isLoading) return <div className="h-40 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
  if (scan.isError || !scan.data)
    return <ErrorState title="This scan didn't load" description="It may have been deleted." onRetry={() => void scan.refetch()} />
  return (
    <div className="bl-enter min-w-0 max-w-3xl mx-auto space-y-5">
      <PageHeader
        back={<Link to="/scans" className="hover:text-ink hover:underline">Back to Scans</Link>}
        title={scanTitle(scan.data)}
        description={`Started ${formatAgo(scan.data.created_at)}`}
      />
      <ScanBody scan={scan.data} onDeleted={() => navigate("/scans")} />
    </div>
  )
}

function ScanBody({ scan, onDeleted, log = true }: { scan: Scan; onDeleted: () => void; log?: boolean }) {
  const client = useQueryClient()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const refresh = (next: Scan) => {
    client.setQueryData(["scan", scan.id], next)
    void client.invalidateQueries({ queryKey: ["scans"] })
  }
  const cancel = useMutation({ mutationFn: () => api.cancelScan(scan.id), onSuccess: refresh, onError: (e) => toastError(e) })
  const remove = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      toastSuccess("Scan deleted. What it found stays in the catalog.")
      onDeleted()
    },
    onError: (e) => toastError(e),
  })
  const running = scan.status === "running"
  useTick(running)
  return (
    <div className="space-y-5">
      <ScanPanel
        scan={scan}
        actions={running ? (
          <Button size="sm" variant="quiet" disabled={cancel.isPending} onClick={() => cancel.mutate()} icon={<Square />}>Stop</Button>
        ) : (
          <ActionMenuButton label="Scan actions" actions={[{ label: "Delete scan", icon: <Trash2 />, danger: true, onSelect: () => setConfirmDelete(true) }]} />
        )}
      />
      {log ? <ActivityLog tasks={scan.tasks ?? []} /> : null}
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent className="max-w-sm">
          <DialogHeader>
            <AlertDialogTitle className="type-title-3">Delete this scan?</AlertDialogTitle>
            <AlertDialogDescription className="text-callout text-ink-secondary">Its activity log goes. The opportunities it saved stay in the catalog.</AlertDialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-5">
            <Button variant="quiet" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Delete scan</Button>
          </DialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

const OPEN = { duration: 380, easing: LINEAR_OK ? springEasing(0.78) : "cubic-bezier(0.2, 0.9, 0.25, 1.05)" }
const CLOSE = { duration: 300, easing: LINEAR_OK ? springEasing(0.92) : "cubic-bezier(0.3, 0.8, 0.3, 1)" }
const RADIUS = 20

type Box = { left: number; top: number; width: number; height: number }

/**
 * The card grows into a panel over the canvas; no scrim, and the composer stays on top.
 * The panel keeps its final layout and is revealed through a window that grows from the
 * card's rect, so text never re-wraps mid-animation.
 */
function ScanMorph({ id, from, onClosed, closeRef }: {
  id: string
  from: DOMRect
  onClosed: () => void
  closeRef: React.RefObject<(() => Promise<void>) | null>
}) {
  const frame = React.useRef<HTMLDivElement>(null)
  const shell = React.useRef<HTMLDivElement>(null)
  const content = React.useRef<HTMLDivElement>(null)
  const body = React.useRef<HTMLDivElement>(null)
  const scan = useScan(id)
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches

  const play = React.useCallback((rect: DOMRect, direction: "open" | "close") => {
    const f = frame.current, s = shell.current, c = content.current
    if (!f || !s || !c) return Promise.resolve()
    const box = f.getBoundingClientRect()
    const card: Box = { left: rect.left - box.left, top: rect.top - box.top, width: rect.width, height: rect.height }
    const full: Box = { left: 0, top: 0, width: box.width, height: box.height }
    const geo = (b: Box) => ({ left: `${b.left}px`, top: `${b.top}px`, width: `${b.width}px`, height: `${b.height}px` })
    const win = (b: Box) => ({
      transform: `translate(${b.left}px, ${b.top}px)`,
      clipPath: `inset(0px ${box.width - b.width}px ${box.height - b.height}px 0px round ${RADIUS}px)`,
    })
    const [a, b] = direction === "open" ? [card, full] : [full, card]
    const timing = { ...(direction === "open" ? OPEN : CLOSE), fill: "both" as const }
    const fade = direction === "open"
      ? c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 40, easing: "ease-out", fill: "both" })
      : c.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 130, delay: CLOSE.duration - 170, easing: "ease-in", fill: "both" })
    const moves = [
      s.animate([geo(a), geo(b)], timing),
      c.animate([win(a), win(b)], timing),
      fade,
    ]
    // A copy of the card rides in the growing shell and cross-fades with the panel.
    const source = document.querySelector<HTMLElement>(`[data-scan-card="${id}"]`)
    const ghost = source?.cloneNode(true) as HTMLElement | undefined
    if (ghost) {
      ghost.removeAttribute("data-scan-card")
      ghost.classList.remove("invisible", "bl-pop")
      Object.assign(ghost.style, { transform: "none", inset: "0 auto auto 0", border: "0", boxShadow: "none", background: "transparent", pointerEvents: "none" })
      s.appendChild(ghost)
      moves.push(direction === "open"
        ? ghost.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, easing: "ease-out", fill: "both" })
        : ghost.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, delay: CLOSE.duration - 150, easing: "ease-in", fill: "both" }))
    }
    return Promise.all(moves.map((m) => m.finished)).then(() => {
      ghost?.remove()
      if (direction === "open") moves.forEach((m) => m.cancel())
    })
  }, [id])

  React.useLayoutEffect(() => {
    if (reduced) return
    void play(from, "open")
  }, [from, play, reduced])

  const closed = React.useRef<Promise<void> | null>(null)
  const close = React.useCallback((): Promise<void> => {
    if (closed.current) return closed.current
    const card = document.querySelector(`[data-scan-card="${id}"]`)
    const done = (!card || reduced ? Promise.resolve() : play(card.getBoundingClientRect(), "close")).catch(() => undefined).then(onClosed)
    closed.current = done
    return done
  }, [id, onClosed, play, reduced])

  React.useEffect(() => {
    closeRef.current = close
    return () => { if (closeRef.current === close) closeRef.current = null }
  }, [close, closeRef])

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector("[role=alertdialog],[role=menu]")) void close() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [close])

  React.useEffect(() => { content.current?.focus({ preventScroll: true }) }, [])

  return (
    <div ref={frame} className="pointer-events-none absolute inset-x-3 top-3 bottom-3 z-50 mx-auto max-w-[880px] sm:inset-x-6 sm:top-5 sm:bottom-5">
      <div ref={shell} aria-hidden="true" className="absolute inset-0 overflow-hidden rounded-lg border border-separator bg-surface shadow-elevation-3" />
      <div
        ref={content}
        role="dialog"
        aria-modal="false"
        aria-label={scan.data ? scanTitle(scan.data) : "Scan"}
        tabIndex={-1}
        className="pointer-events-auto absolute inset-0 flex flex-col overflow-hidden rounded-lg outline-none"
      >
        <header className="flex shrink-0 items-start gap-3 border-b border-separator px-5 py-4">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-forest-soft text-link">
            <Radar className="size-4" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate type-title-3 text-ink">{scan.data ? scanTitle(scan.data) : "Scan"}</h2>
            {scan.data ? <p className="text-footnote text-ink-secondary">Started {formatAgo(scan.data.created_at)}</p> : null}
          </div>
          <button type="button" aria-label="Close" onClick={() => void close()} className="grid size-8 shrink-0 cursor-pointer place-items-center rounded-full bg-surface-sunk text-ink-secondary transition-colors hover:bg-separator hover:text-ink focus-visible:outline-2 focus-visible:outline-focus">
            <X className="size-4" />
          </button>
        </header>
        <div ref={body} className="flex min-h-0 flex-1 flex-col">
          <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
            {scan.isLoading ? (
              <div className="h-40 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
            ) : scan.isError || !scan.data ? (
              <ErrorState title="This scan didn't load" description="It may have been deleted." onRetry={() => void scan.refetch()} />
            ) : (
              <ScanBody scan={scan.data} onDeleted={onClosed} log={false} />
            )}
          </div>
          {scan.data?.tasks?.length ? <DockedLog tasks={scan.data.tasks} container={body} /> : null}
        </div>
      </div>
    </div>
  )
}

const FINDS_PREVIEW = 8

function Finds({ finds, running }: { finds: ScanFind[]; running: boolean }) {
  const [all, setAll] = React.useState(false)
  const tracked = useTrackedOpportunities()
  const shown = all ? finds : finds.slice(0, FINDS_PREVIEW)
  return (
    <div>
      <div className="flex items-baseline gap-2" aria-live="polite">
        <h3 className="text-callout font-semibold text-ink">{running ? "Found so far" : "Found"}</h3>
        <span className="ml-auto text-footnote text-ink-tertiary tabular-nums">
          {finds.length} {finds.length === 1 ? "opportunity" : "opportunities"}
        </span>
      </div>
      {shown.length ? (
        <ul className="mt-1">
          {shown.map((find, index) => (
            <FindRow key={find.opportunity_id} find={find} tracking={!!tracked.data?.[find.opportunity_id]} index={index} />
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-footnote text-ink-secondary">{running ? "Finds appear here as the scan runs." : "This scan didn't find anything new."}</p>
      )}
      {finds.length > FINDS_PREVIEW ? (
        <Button size="sm" variant="quiet" className="mt-1" aria-expanded={all} onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${finds.length}`}
        </Button>
      ) : null}
    </div>
  )
}

function FindRow({ find, tracking, index }: { find: ScanFind; tracking: boolean; index: number }) {
  const track = useTrackOpportunity()
  const fromWeb = find.source === "web"
  const SourceIcon = fromWeb ? Globe : Database
  const actions: MenuAction[] = []
  if (find.official_url) actions.push({ label: "Official page", icon: <ArrowUpRight />, href: find.official_url })

  return (
    <ActionContextMenu actions={actions}>
      <li
        style={{ "--i": index } as React.CSSProperties}
        className={cn(
          "bl-enter relative grid grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 border-t border-separator py-2.5 first:border-t-0",
          !find.in_review && "-mx-2 rounded-sm px-2 hover:bg-highlight",
        )}
      >
        <OpportunityArt seed={find.slug || find.opportunity_id} category={find.category ?? undefined} kind={find.kind ?? undefined} shape="square" className="size-9 rounded-sm" />
        <div className="min-w-0">
          {find.in_review ? (
            <p className="truncate text-callout font-semibold text-ink" title={find.title}>{find.title}</p>
          ) : (
            <Link
              to={`/opportunities/${encodeURIComponent(find.slug || find.opportunity_id)}`}
              title={find.title}
              className="block truncate text-callout font-semibold text-ink after:absolute after:inset-0 after:rounded-sm after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-focus"
            >
              {find.title}
            </Link>
          )}
          <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-caption font-medium text-ink-tertiary">
            <span className="inline-flex min-w-0 items-center gap-1">
              <SourceIcon aria-hidden="true" className="size-3.5 shrink-0" />
              <span className="truncate">{fromWeb ? `Found on the web${find.source_domain ? `, ${find.source_domain}` : ""}` : "From the Blesser catalog"}</span>
            </span>
            {find.deadline_date ? <Countdown variant="text" daysLeft={daysUntil(find.deadline_date)} date={find.deadline_date} /> : null}
          </p>
        </div>
        <div className="relative z-10 flex items-center gap-1.5">
          {find.in_review ? <Chip tone="neutral">In review</Chip> : find.is_new && !tracking ? <Chip tone="sun" className="max-sm:hidden">New</Chip> : null}
          {tracking ? (
            <Link to="/applications" className={cn(buttonVariants({ size: "sm", variant: "quiet" }), "text-link")}>
              <Check aria-hidden="true" /> Tracking
            </Link>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              icon={<Plus />}
              disabled={track.isPending}
              onClick={() => track.mutate(find.opportunity_id, {
                onSuccess: () => toastSuccess("Added to your applications."),
                onError: (err) => toastError(err, "Couldn't track this opportunity."),
              })}
            >
              Track
            </Button>
          )}
          {actions.length ? <ActionMenuButton actions={actions} label={`More for ${find.title}`} /> : null}
        </div>
      </li>
    </ActionContextMenu>
  )
}

function taskName(task: ScanTask): string {
  const category = CATEGORIES.find((value) => task.target === `category:${value}`)
  return category ? `Searching for ${CATEGORY_LABELS[category].toLowerCase()}` : "Searching"
}

const TASK_STATE = {
  pending: { cls: "bg-surface-sunk text-ink-secondary", icon: CircleDashed },
  running: { cls: "bg-sun-soft text-sun-ink", icon: Loader2 },
  done: { cls: "bg-forest-soft text-link", icon: Check },
  error: { cls: "bg-caution-soft text-caution", icon: CircleAlert },
  cancelled: { cls: "bg-surface-sunk text-ink-tertiary", icon: Square },
} as const

function lastAction(task: ScanTask): string | null {
  for (let i = task.log.length - 1; i >= 0; i--) {
    if (task.log[i].kind !== "turn") return describeEvent(task.log[i]).text
  }
  return null
}

function Tasks({ tasks }: { tasks: ScanTask[] }) {
  if (!tasks.length) return null
  return (
    <ol aria-label="Scan tasks">
      {tasks.map((task) => {
        const { cls, icon: Icon } = TASK_STATE[task.status]
        const activity = task.status === "running" ? lastAction(task) : task.status === "pending" ? "Waiting to start" : task.status === "error" ? task.error : null
        const duration = task.started_at ? formatDuration(elapsedMs(task.started_at, task.finished_at)) : ""
        const right = task.status === "pending" ? "Queued" : task.status === "error" ? "Stopped early" : task.status === "cancelled" ? "Stopped" : duration
        return (
          <li key={task.id} className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-start gap-3 border-t border-separator py-3 first:border-t-0">
            <span className={cn("grid size-7 place-items-center rounded-full", cls)}>
              <Icon aria-hidden="true" className={cn("size-3.5", task.status === "running" && "motion-safe:animate-spin")} />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-callout font-semibold text-ink">{taskName(task)}</p>
              {activity ? <p className="line-clamp-2 text-footnote text-ink-secondary wrap-anywhere">{activity}</p> : null}
            </div>
            {right ? <span className="pt-1 text-footnote text-ink-tertiary tabular-nums">{right}</span> : null}
          </li>
        )
      })}
    </ol>
  )
}

const PREFIX: Record<string, { label: string; tone: string }> = {
  search: { label: "search", tone: "text-console-info" },
  read: { label: "read", tone: "text-console-dim" },
  save: { label: "save", tone: "text-console-ok" },
  update: { label: "update", tone: "text-console-ok" },
  note: { label: "note", tone: "text-console-dim" },
}

const LOG_HEIGHT_KEY = "blesser.scan-log-height"
const LOG_MIN = 96

function DockedLog({ tasks, container }: { tasks: ScanTask[]; container: React.RefObject<HTMLDivElement | null> }) {
  const [height, setHeight] = React.useState(() => {
    try {
      return Number(localStorage.getItem(LOG_HEIGHT_KEY)) || 280
    } catch {
      return 280
    }
  })
  const [dragging, setDragging] = React.useState(false)
  const max = () => Math.max(LOG_MIN, (container.current?.clientHeight ?? 600) - 120)
  const commit = (h: number) => {
    const next = Math.round(Math.min(max(), Math.max(LOG_MIN, h)))
    setHeight(next)
    try {
      localStorage.setItem(LOG_HEIGHT_KEY, String(next))
    } catch {
      // Height is a per-browser convenience.
    }
  }

  const drag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    const startY = e.clientY
    const startH = height
    setDragging(true)
    const onMove = (ev: PointerEvent) => setHeight(Math.min(max(), Math.max(LOG_MIN, startH - (ev.clientY - startY))))
    const onUp = (ev: PointerEvent) => {
      el.removeEventListener("pointermove", onMove)
      el.removeEventListener("pointerup", onUp)
      setDragging(false)
      commit(startH - (ev.clientY - startY))
    }
    el.addEventListener("pointermove", onMove)
    el.addEventListener("pointerup", onUp)
  }

  const shown = Math.min(height, max())
  return (
    <div style={{ height: shown }} className="relative flex shrink-0 flex-col">
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize activity log"
        aria-valuemin={LOG_MIN}
        aria-valuemax={max()}
        aria-valuenow={shown}
        tabIndex={0}
        onPointerDown={drag}
        onDoubleClick={() => commit(shown > LOG_MIN + 40 ? LOG_MIN : 280)}
        onKeyDown={(e) => {
          const step = e.shiftKey ? 80 : 24
          if (e.key === "ArrowUp") { e.preventDefault(); commit(shown + step) }
          else if (e.key === "ArrowDown") { e.preventDefault(); commit(shown - step) }
        }}
        className="group absolute inset-x-0 -top-1.5 z-10 flex h-3 cursor-row-resize touch-none items-center outline-none"
      >
        <span className={cn("h-0.5 w-full transition-colors duration-150 group-hover:bg-focus group-focus-visible:bg-focus", dragging ? "bg-focus" : "bg-transparent")} />
      </div>
      <ActivityLog tasks={tasks} docked />
    </div>
  )
}

function ActivityLog({ tasks, docked = false }: { tasks: ScanTask[]; docked?: boolean }) {
  const [picked, setPicked] = React.useState<string | null>(null)
  const [notes, setNotes] = React.useState(true)
  const scroller = React.useRef<HTMLOListElement>(null)
  const follow = React.useRef(true)
  const current = tasks.find((t) => t.id === picked) ?? tasks.find((t) => t.status === "running") ?? tasks[0]
  const lines = current ? current.log.map(describeEvent).filter((l) => (l.kind === "note" ? notes && l.text : true)) : []
  const live = current?.status === "running"

  React.useEffect(() => {
    const el = scroller.current
    if (el && follow.current) el.scrollTop = el.scrollHeight
  }, [lines.length, current?.id])

  if (!current) return null
  return (
    <section aria-label="Activity log" className={cn("overflow-hidden bg-console text-console-ink", docked ? "flex h-full min-h-0 flex-col" : "rounded-lg shadow-elevation-1")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-console-line bg-console-bar px-4 py-2.5">
        <span className="flex items-center gap-2 font-mono text-[12px] text-console-dim">
          <span aria-hidden="true" className={cn("size-2 rounded-full", live ? "bg-console-ok motion-safe:animate-pulse" : "bg-console-line")} />
          activity.log
        </span>
        {tasks.length > 1 ? (
          <div role="tablist" aria-label="Agent" className="flex gap-1">
            {tasks.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={t.id === current.id}
                onClick={() => setPicked(t.id)}
                className={cn(
                  "h-6 cursor-pointer rounded-[6px] px-2 font-mono text-[12px] transition-colors focus-visible:outline-2 focus-visible:outline-focus",
                  t.id === current.id ? "bg-console-line text-console-ink" : "text-console-dim hover:text-console-ink",
                )}
              >
                {taskName(t)}
              </button>
            ))}
          </div>
        ) : null}
        <button
          type="button"
          aria-pressed={notes}
          onClick={() => setNotes((v) => !v)}
          className="ml-auto h-6 cursor-pointer rounded-[6px] px-2 font-mono text-[12px] text-console-dim transition-colors hover:text-console-ink focus-visible:outline-2 focus-visible:outline-focus aria-pressed:text-console-ink"
        >
          {notes ? "[x]" : "[ ]"} notes
        </button>
      </div>
      {lines.length === 0 ? (
        <p className="px-4 py-4 font-mono text-[12px] text-console-dim">
          {current.status === "pending" ? "$ waiting for this agent to start" : "$ no steps recorded"}
        </p>
      ) : (
        <ol
          ref={scroller}
          onScroll={(e) => {
            const el = e.currentTarget
            follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
          }}
          aria-label={`${taskName(current)} activity`}
          aria-live={live ? "polite" : undefined}
          className={cn(docked ? "min-h-0 flex-1" : "max-h-[28rem]", "overflow-y-auto overscroll-contain px-4 py-3 font-mono text-[12px] leading-[20px] [scrollbar-color:var(--console-line)_transparent]")}
        >
          {lines.map((line, i) => <LogRow key={i} line={line} />)}
          {live ? (
            <li aria-hidden="true" className="flex gap-3 text-console-dim">
              <span className="w-[4.5rem] shrink-0" />
              <span className="inline-block h-[15px] w-[7px] translate-y-[3px] bg-console-ink motion-safe:animate-pulse" />
            </li>
          ) : null}
        </ol>
      )}
    </section>
  )
}

function LogRow({ line }: { line: LogLine }) {
  const prefix = line.failed ? { label: "error", tone: "text-console-warn" } : PREFIX[line.kind] ?? { label: "tool", tone: "text-console-dim" }
  const text = line.opportunityId ? (
    <Link to={`/opportunities/${line.opportunityId}`} className="underline decoration-console-line underline-offset-2 hover:decoration-console-ink">{line.text}</Link>
  ) : line.href && !line.failed ? (
    <a href={line.href} target="_blank" rel="noopener noreferrer" className="underline decoration-console-line underline-offset-2 hover:decoration-console-ink">{line.text}</a>
  ) : line.text
  return (
    <li className="flex gap-3 rounded-[4px] hover:bg-console-bar">
      <time className="w-[4.5rem] shrink-0 text-console-dim tabular-nums">{clock(line.at)}</time>
      <span className={cn("w-12 shrink-0", prefix.tone)}>{prefix.label}</span>
      <span className={cn("min-w-0 flex-1 break-words", line.kind === "note" ? "text-console-dim italic" : line.failed ? "text-console-warn" : "text-console-ink")}>
        {text}
        {line.reason ? <span className="block text-console-dim not-italic">{line.reason}</span> : null}
      </span>
    </li>
  )
}
