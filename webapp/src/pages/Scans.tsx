import { Checkbox } from "../components/ui/checkbox"
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
  FileText,
  Info,
  Loader,
  MessageSquareText,
  Plus,
  Search,
  Square,
  Trash2,
} from "lucide-react"
import * as api from "../lib/api"
import { formatAgo } from "../lib/format"
import { CATEGORIES, CATEGORY_DESCRIPTIONS, CATEGORY_LABELS } from "../lib/opportunities"
import {
  clock,
  describeEvent,
  elapsedMs,
  formatDuration,
  savedOpportunities,
  scanElapsedMs,
  taskStats,
  type LogLine,
} from "../lib/scanLog"
import { toastError, toastSuccess } from "../lib/toast"
import type { OpportunityCategory, Scan, ScanTask } from "../lib/types"
import { Button, Countdown, Field, Input, cn, daysUntil } from "@blesser/ui"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { FilterToggle, PageHeader, Segmented } from "../components/layout/PageHeader"
import scanningArt from "@blesser/ui/illustrations/spot-scanning.webp"

type Status = ScanTask["status"] | Scan["status"]

const STATUS: Record<Status, { label: string; dot: string }> = {
  running: { label: "Running", dot: "bg-info motion-safe:animate-pulse" },
  pending: { label: "Waiting", dot: "bg-control-border" },
  done: { label: "Finished", dot: "bg-positive" },
  error: { label: "Stopped early", dot: "bg-caution" },
  cancelled: { label: "Stopped", dot: "bg-ink-tertiary" },
}

function StatusLabel({ status, className }: { status: Status; className?: string }) {
  const s = STATUS[status] ?? STATUS.pending
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-footnote font-medium whitespace-nowrap text-ink-secondary", className)}>
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  )
}

function audiences(scan: Scan): string {
  return scan.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")
}

function scanTitle(scan: Scan): string {
  return scan.region ? `${audiences(scan)} in ${scan.region}` : audiences(scan)
}

/** Re-renders every `ms` while `active`, for elapsed timers. */
function useTick(active: boolean, ms = 15_000) {
  const [, setTick] = React.useState(0)
  React.useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setTick((n) => n + 1), ms)
    return () => window.clearInterval(t)
  }, [active, ms])
}

