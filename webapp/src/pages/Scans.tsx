import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, ChevronDown, Radar, Sparkles, Trash2 } from "lucide-react"
import * as api from "../lib/api"
import { formatAgo } from "../lib/format"
import { CATEGORIES, CATEGORY_DESCRIPTIONS, CATEGORY_LABELS } from "../lib/opportunities"
import { toastError, toastSuccess } from "../lib/toast"
import { cn } from "@blesser/ui"
import type { OpportunityCategory, Scan, ScanTask } from "../lib/types"
import { Button, Chip, Field, Input, Textarea, buttonVariants, type ChipTone } from "@blesser/ui"
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

const STATUS_CHIP: Record<ScanTask["status"], { tone: ChipTone; label: string }> = {
  running: { tone: "info", label: "Running" },
  pending: { tone: "neutral", label: "Waiting" },
  done: { tone: "forest", label: "Finished" },
  error: { tone: "critical", label: "Stopped with an error" },
  cancelled: { tone: "neutral", label: "Stopped" },
}

function StatusChip({ status }: { status: ScanTask["status"] }) {
  const chip = STATUS_CHIP[status]
  return <Chip tone={chip.tone}>{chip.label}</Chip>
}

function scanTitle(scan: Scan): string {
  return `${scan.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")} in ${scan.region}`
}

