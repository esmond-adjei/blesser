import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription } from "../components/ui/alert-dialog"
import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  CircleDashed,
  Database,
  FileText,
  Globe,
  Loader2,
  PanelRightOpen,
  Radar,
  MessageSquareText,
  Plus,
  Search,
  Square,
  Trash2,
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
import type { OpportunityCategory, Scan, ScanFind, ScanTask } from "../lib/types"
import { Button, Chip, Countdown, Field, Input, OpportunityArt, Textarea, buttonVariants, cn, daysUntil } from "@blesser/ui"
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
import { FilterToggle, PageHeader, Segmented } from "../components/layout/PageHeader"
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
  const text = a.left_today === 0 ? "No scans left today" : left === 0 ? "No scans left this hour" : `${a.left_this_hour} of ${a.per_hour} scans left this hour`
  return <span className="text-footnote text-ink-secondary tabular-nums">{text}</span>
}

export function Scans() {
  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "running") ? 10_000 : 60_000),
  })
  const running = scans.data?.find((s) => s.status === "running")
  useTick(!!running)
  return (
    <div className="bl-enter min-w-0 space-y-6">
      <PageHeader
        title="Scans"
        description="Find opportunities from the Blesser catalog and across the web."
        actions={<AllowanceNote />}
      />
      <div className="grid items-start gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <section aria-labelledby="new-scan-heading" className={cn(PANEL, "lg:sticky lg:top-0")}>
          <h2 id="new-scan-heading" className="text-headline text-ink">New scan</h2>
          <NewScanForm />
        </section>
        <div className="min-w-0 space-y-5">
          {running ? <RunningScan id={running.id} /> : null}
          <section aria-labelledby="your-scans-heading" className={cn(PANEL, "gap-0 p-0")}>
            <h2 id="your-scans-heading" className="px-5 pt-5 pb-3 text-headline text-ink">Your scans</h2>
            {scans.isLoading ? (
              <div className="mx-5 mb-5 h-24 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
            ) : scans.isError ? (
              <div className="px-5 pb-5"><ErrorState compact title="Your scans didn't load" description="Try again in a moment." onRetry={() => void scans.refetch()} /></div>
            ) : !scans.data?.length ? (
              <p className="px-5 pb-5 text-callout text-ink-secondary">No scans yet. Start one to look beyond the catalog.</p>
            ) : (
              <ul className="border-t border-separator">
                {scans.data.map((scan, i) => <ScanRow key={scan.id} scan={scan} index={i} />)}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

function ScanRow({ scan, index }: { scan: Scan; index: number }) {
  const duration = formatDuration(scanElapsedMs(scan))
  const status = STATUS[scan.status] ?? STATUS.pending
  return (
    <li style={{ "--i": index } as React.CSSProperties} className="bl-enter border-t border-separator first:border-t-0">
      <Link
        to={`/scans/${scan.id}`}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3 hover:bg-highlight focus-visible:-outline-offset-2"
      >
        <span className="min-w-0">
          <span className="block truncate text-callout font-semibold text-ink">{scanTitle(scan)}</span>
          <span className="block truncate text-footnote text-ink-tertiary">
            {[scanFocus(scan) && `Focus on ${scanFocus(scan)}`, `${scan.opportunities_added} saved`, duration, formatAgo(scan.created_at)].filter(Boolean).join(", ")}
          </span>
        </span>
        <Chip tone={status.tone}>{status.label}</Chip>
      </Link>
    </li>
  )
}

function NewScanForm({ onStarted, className }: { onStarted?: () => void; className?: string }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const allowance = useAllowance()
  const [categories, setCategories] = React.useState<OpportunityCategory[]>([...CATEGORIES])
  const [region, setRegion] = React.useState("Ghana")
  const [focus, setFocus] = React.useState("")
  const start = useMutation({
    mutationFn: () => api.startScan({ categories, region: region.trim(), focus: focus.trim() }),
    onSuccess: (scan) => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      onStarted?.()
      navigate(`/scans/${scan.id}`)
    },
    onError: (err) => toastError(err, "Couldn't start the scan"),
  })
  const toggle = (c: OpportunityCategory) =>
    setCategories((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  const a = allowance.data
  const blocked = !!a?.enabled && (a.left_this_hour === 0 || a.left_today === 0)
  return (
    <form
      className={cn("flex flex-col gap-4", className)}
      onSubmit={(e) => {
        e.preventDefault()
        if (categories.length && !blocked) start.mutate()
      }}
    >
      <Field label="What are you looking for?" hint="Optional. Sectors, fields or kinds to look at first.">
        <Textarea
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          maxLength={2000}
          rows={3}
          className="min-h-20"
          placeholder="Climate and agritech funding for an early-stage startup"
        />
      </Field>
      <fieldset>
        <legend className="mb-1.5 text-callout font-semibold text-ink">For</legend>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <Chip key={c} selected={categories.includes(c)} onClick={() => toggle(c)}>{CATEGORY_LABELS[c]}</Chip>
          ))}
        </div>
        {!categories.length ? <p className="mt-1.5 text-footnote text-caution">Pick at least one.</p> : null}
      </fieldset>
      <Field label="Where">
        <Input value={region} onChange={(e) => setRegion(e.target.value)} maxLength={120} placeholder="Ghana" />
      </Field>
      <p className="text-footnote text-ink-secondary">
        We check the Blesser catalog first, then search the web for anything missing. Scans take 15 to 30 minutes and keep running if you leave.
      </p>
      <Button type="submit" size="lg" variant="primary" icon={<Radar />} disabled={start.isPending || !categories.length || blocked}>
        {start.isPending ? "Starting" : blocked ? "No scans left for now" : "Start a scan"}
      </Button>
    </form>
  )
}

export function ScanDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>New scan</DialogTitle>
          <DialogDescription><AllowanceNote /></DialogDescription>
        </DialogHeader>
        <DialogBody>
          <NewScanForm onStarted={() => onOpenChange(false)} />
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

function RunningScan({ id }: { id: string }) {
  const scan = useScan(id)
  if (!scan.data) return null
  return <ScanPanel scan={scan.data} />
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
      <Tasks tasks={scan.tasks ?? []} />
      <Finds finds={scan.finds ?? []} running={running} />
    </section>
  )
}

