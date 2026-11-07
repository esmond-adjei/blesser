import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, ChevronDown, Radar, Sparkles, Trash2 } from "lucide-react"
import * as api from "../lib/api"
import { formatAgo } from "../lib/format"
import { CATEGORIES, CATEGORY_DESCRIPTIONS, CATEGORY_LABELS } from "../lib/opportunities"
import { toastError, toastSuccess } from "../lib/toast"
import { cn } from "../lib/utils"
import type { OpportunityCategory, Scan, ScanTask } from "../lib/types"
import { Badge } from "../components/ui/badge"
import { Button, buttonVariants } from "../components/ui/button"
import { Field, Input, Textarea } from "../components/ui/input"
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

const STATUS_VARIANT = {
  running: "info",
  pending: "secondary",
  done: "success",
  error: "destructive",
  cancelled: "outline",
} as const

function scanTitle(scan: Scan): string {
  return `${scan.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")} in ${scan.region}`
}

export function Scans() {
  const scans = useQuery({ queryKey: ["scans"], queryFn: api.listScans, refetchInterval: 10_000 })
  const [open, setOpen] = React.useState(false)
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="type-page-title">Scans</h1>
          <p className="type-meta max-w-2xl">
            Agents search the web, read each opportunity's own page and add what they verify to the public catalogue.
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Sparkles /> New scan
        </Button>
      </header>
      {scans.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-fill-quiet" />
      ) : scans.isError ? (
        <ErrorState title="Couldn't load your scans" description="Try again in a moment." onRetry={() => void scans.refetch()} />
      ) : !scans.data?.length ? (
        <EmptyState
          title="No scans yet"
          description="Start one to find new opportunities for startups, researchers or students."
          action={
            <Button size="sm" onClick={() => setOpen(true)}>
              <Sparkles /> New scan
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
          {scans.data.map((scan) => (
            <li key={scan.id}>
              <Link to={`/scans/${scan.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-fill-quiet">
                <Radar className="size-4 shrink-0 text-label-tertiary" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-label">{scanTitle(scan)}</span>
                  <span className="block text-xs text-label-secondary">
                    Started {formatAgo(scan.created_at)} · {scan.opportunities_added} added
                  </span>
                </span>
                <Badge variant={STATUS_VARIANT[scan.status]}>{scan.status === "done" ? "Finished" : scan.status}</Badge>
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
              <legend className="g-label mb-1">Look for</legend>
              {CATEGORIES.map((c) => (
                <label key={c} className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={categories.includes(c)} onChange={() => toggle(c)} />
                  <span>
                    <span className="font-medium text-label">{CATEGORY_LABELS[c]}</span>
                    <span className="block text-label-secondary">{CATEGORY_DESCRIPTIONS[c]}</span>
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
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={start.isPending || !categories.length}>
              <Sparkles /> Start scan
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

  if (scan.isLoading) return <div className="h-40 animate-pulse rounded-lg bg-fill-quiet" />
  if (scan.isError || !scan.data)
    return <ErrorState title="Couldn't load this scan" description="It may have been deleted." onRetry={() => void scan.refetch()} />
  const data = scan.data
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link to="/scans" className="text-sm text-label-secondary hover:underline">
          Scans
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="type-page-title min-w-0 flex-1">{scanTitle(data)}</h1>
          <Badge variant={STATUS_VARIANT[data.status]}>{data.status === "done" ? "Finished" : data.status}</Badge>
        </div>
        <p className="type-meta">
          Started {formatAgo(data.created_at)} · {data.opportunities_added} new{" "}
          {data.opportunities_added === 1 ? "opportunity" : "opportunities"}
          {data.focus ? ` · Focus: ${data.focus}` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          <Link to="/opportunities?sort=new" className={buttonVariants({ size: "sm", variant: "outline" })}>
            See the newest opportunities
          </Link>
          {data.status === "running" ? (
            <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              <Ban /> Stop
            </Button>
          ) : (
            <Button size="sm" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
              <Trash2 /> Delete
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
    <section className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="min-w-0 flex-1">
          <span className={cn("block text-sm font-semibold text-label", task.status === "running" && "shimmer-text")}>
            {taskLabel(task)}
          </span>
          <span className="block text-xs text-label-secondary">
            {task.log.length} steps · {saves} saved{task.turns ? ` · ${task.turns} turns` : ""}
          </span>
        </span>
        <Badge variant={STATUS_VARIANT[task.status]}>{task.status}</Badge>
        <ChevronDown className={cn("size-4 text-label-tertiary transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="space-y-2 border-t border-border px-4 py-3">
          {task.error ? <p className="text-sm text-critical">{task.error}</p> : null}
          {task.log.length === 0 ? (
            <p className="text-sm text-label-secondary">{task.status === "pending" ? "Waiting for a worker." : "No steps recorded."}</p>
          ) : (
            <ol className="space-y-1.5">
              {task.log.map((event, i) =>
                event.kind === "turn" ? (
                  <li key={i} className="text-sm whitespace-pre-wrap text-label-secondary italic">
                    {event.note}
                  </li>
                ) : (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", event.ok ? "bg-positive" : "bg-critical")} />
                    <span className="min-w-0 break-words text-label">
                      {describe(event)}
                      {!event.ok && event.result_preview ? (
                        <span className="block text-xs text-label-tertiary">{event.result_preview.slice(0, 240)}</span>
                      ) : null}
                    </span>
                  </li>
                ),
              )}
            </ol>
          )}
          {task.final_text ? (
            <p className="rounded-md bg-fill-quiet p-3 text-sm whitespace-pre-wrap text-label">{task.final_text}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