export function Scans() {
  const scans = useQuery({ queryKey: ["scans"], queryFn: api.listScans, refetchInterval: 10_000 })
  const [open, setOpen] = React.useState(false)
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="type-title-2">Scans</h1>
          <p className="text-callout text-ink-secondary max-w-2xl">
            Agents search the web, read each opportunity's own page and add what they verify to the public catalogue.
          </p>
        </div>
        <Button size="sm" variant="primary" onClick={() => setOpen(true)} icon={<Sparkles />}>
          Start a scan
        </Button>
      </header>
      {scans.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
      ) : scans.isError ? (
        <ErrorState title="Your scans didn't load" description="Try again in a moment." onRetry={() => void scans.refetch()} />
      ) : !scans.data?.length ? (
        <EmptyState
          title="No scans yet"
          description="Start one to find new opportunities for startups, researchers or students."
          action={
            <Button onClick={() => setOpen(true)} icon={<Sparkles />}>
              Start a scan
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface shadow-elevation-1">
          {scans.data.map((scan) => (
            <li key={scan.id}>
              <Link to={`/scans/${scan.id}`} className="flex items-center gap-3 px-5 py-3.5 hover:bg-surface-sunk">
                <Radar className="size-5 shrink-0 text-ink-tertiary" strokeWidth={1.75} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-headline text-ink">{scanTitle(scan)}</span>
                  <span className="block text-footnote text-ink-secondary">
                    Started {formatAgo(scan.created_at)} · {scan.opportunities_added} added
                  </span>
                </span>
                <StatusChip status={scan.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
      <ScanDialog open={open} onOpenChange={setOpen} />
    </div>
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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" onClose={() => onOpenChange(false)}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={(e) => {
            e.preventDefault()
            if (categories.length) start.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>Find more opportunities</DialogTitle>
            <DialogDescription>
              One agent per audience searches the web and adds what it can verify to the public catalogue.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm font-semibold text-ink">Look for</legend>
              {CATEGORIES.map((c) => (
                <label key={c} className="flex items-start gap-2 text-callout">
                  <input type="checkbox" className="mt-0.5 size-4 accent-forest" checked={categories.includes(c)} onChange={() => toggle(c)} />
                  <span>
                    <span className="font-medium text-ink">{CATEGORY_LABELS[c]}</span>
                    <span className="block text-ink-secondary">{CATEGORY_DESCRIPTIONS[c]}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <Field label="Region">
              <Input value={region} onChange={(e) => setRegion(e.target.value)} maxLength={120} placeholder="Ghana" />
            </Field>
            <Field label="Focus (optional)">
              <Textarea
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="e.g. agritech and climate startups; PhD funding in public health"
              />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={start.isPending || !categories.length} icon={<Sparkles />}>
              Start a scan
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
  const scan = useQuery({
    queryKey: ["scan", scanId],
    queryFn: () => api.getScan(scanId),
    // Live while agents work; still once the scan is over.
    refetchInterval: (query) => (query.state.data?.status === "running" ? 3000 : false),
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

  if (scan.isLoading) return <div className="h-40 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
  if (scan.isError || !scan.data)
    return <ErrorState title="This scan didn't load" description="It may have been deleted." onRetry={() => void scan.refetch()} />
  const data = scan.data
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link to="/scans" className="text-callout font-semibold text-link hover:underline">
          Scans
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="type-title-2 min-w-0 flex-1">{scanTitle(data)}</h1>
          <StatusChip status={data.status} />
        </div>
        <p className="text-callout text-ink-secondary">
          Started {formatAgo(data.created_at)} · {data.opportunities_added} new{" "}
          {data.opportunities_added === 1 ? "opportunity" : "opportunities"}
          {data.focus ? ` · Focus: ${data.focus}` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          <Link to="/opportunities?sort=new" className={buttonVariants({ size: "sm", variant: "secondary" })}>
            See the newest opportunities
          </Link>
          {data.status === "running" ? (
            <Button size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()} icon={<Ban />}>
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="quiet" disabled={remove.isPending} onClick={() => remove.mutate()} icon={<Trash2 />}>
              Delete
            </Button>
          )}
        </div>
      </header>
      <div className="space-y-3">
        {(data.tasks ?? []).map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  )
}

function taskLabel(task: ScanTask): string {
  const category = (task.target ?? "").replace(/^category:/, "") as OpportunityCategory
  return CATEGORY_LABELS[category] ? `Opportunities for ${CATEGORY_LABELS[category].toLowerCase()}` : "Find opportunities"
}

function describe(event: ScanTask["log"][number]): string {
  const input = event.input ?? {}
  if (event.tool === "search_web") return `Searched: ${String(input.query ?? "")}`
  if (event.tool === "fetch_page") return `Read ${String(input.url ?? "")}`
  if (event.tool === "save_opportunity") return `Saved ${String(input.title ?? "an opportunity")}`
  return event.tool ?? ""
}

function TaskCard({ task }: { task: ScanTask }) {
  const [open, setOpen] = React.useState(task.status === "running")
  const saves = task.log.filter((e) => e.tool === "save_opportunity" && e.ok).length
  return (
    <section className="rounded-lg border border-separator bg-surface shadow-elevation-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-3 px-5 py-3.5 text-left"
      >
        <span className="min-w-0 flex-1">
          <span className={cn("block text-headline text-ink", task.status === "running" && "shimmer-text")}>
            {taskLabel(task)}
          </span>
          <span className="block text-footnote text-ink-secondary">
            {task.log.length} steps · {saves} saved{task.turns ? ` · ${task.turns} turns` : ""}
          </span>
        </span>
        <StatusChip status={task.status} />
        <ChevronDown className={cn("size-4 text-ink-tertiary transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="space-y-2 border-t border-separator px-5 py-3">
          {task.error ? <p className="text-sm text-critical">{task.error}</p> : null}
          {task.log.length === 0 ? (
            <p className="text-sm text-ink-secondary">{task.status === "pending" ? "Waiting for a worker." : "No steps recorded."}</p>
          ) : (
            <ol className="space-y-1.5">
              {task.log.map((event, i) =>
                event.kind === "turn" ? (
                  <li key={i} className="text-sm whitespace-pre-wrap text-ink-secondary italic">
                    {event.note}
                  </li>
                ) : (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", event.ok ? "bg-positive" : "bg-caution")} />
                    <span className="min-w-0 break-words text-ink">
                      {describe(event)}
                      {!event.ok && event.result_preview ? (
                        <span className="block text-xs text-ink-tertiary">{event.result_preview.slice(0, 240)}</span>
                      ) : null}
                    </span>
                  </li>
                ),
              )}
            </ol>
          )}
          {task.final_text ? (
            <p className="rounded-sm bg-surface-sunk p-3 text-callout whitespace-pre-wrap text-ink">{task.final_text}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