export function ScanDetail() {
  const { scanId = "" } = useParams<{ scanId: string }>()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const scan = useScan(scanId)
  const refresh = (next: Scan) => {
    client.setQueryData(["scan", scanId], next)
    void client.invalidateQueries({ queryKey: ["scans"] })
  }
  const cancel = useMutation({ mutationFn: () => api.cancelScan(scanId), onSuccess: refresh, onError: (e) => toastError(e) })
  const remove = useMutation({
    mutationFn: () => api.deleteScan(scanId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      toastSuccess("Scan deleted. What it found stays in the catalog.")
      navigate("/scans")
    },
    onError: (e) => toastError(e),
  })
  const running = scan.data?.status === "running"
  useTick(running)

  if (scan.isLoading) return <div className="h-40 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
  if (scan.isError || !scan.data)
    return <ErrorState title="This scan didn't load" description="It may have been deleted." onRetry={() => void scan.refetch()} />
  const data = scan.data
  return (
    <div className="bl-enter min-w-0 space-y-5">
      <PageHeader
        back={<Link to="/scans" className="hover:text-ink hover:underline">Scans</Link>}
        title={scanTitle(data)}
        description={`Started ${formatAgo(data.created_at)}`}
      />
      <ScanPanel
        scan={data}
        actions={running ? (
          <Button size="sm" variant="quiet" disabled={cancel.isPending} onClick={() => cancel.mutate()} icon={<Square />}>Stop</Button>
        ) : (
          <ActionMenuButton label="Scan actions" actions={[{ label: "Delete scan", icon: <Trash2 />, danger: true, onSelect: () => setConfirmDelete(true) }]} />
        )}
      />
      <ActivityLog tasks={data.tasks ?? []} />
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
  const navigate = useNavigate()
  const track = useTrackOpportunity()
  const fromWeb = find.source === "web"
  const SourceIcon = fromWeb ? Globe : Database
  const actions: MenuAction[] = []
  if (!find.in_review) {
    actions.push({ label: "Open details", icon: <PanelRightOpen />, onSelect: () => navigate(`/opportunities/${find.slug || find.opportunity_id}`) })
  }
  if (find.official_url) actions.push({ label: "Official page", icon: <ArrowUpRight />, href: find.official_url })

  return (
    <ActionContextMenu actions={actions}>
      <li
        style={{ "--i": index } as React.CSSProperties}
        className="bl-enter grid grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 border-t border-separator py-2.5 first:border-t-0"
      >
        <OpportunityArt seed={find.slug || find.opportunity_id} category={find.category ?? undefined} kind={find.kind ?? undefined} shape="square" className="size-9 rounded-sm" />
        <div className="min-w-0">
          <p className="truncate text-callout font-semibold text-ink" title={find.title}>{find.title}</p>
          <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-caption font-medium text-ink-tertiary">
            <span className="inline-flex min-w-0 items-center gap-1">
              <SourceIcon aria-hidden="true" className="size-3.5 shrink-0" />
              <span className="truncate">{fromWeb ? `Found on the web${find.source_domain ? `, ${find.source_domain}` : ""}` : "From the Blesser catalog"}</span>
            </span>
            {find.deadline_date ? <Countdown variant="text" daysLeft={daysUntil(find.deadline_date)} date={find.deadline_date} /> : null}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {find.is_new && !tracking ? <Chip tone="sun" className="max-sm:hidden">New</Chip> : null}
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

function LineIcon({ line }: { line: LogLine }) {
  const cls = "size-3.5 shrink-0"
  if (line.failed) return <CircleAlert aria-hidden="true" className={cn(cls, "text-caution")} />
  if (line.kind === "search") return <Search aria-hidden="true" className={cn(cls, "text-ink-tertiary")} />
  if (line.kind === "read") return <FileText aria-hidden="true" className={cn(cls, "text-ink-tertiary")} />
  if (line.kind === "save" || line.kind === "update") return <Check aria-hidden="true" className={cn(cls, "text-positive")} />
  if (line.kind === "note") return <MessageSquareText aria-hidden="true" className={cn(cls, "text-ink-tertiary")} />
  return <span aria-hidden="true" className="size-3.5 shrink-0" />
}

function ActivityLog({ tasks }: { tasks: ScanTask[] }) {
  const [open, setOpen] = React.useState(false)
  const [picked, setPicked] = React.useState<string | null>(null)
  const [notes, setNotes] = React.useState(true)
  const id = React.useId()
  const steps = tasks.reduce((n, t) => n + t.log.filter((e) => e.kind !== "turn").length, 0)
  if (!tasks.length) return null
  const current = tasks.find((t) => t.id === picked) ?? tasks.find((t) => t.status === "running") ?? tasks[0]
  const lines = current.log.map(describeEvent).filter((l) => (l.kind === "note" ? notes && l.text : true))
  return (
    <section className="rounded-lg border border-separator bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-4 py-3 text-left hover:bg-highlight"
      >
        <ChevronRight aria-hidden="true" className={cn("size-4 text-ink-tertiary transition-transform duration-160", open && "rotate-90")} />
        <span className="text-callout font-semibold text-ink">Activity log</span>
        <span className="text-footnote text-ink-tertiary">{steps} steps</span>
      </button>
      <div id={id} hidden={!open} className="border-t border-separator">
        {open ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
              {tasks.length > 1 ? (
                <Segmented
                  label="Agent"
                  value={current.id}
                  onChange={setPicked}
                  options={tasks.map((t) => ({ value: t.id, label: taskName(t), count: t.log.filter((e) => e.kind !== "turn").length }))}
                />
              ) : (
                <span />
              )}
              <FilterToggle pressed={notes} onChange={setNotes}>
                Agent notes
              </FilterToggle>
            </div>
            {lines.length === 0 ? (
              <p className="px-4 pb-4 text-footnote text-ink-secondary">
                {current.status === "pending" ? "This agent hasn't started yet." : "No steps recorded."}
              </p>
            ) : (
              <ol className="max-h-[32rem] overflow-y-auto overscroll-contain px-4 pb-3 nice-scroll" aria-label={`${taskName(current)} activity`}>
                {lines.map((line, i) => (
                  <LogRow key={i} line={line} />
                ))}
              </ol>
            )}
          </>
        ) : null}
      </div>
    </section>
  )
}

function LogRow({ line }: { line: LogLine }) {
  return (
    <li className="grid grid-cols-[2.75rem_14px_minmax(0,1fr)] items-start gap-x-2 py-1">
      <time className="pt-px font-mono text-[11px] leading-[18px] text-ink-tertiary">{clock(line.at)}</time>
      <span className="pt-0.5">
        <LineIcon line={line} />
      </span>
      <span className={cn("min-w-0 text-footnote break-words", line.kind === "note" ? "text-ink-tertiary italic" : line.kind === "save" || line.kind === "update" ? "text-ink" : "text-ink-secondary")}>
        {line.opportunityId ? (
          <Link to={`/opportunities/${line.opportunityId}`} className="hover:underline">
            {line.text}
          </Link>
        ) : line.href && !line.failed ? (
          <a href={line.href} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-0.5 hover:underline">
            <span className="truncate">{line.text}</span>
            <ArrowUpRight aria-hidden="true" className="size-3 shrink-0 opacity-60" />
          </a>
        ) : (
          line.text
        )}
        {line.reason ? <span className="block text-ink-tertiary not-italic">{line.reason}</span> : null}
      </span>
    </li>
  )
}

