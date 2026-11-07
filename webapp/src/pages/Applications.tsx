import * as React from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, Plus, Trash2 } from "lucide-react"
import { OPEN_STATUSES, STATUSES, STATUS_LABEL, useApplicationMutations, useApplications } from "../lib/applications"
import { formatDay } from "../lib/format"
import { toastError, toastSuccess } from "../lib/toast"
import { cn } from "../lib/utils"
import type { Application, ApplicationStatus, RequirementItem } from "../lib/types"
import { Badge } from "../components/ui/badge"
import { Button, buttonVariants } from "../components/ui/button"
import { Field, Input, Textarea } from "../components/ui/input"
import { Select } from "../components/ui/select"
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

function todayIso(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

function daysUntil(day: string): number {
  return Math.round((Date.parse(`${day}T00:00:00Z`) - Date.parse(`${todayIso()}T00:00:00Z`)) / 86_400_000)
}

function DeadlineBadge({ app }: { app: Application }) {
  if (!app.deadline_date) return app.deadline ? <Badge variant="secondary">{app.deadline}</Badge> : null
  const days = daysUntil(app.deadline_date)
  const open = OPEN_STATUSES.includes(app.status)
  const label = days < 0 ? "Deadline passed" : days === 0 ? "Due today" : days === 1 ? "Due tomorrow" : `${days} days left`
  const variant = !open ? "outline" : days < 0 ? "outline" : days <= 7 ? "destructive" : days <= 21 ? "warning" : "success"
  return (
    <Badge variant={variant} data-tooltip={formatDay(app.deadline_date)}>
      {open ? label : formatDay(app.deadline_date)}
    </Badge>
  )
}

const FILTERS = [
  { value: "active", label: "In progress" },
  { value: "all", label: "All" },
  ...STATUSES,
]

export function Applications() {
  const { data, isLoading, isError, refetch } = useApplications()
  const { update } = useApplicationMutations()
  const [filter, setFilter] = React.useState("active")
  const [editing, setEditing] = React.useState<Application | null>(null)
  const [adding, setAdding] = React.useState(false)

  const apps = (data ?? []).filter((a) => {
    if (filter === "all") return true
    if (filter === "active") return a.status !== "accepted" && a.status !== "rejected"
    return a.status === filter
  })

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="type-page-title">Applications</h1>
          <p className="type-meta max-w-2xl">
            Everything you're applying for, from saved to accepted. Saved and preparing applications get deadline
            reminders 14, 7 and 1 days before.
          </p>
        </div>
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus /> Add by hand
        </Button>
      </header>

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => {
          const count =
            f.value === "all"
              ? data?.length
              : f.value === "active"
                ? data?.filter((a) => a.status !== "accepted" && a.status !== "rejected").length
                : data?.filter((a) => a.status === f.value).length
          return (
            <button
              key={f.value}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "inline-flex h-8 items-center rounded-full border px-3 text-sm transition-colors",
                filter === f.value ? "border-tint bg-tint-soft text-tint" : "border-border text-label-secondary hover:bg-fill-quiet",
              )}
            >
              {f.label}
              {count ? <span className="ml-1.5 text-xs opacity-70">{count}</span> : null}
            </button>
          )
        })}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-fill-quiet" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState title="Couldn't load your applications" description="Try again in a moment." onRetry={() => void refetch()} />
      ) : apps.length === 0 ? (
        <EmptyState
          title={data?.length ? "Nothing with this status" : "Nothing tracked yet"}
          description="Track an opportunity from the catalogue, or add one by hand."
          action={
            <Link to="/opportunities" className={buttonVariants({ size: "sm" })}>
              Browse opportunities
            </Link>
          }
        />
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
          {apps.map((app) => {
            const done = app.requirements.filter((r) => r.done).length
            return (
              <li key={app.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <button type="button" className="w-full min-w-0 text-left sm:w-auto sm:flex-1" onClick={() => setEditing(app)}>
                  <span className="block truncate text-sm font-semibold text-label hover:underline">{app.title}</span>
                  <span className="block truncate text-xs text-label-secondary">
                    {[app.organization, app.kind].filter(Boolean).join(" · ")}
                    {app.requirements.length ? ` · ${done}/${app.requirements.length} ready` : ""}
                  </span>
                </button>
                <DeadlineBadge app={app} />
                <Select
                  aria-label={`Status of ${app.title}`}
                  className="ml-auto w-auto min-w-[140px] sm:ml-0"
                  value={app.status}
                  onChange={(e) =>
                    update.mutate(
                      { id: app.id, body: { status: e.target.value as ApplicationStatus } },
                      { onError: (err) => toastError(err, "Couldn't update the status") },
                    )
                  }
                >
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </li>
            )
          })}
        </ul>
      )}

      <ApplicationDialog app={editing} onClose={() => setEditing(null)} />
      <AddDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}