export function Scans() {
  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "running") ? 10_000 : 60_000),
  })
  const [open, setOpen] = React.useState(false)
  useTick(!!scans.data?.some((s) => s.status === "running"))
  return (
    <div className="space-y-6">
      <PageHeader
        title="Scans"
        description="Agents search the web, read each opportunity's own page and save what they can verify."
        actions={
          <Button size="sm" variant="primary" onClick={() => setOpen(true)} icon={<Plus />}>
            New scan
          </Button>
        }
      />
      {scans.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
      ) : scans.isError ? (
        <ErrorState title="Your scans didn't load" description="Try again in a moment." onRetry={() => void scans.refetch()} />
      ) : !scans.data?.length ? (
        <EmptyState
          illustration={scanningArt}
          title="No scans yet"
          description="A scan sends agents to find new opportunities for startups, researchers or students."
          action={
            <Button size="sm" onClick={() => setOpen(true)} icon={<Plus />}>
              New scan
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-separator bg-surface">
          <div
            aria-hidden="true"
            className="hidden grid-cols-[minmax(0,1fr)_120px_70px_80px_100px] gap-4 border-b border-separator px-4 py-2 text-caption text-ink-tertiary md:grid"
          >
            <span>Scan</span>
            <span>Status</span>
            <span className="text-right">Saved</span>
            <span className="text-right">Duration</span>
            <span className="text-right">Started</span>
          </div>
          <ul className="divide-y divide-separator">
            {scans.data.map((scan) => (
              <li key={scan.id}>
                <ScanRow scan={scan} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <ScanDialog open={open} onOpenChange={setOpen} />
    </div>
  )
}

function ScanRow({ scan }: { scan: Scan }) {
  const duration = formatDuration(scanElapsedMs(scan))
  return (
    <Link
      to={`/scans/${scan.id}`}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-sunk focus-visible:-outline-offset-2 md:grid-cols-[minmax(0,1fr)_120px_70px_80px_100px]"
    >
      <span className="min-w-0">
        <span className="block truncate text-callout font-semibold text-ink">{scanTitle(scan)}</span>
        {scan.focus ? <span className="block truncate text-footnote text-ink-tertiary">Focus: {scan.focus}</span> : null}
      </span>
      <StatusLabel status={scan.status} className="justify-self-end md:justify-self-start" />
      <span className="col-span-2 text-footnote text-ink-tertiary md:hidden">
        {scan.opportunities_added} saved · {duration === "—" ? "" : `${duration} · `}started {formatAgo(scan.created_at)}
      </span>
      <span className="hidden text-right text-callout text-ink tabular-nums md:block">{scan.opportunities_added}</span>
      <span className="hidden text-right text-footnote text-ink-secondary tabular-nums md:block">{duration}</span>
      <span className="hidden text-right text-footnote text-ink-secondary md:block">{formatAgo(scan.created_at)}</span>
    </Link>
  )
}

export function ScanDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const [categories, setCategories] = React.useState<OpportunityCategory[]>([...CATEGORIES])
  const [region, setRegion] = React.useState("Ghana")
  const [focus, setFocus] = React.useState("")
  const start = useMutation({
    mutationFn: () => api.startScan({ categories, region: region.trim(), focus: focus.trim() }),
    onSuccess: (scan) => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      onOpenChange(false)
      navigate(`/scans/${scan.id}`)
    },
    onError: (err) => toastError(err, "Couldn't start the scan"),
  })
  const toggle = (c: OpportunityCategory) =>
    setCategories((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  const agents = categories.length
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onClose={() => onOpenChange(false)}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={(e) => {
            e.preventDefault()
            if (categories.length) start.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>New scan</DialogTitle>
            <DialogDescription>Find open opportunities and add the ones that check out to the catalogue.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <fieldset>
              <legend className="mb-1.5 text-sm leading-5 font-semibold text-ink">Look for</legend>
              <div className="divide-y divide-separator rounded-sm border border-separator">
                {CATEGORIES.map((c) => (
                  <label key={c} className="flex cursor-pointer items-start gap-2.5 px-3 py-2 hover:bg-surface-sunk">
                    <Checkbox
                      className="mt-0.5"
                      checked={categories.includes(c)}
                      onCheckedChange={() => toggle(c)}
                    />
                    <span className="min-w-0">
                      <span className="block text-callout text-ink">{CATEGORY_LABELS[c]}</span>
                      <span className="block truncate text-footnote text-ink-tertiary">{CATEGORY_DESCRIPTIONS[c]}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <Field label="Region">
              <Input value={region} onChange={(e) => setRegion(e.target.value)} maxLength={120} placeholder="Ghana" />
            </Field>
            <Field label="Focus" hint="Optional. Sectors, fields or kinds to look at first.">
              <Input
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                maxLength={2000}
                placeholder="e.g. agritech startups, PhD funding in public health"
              />
            </Field>
            <p className="flex gap-2 text-footnote text-ink-secondary">
              <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-ink-tertiary" />
              <span>
                {agents ? `${agents} ${agents === 1 ? "agent works" : "agents work"} in parallel, one per audience.` : "Pick at least one audience."}{" "}
                Scans usually take 15 to 30 minutes and keep running if you leave.
              </span>
            </p>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={start.isPending || !categories.length}>
              {start.isPending ? "Starting…" : "Start scan"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ScanDetail() {
  const { scanId = "" } = useParams<{ scanId: string }>()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const scan = useQuery({
    queryKey: ["scan", scanId],
    queryFn: () => api.getScan(scanId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 4000 : false),
  })
  const refresh = (next: Scan) => {
    client.setQueryData(["scan", scanId], next)
    void client.invalidateQueries({ queryKey: ["scans"] })
  }
  const cancel = useMutation({ mutationFn: () => api.cancelScan(scanId), onSuccess: refresh, onError: (e) => toastError(e) })
  const remove = useMutation({
    mutationFn: () => api.deleteScan(scanId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scans"] })
      toastSuccess("Scan deleted. What it found stays in the catalogue.")
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
  const tasks = data.tasks ?? []
  const duration = scanElapsedMs(data)
  return (
    <div className="space-y-6">
      <PageHeader
        back={
          <Link to="/scans" className="hover:text-ink hover:underline">
            Scans
          </Link>
        }
        title={scanTitle(data)}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <StatusLabel status={data.status} />
            <span aria-hidden="true">·</span>
            <span>Started {formatAgo(data.created_at)}</span>
            {duration != null ? (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  {running ? "Running for" : "Took"} {formatDuration(duration)}
                </span>
              </>
            ) : null}
            {data.focus ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="min-w-0 truncate">Focus: {data.focus}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          running ? (
            <Button size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()} icon={<Square />}>
              Stop scan
            </Button>
          ) : (
            <Button size="sm" variant="quiet" onClick={() => setConfirmDelete(true)} icon={<Trash2 />}>
              Delete
            </Button>
          )
        }
      />
      <Outcome scan={data} />
      <Progress tasks={tasks} />
      <ActivityLog tasks={tasks} />
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent className="max-w-sm">
          <DialogHeader>
            <AlertDialogTitle className="type-title-3">Delete this scan?</AlertDialogTitle>
            <AlertDialogDescription className="text-callout text-ink-secondary">Its activity log goes. The opportunities it saved stay in the catalogue.</AlertDialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-5">
            <Button variant="quiet" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
              Delete scan
            </Button>
          </DialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

const OUTCOME_PREVIEW = 8

function Outcome({ scan }: { scan: Scan }) {
  const tasks = scan.tasks ?? []
  const saved = savedOpportunities(tasks)
  const [all, setAll] = React.useState(false)
  const running = scan.status === "running"
  const failures = tasks.reduce((n, t) => n + taskStats(t).failures, 0)
  const shown = all ? saved : saved.slice(0, OUTCOME_PREVIEW)
  const count = Math.max(saved.length, scan.opportunities_added)
  return (
    <section aria-labelledby="outcome-heading" className="rounded-lg border border-separator bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 id="outcome-heading" className="text-headline text-ink" aria-live="polite">
          {count === 0
            ? running
              ? "Nothing saved yet"
              : "No new opportunities"
            : `${count} ${count === 1 ? "opportunity" : "opportunities"} saved`}
        </h2>
        {count ? (
          <Link to="/opportunities?sort=new" className="text-footnote font-medium text-link hover:underline">
            See newest in catalogue
          </Link>
        ) : null}
      </div>
      {saved.length ? (
        <ul className="divide-y divide-separator border-t border-separator">
          {shown.map((s) => (
            <li key={s.opportunityId ?? s.title} className="flex items-center gap-3 px-4 py-2.5">
              <Check aria-hidden="true" className="size-4 shrink-0 text-positive" />
              <span className="min-w-0 flex-1">
                {s.opportunityId ? (
                  <Link to={`/opportunities?open=${s.opportunityId}`} className="block truncate text-callout text-ink hover:underline">
                    {s.title}
                  </Link>
                ) : (
                  <span className="block truncate text-callout text-ink">{s.title}</span>
                )}
              </span>
              {!s.created ? <span className="text-footnote text-ink-tertiary">Updated</span> : null}
              {s.deadline ? <Countdown variant="text" daysLeft={daysUntil(s.deadline)} date={s.deadline} /> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="border-t border-separator px-4 py-3 text-footnote text-ink-secondary">
          {running
            ? "Agents are searching and reading pages. Saved opportunities appear here as they are verified."
            : "The agents didn't find anything new they could verify. Try a narrower focus or another region."}
        </p>
      )}
      {saved.length > OUTCOME_PREVIEW ? (
        <div className="border-t border-separator px-4 py-2">
          <button type="button" className="cursor-pointer text-footnote font-medium text-link hover:underline" onClick={() => setAll((v) => !v)}>
            {all ? "Show fewer" : `Show all ${saved.length}`}
          </button>
        </div>
      ) : null}
      {failures ? (
        <p className="flex items-center gap-2 border-t border-separator px-4 py-2.5 text-footnote text-ink-tertiary">
          <Info aria-hidden="true" className="size-3.5 shrink-0" />
          {failures} {failures === 1 ? "step" : "steps"} didn't work and the agents moved on. Details are in the activity log.
        </p>
      ) : null}
    </section>
  )
}

function taskName(task: ScanTask): string {
  const category = (task.target ?? "").replace(/^category:/, "") as OpportunityCategory
  return CATEGORY_LABELS[category] ?? "Agent"
}

function TaskIcon({ status }: { status: ScanTask["status"] }) {
  const cls = "size-4 shrink-0"
  if (status === "running") return <Loader aria-hidden="true" className={cn(cls, "text-info motion-safe:animate-spin motion-safe:[animation-duration:2.4s]")} />
  if (status === "done") return <Check aria-hidden="true" className={cn(cls, "text-positive")} />
  if (status === "error") return <CircleAlert aria-hidden="true" className={cn(cls, "text-caution")} />
  return <CircleDashed aria-hidden="true" className={cn(cls, "text-ink-tertiary")} />
}

function lastAction(task: ScanTask): string | null {
  for (let i = task.log.length - 1; i >= 0; i--) {
    if (task.log[i].kind !== "turn") return describeEvent(task.log[i]).text
  }
  return null
}

function Progress({ tasks }: { tasks: ScanTask[] }) {
  if (!tasks.length) return null
  return (
    <section aria-labelledby="progress-heading" className="space-y-2">
      <h2 id="progress-heading" className="text-caption text-ink-tertiary">
        Agents
      </h2>
      <ol className="divide-y divide-separator rounded-lg border border-separator bg-surface">
        {tasks.map((task) => {
          const stats = taskStats(task)
          const ms = elapsedMs(task.started_at, task.finished_at)
          const now = task.status === "running" ? lastAction(task) : null
          const note = task.error || task.final_text
          return (
            <li key={task.id} className="flex items-start gap-3 px-4 py-3">
              <span className="mt-0.5">
                <TaskIcon status={task.status} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="text-callout font-semibold text-ink">{taskName(task)}</span>
                  <span className="text-footnote text-ink-tertiary">
                    {task.status === "pending"
                      ? "Waiting for a free worker"
                      : `${stats.searches} searches · ${stats.reads} pages read · ${stats.saved} saved`}
                  </span>
                </div>
                {now ? <p className="mt-0.5 truncate text-footnote text-ink-secondary">{now}</p> : null}
                {!now && note ? <p className="mt-0.5 text-footnote text-ink-tertiary">{note}</p> : null}
              </div>
              <span className="shrink-0 text-right text-footnote text-ink-tertiary tabular-nums">
                {task.status === "pending" ? "" : formatDuration(ms)}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
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
        className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-4 py-3 text-left hover:bg-surface-sunk"
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
          <Link to={`/opportunities?open=${line.opportunityId}`} className="hover:underline">
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