function ApplicationDialog({ app, onClose }: { app: Application | null; onClose: () => void }) {
  const { update, remove } = useApplicationMutations()
  const [shown, setShown] = React.useState<Application | null>(app)
  const [notes, setNotes] = React.useState("")
  const [deadline, setDeadline] = React.useState("")
  const [requirements, setRequirements] = React.useState<RequirementItem[]>([])
  const [newItem, setNewItem] = React.useState("")
  if (app && app !== shown) {
    setShown(app)
    setNotes(app.notes)
    setDeadline(app.deadline_date ?? "")
    setRequirements(app.requirements)
    setNewItem("")
  }
  const save = (body: Parameters<typeof update.mutate>[0]["body"]) =>
    shown && update.mutate({ id: shown.id, body }, { onError: (err) => toastError(err, "Couldn't save") })

  return (
    <Dialog open={!!app} onOpenChange={(open) => !open && onClose()}>
      {shown ? (
        <DialogContent className="max-w-xl" onClose={onClose}>
          <DialogHeader>
            <DialogTitle>{shown.title}</DialogTitle>
            <DialogDescription>
              {[shown.organization, shown.kind, STATUS_LABEL[shown.status]].filter(Boolean).join(" · ")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            {shown.benefits ? <p className="text-sm font-medium text-label">{shown.benefits}</p> : null}
            <Field label="Deadline">
              <Input
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                onBlur={() => deadline !== (shown.deadline_date ?? "") && save({ deadline_date: deadline || null })}
              />
            </Field>
            <div>
              <p className="g-label mb-1.5">What to prepare</p>
              <ul className="space-y-1.5">
                {requirements.map((r, i) => (
                  <li key={`${r.label}-${i}`} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={r.done}
                      aria-label={r.label}
                      onChange={() => {
                        const next = requirements.map((x, j) => (j === i ? { ...x, done: !x.done } : x))
                        setRequirements(next)
                        save({ requirements: next })
                      }}
                    />
                    <span className={cn(r.done && "text-label-tertiary line-through")}>{r.label}</span>
                  </li>
                ))}
              </ul>
              <form
                className="mt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (!newItem.trim()) return
                  const next = [...requirements, { label: newItem.trim(), done: false }]
                  setRequirements(next)
                  setNewItem("")
                  save({ requirements: next })
                }}
              >
                <Input
                  aria-label="Add an item"
                  placeholder="Add an item, e.g. Two references"
                  value={newItem}
                  onChange={(e) => setNewItem(e.target.value)}
                  className="flex-1"
                />
                <Button type="submit" size="sm" variant="outline" disabled={!newItem.trim()}>
                  Add
                </Button>
              </form>
            </div>
            <Field label="Notes">
              <Textarea
                rows={4}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => notes !== shown.notes && save({ notes })}
              />
            </Field>
          </DialogBody>
          <DialogFooter className="flex-wrap">
            <Button
              size="sm"
              variant="ghost"
              className="mr-auto text-critical"
              onClick={() =>
                remove.mutate(shown.id, {
                  onSuccess: () => {
                    toastSuccess("Removed from your applications")
                    onClose()
                  },
                  onError: (err) => toastError(err, "Couldn't remove it"),
                })
              }
            >
              <Trash2 /> Remove
            </Button>
            {shown.link ? (
              <a href={shown.link} target="_blank" rel="noopener noreferrer" className={buttonVariants({ size: "sm", variant: "outline" })}>
                Open <ArrowUpRight />
              </a>
            ) : null}
            <Button size="sm" onClick={onClose}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

function AddDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { create } = useApplicationMutations()
  const [form, setForm] = React.useState({ title: "", organization: "", link: "", deadline: "" })
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }))
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" onClose={onClose}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { title: form.title.trim(), organization: form.organization.trim(), link: form.link.trim(), deadline: form.deadline },
              {
                onSuccess: () => {
                  setForm({ title: "", organization: "", link: "", deadline: "" })
                  onClose()
                },
                onError: (err) => toastError(err, "Couldn't add it"),
              },
            )
          }}
        >
          <DialogHeader>
            <DialogTitle>Add an application</DialogTitle>
            <DialogDescription>For something that isn't in the catalogue.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="Name">
              <Input value={form.title} onChange={(e) => set("title", e.target.value)} required maxLength={300} />
            </Field>
            <Field label="Organization">
              <Input value={form.organization} onChange={(e) => set("organization", e.target.value)} maxLength={200} />
            </Field>
            <Field label="Link">
              <Input type="url" value={form.link} onChange={(e) => set("link", e.target.value)} placeholder="https://" />
            </Field>
            <Field label="Deadline">
              <Input type="date" value={form.deadline} onChange={(e) => set("deadline", e.target.value)} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || !form.title.trim()}>
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
